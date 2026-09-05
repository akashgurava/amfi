from __future__ import annotations

from datetime import date, datetime

import httpx
import pytest

from amfi.client import (
    AmfiClient,
    MultiWindowRateLimiter,
    RateLimitRule,
    _date_key,
    _to_date,
)
from amfi.error import AppConfigError, HttpClientNotInitializedError


def test_to_date_accepts_date_datetime_and_iso_string() -> None:
    assert _to_date(date(2024, 1, 2)) == date(2024, 1, 2)
    assert _to_date(datetime(2024, 1, 2, 10, 30)) == date(2024, 1, 2)
    assert _to_date("2024-01-02") == date(2024, 1, 2)


def test_to_date_rejects_unsupported_type() -> None:
    with pytest.raises(TypeError):
        _to_date(12345)  # type: ignore[arg-type]


def test_date_key_returns_iso_date() -> None:
    assert _date_key("2024-01-02") == "2024-01-02"
    assert _date_key(date(2024, 1, 2)) == "2024-01-02"


def test_rate_limit_rule_validation() -> None:
    with pytest.raises(ValueError, match="max_requests"):
        RateLimitRule(max_requests=0, window_seconds=1)
    with pytest.raises(ValueError, match="window_seconds"):
        RateLimitRule(max_requests=1, window_seconds=0)


def test_rate_limit_rule_per_seconds_factory() -> None:
    rule = RateLimitRule.per_seconds(5, 2)
    assert rule.max_requests == 5
    assert rule.window_seconds == 2


@pytest.mark.asyncio
async def test_multi_window_rate_limiter_noop_without_rules() -> None:
    limiter = MultiWindowRateLimiter()
    # Should return immediately.
    await limiter.acquire()


@pytest.mark.asyncio
async def test_amfi_client_rejects_invalid_parallel_requests() -> None:
    with pytest.raises(AppConfigError):
        AmfiClient(parallel_requests=-1)


@pytest.mark.asyncio
async def test_amfi_client_rejects_invalid_timeout() -> None:
    with pytest.raises(AppConfigError):
        AmfiClient(timeout_seconds=0)


@pytest.mark.asyncio
async def test_amfi_client_rejects_negative_max_retries() -> None:
    with pytest.raises(AppConfigError):
        AmfiClient(max_retries=-1)


@pytest.mark.asyncio
async def test_fetch_date_without_context_manager_raises() -> None:
    client = AmfiClient()
    with pytest.raises(HttpClientNotInitializedError):
        await client.fetch_date("2024-01-01")


@pytest.mark.asyncio
async def test_fetch_date_builds_expected_request_and_parses_tuple() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "mfName": "Sample MF",
                        "schemes": [
                            {
                                "schemeName": "Sample Scheme",
                                "navs": [
                                    {
                                        "SD_ID": "101",
                                        "NAV_Name": "Sample - Direct - Growth",
                                        "hNAV_Amt": "12.3456",
                                        "ISIN_RI": "",
                                        "ISIN_PO": "INF000000001",
                                        "hNAV_Date": "2024-01-02T00:00:00.000Z",
                                        "hNAV_Dtstamp": "2024-01-02T20:00:00Z",
                                        "hNAV_reissue": "",
                                        "hNAV_repurchase": "",
                                        "hNAV_Upload_display": "02 Jan 2024 20:00:00",
                                    }
                                ],
                            }
                        ],
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://www.amfiindia.com",
    ) as http:
        client = AmfiClient(client=http)
        plan_details, navs = await client.fetch_date("2024-01-02")

    assert len(captured) == 1
    assert captured[0].url.path == "/api/nav-history"
    assert captured[0].url.params["query_type"] == "all_for_date"
    assert captured[0].url.params["from_date"] == "2024-01-02"

    assert len(plan_details) == 1
    assert plan_details[0].sd_id == "101"
    assert plan_details[0].fund_house == "Sample MF"
    assert plan_details[0].scheme == "Sample Scheme"
    assert plan_details[0].plan == "Sample - Direct - Growth"

    assert len(navs) == 1
    assert navs[0].sd_id == "101"
    assert navs[0].hnav_amt == "12.3456"
    assert navs[0].isin_po == "INF000000001"


@pytest.mark.asyncio
async def test_fetch_fund_house_details_parses_next_payload() -> None:
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
    html = f"""
    <html><body>
    <script>self.__next_f.push([1,"{payload_inner}"])</script>
    </body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://www.amfiindia.com"
    ) as http:
        client = AmfiClient(client=http)
        fund_houses = await client.fetch_fund_house_details()

    assert len(fund_houses) == 1
    assert fund_houses[0].mf_id == "123"
    assert fund_houses[0].mf_name == "Test Fund"
    assert fund_houses[0].amc_name == "Test AMC"


@pytest.mark.asyncio
async def test_client_context_manager_opens_and_closes() -> None:
    async with AmfiClient() as client:
        assert client._client is not None
    assert client._client is None


@pytest.mark.asyncio
async def test_fetch_scheme_aum_no_data_found() -> None:
    from amfi.client import SchemeListItem

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": "No data found."})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = AmfiClient(client=http)
        scheme = SchemeListItem(scheme_id="1", scheme_name="Test Scheme", mf_id="10")
        rows = await client.fetch_scheme_aum(scheme)
        assert rows == []

