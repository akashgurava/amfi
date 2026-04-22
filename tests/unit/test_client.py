from __future__ import annotations

from datetime import date

import httpx
import pytest

from amfi.client import (
    AmfiClient,
    RateLimitRule,
    RequestExecutionError,
    ResponsePayloadError,
)


@pytest.mark.asyncio
async def test_fetch_date_builds_expected_request() -> None:
    captured: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"data": [{"mfName": "Sample"}]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://www.amfiindia.com",
    ) as http_client:
        client = AmfiClient(client=http_client)
        payload = await client.fetch_date("2010-01-01")

    assert payload["data"][0]["mfName"] == "Sample"
    assert len(captured) == 1
    assert captured[0].url.path == "/api/nav-history"
    assert captured[0].url.params["query_type"] == "all_for_date"
    assert captured[0].url.params["from_date"] == "2010-01-01"


@pytest.mark.asyncio
async def test_fetch_date_range_retries_failed_date_first() -> None:
    call_order: list[str] = []
    attempts: dict[str, int] = {}

    class StubClient(AmfiClient):
        async def fetch_date(self, nav_date: date | str) -> dict[str, object]:
            key = nav_date if isinstance(nav_date, str) else nav_date.isoformat()
            call_order.append(key)
            attempts[key] = attempts.get(key, 0) + 1
            if key == "2010-01-01" and attempts[key] == 1:
                raise RuntimeError("retry me")
            return {"date": key}

    client = StubClient(parallel_requests=1, max_retries=2)
    summary = await client.fetch_date_range("2010-01-01", "2010-01-02")

    assert summary.results["2010-01-01"]["date"] == "2010-01-01"
    assert summary.results["2010-01-02"]["date"] == "2010-01-02"
    assert summary.failure_count == 0
    assert call_order == ["2010-01-01", "2010-01-01", "2010-01-02"]


@pytest.mark.asyncio
async def test_fetch_date_range_records_failure_when_retries_exhausted() -> None:
    class FailingClient(AmfiClient):
        async def fetch_date(self, nav_date: date | str) -> dict[str, object]:
            raise RuntimeError("always fails")

    client = FailingClient(parallel_requests=1, max_retries=1)
    summary = await client.fetch_date_range("2010-01-01", "2010-01-01")

    assert summary.success_count == 0
    assert summary.failure_count == 1
    assert "2010-01-01" in summary.failed_dates


def test_rate_limit_rule_validation() -> None:
    with pytest.raises(ValueError, match="max_requests"):
        RateLimitRule(max_requests=0, window_seconds=1)

    with pytest.raises(ValueError, match="window_seconds"):
        RateLimitRule(max_requests=1, window_seconds=0)


@pytest.mark.asyncio
async def test_fetch_date_range_does_not_retry_payload_errors() -> None:
    call_order: list[str] = []

    class PayloadErrorClient(AmfiClient):
        async def fetch_date(self, nav_date: date | str) -> dict[str, object]:
            key = nav_date if isinstance(nav_date, str) else nav_date.isoformat()
            call_order.append(key)
            if key == "2010-01-01":
                raise ResponsePayloadError("invalid response payload")
            return {"date": key}

    client = PayloadErrorClient(parallel_requests=1, max_retries=5)
    summary = await client.fetch_date_range("2010-01-01", "2010-01-02")

    assert summary.success_count == 1
    assert summary.failure_count == 1
    assert "2010-01-01" in summary.failed_dates
    assert call_order == ["2010-01-01", "2010-01-02"]


@pytest.mark.asyncio
async def test_fetch_date_range_aborts_after_consecutive_errors() -> None:
    class AlwaysFailClient(AmfiClient):
        async def fetch_date(self, nav_date: date | str) -> dict[str, object]:
            raise RequestExecutionError("rate limit simulated")

    client = AlwaysFailClient(parallel_requests=1, max_retries=None)
    summary = await client.fetch_date_range(
        "2010-01-01",
        "2010-01-05",
        consecutive_error_limit=3,
    )

    assert summary.aborted is True
    assert summary.abort_reason is not None
    assert summary.failure_count >= 3


@pytest.mark.asyncio
async def test_fetch_scheme_details_parses_response() -> None:
    # Minimal reproduction of the React Server Components payload
    # The parser expects:
    # self.__next_f.push([1,"c:[\"$\",\"$L17\",null,{\"mutualFunds\":...
    # The string inside is a JSON string representing the array structure.

    # Inner JSON structure includes the full FundHouseResponse payload.

    # Escaped as a string literal (what matches the regex group):
    # c:[\"$\",\"$L17\",null,{\"mutualFunds\":[{\"mf_name\": \"Test Fund\", ...}]}]

    # We need to be careful with escaping for the Python string literal to represent
    # the HTML content.
    payload_inner = (
        r"c:[\"$\",\"$L17\",null,{\"mutualFunds\":"
        r"[{\"mf_id\": \"123\", \"mf_name\": \"Test Fund\", "
        r"\"amc_name\": \"Test AMC\", \"amc_website\": \"\", "
        r"\"amc_schemewise_annual_report\": \"\", "
        r"\"amc_fortnightly_portfolio_disclosure\": \"\", "
        r"\"amc_monthly_portfolio_disclosure\": \"\", "
        r"\"amc_halfYearly_portfolio_disclosure\": \"\", "
        r"\"amc_monthly_mf_factsheets\": \"\", "
        r"\"amc_riskometer_monthly\": \"\", "
        r"\"amc_riskometer_yearly\": \"\", "
        r"\"amc_unclaimed_dividend_amt\": \"\", "
        r"\"amc_unclaimed_redemption_amt\": \"\", "
        r"\"amc_investonline_in_mf\": \"\", "
        r"\"rss_latest_nav\": \"\", \"rss_latest_aum\": \"\", "
        r"\"statement_of_information\": \"\", \"scheme_wise\": \"\", "
        r"\"icon_wordmark\": {}, \"icons\": []}]}]"
    )

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <body>
        <script>
            self.__next_f.push([1,"{payload_inner}"])
        </script>
    </body>
    </html>
    """

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html_content)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://www.amfiindia.com",
    ) as http_client:
        client = AmfiClient(client=http_client)
        schemes = await client.fetch_fund_house_details()

    assert len(schemes) == 1
    assert schemes[0].mf_name == "Test Fund"
    assert schemes[0].mf_id == "123"
