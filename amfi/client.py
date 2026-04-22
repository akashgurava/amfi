from __future__ import annotations

import asyncio
import json
import re
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime

import httpx
from tqdm.asyncio import tqdm as tqdm_async
from typing_extensions import Any

from .data import (
    RawFundHouseResponse,
    RawSchemeAumResponse,
    RawSchemeDocumentResponse,
    RawSchemeResponse,
    RawNavResponse,
    RawNavPlanDetailsResponse,
)
from .error import (
    AppConfigError,
    HttpClientNotInitializedError,
    RequestExecutionError,
)
from .utils import LOGGER

DateLike = date | datetime | str
ProgressCallback = Callable[[int, int, str | None, tuple[str, ...]], None]
# SuccessCallback = Callable[
#     [duckdb.DuckDBPyConnection, str, dict[str, Any], tqdm_asyncio[Never]],
#     Awaitable[None] | None,
# ]


def _to_date(value: DateLike) -> date:
    """Normalize supported date input into a `datetime.date`."""

    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise TypeError(f"Unsupported date type: {type(value)!r}")


def _date_key(value: DateLike) -> str:
    """Convert supported date input into an ISO date key (`YYYY-MM-DD`)."""

    return _to_date(value).isoformat()


@dataclass(frozen=True)
class RateLimitRule:
    """Single fixed-window rate-limit rule.

    Attributes:
        max_requests: Maximum requests allowed in one window.
        window_seconds: Window size in seconds.
    """

    max_requests: int
    window_seconds: float

    def __post_init__(self) -> None:
        if self.max_requests <= 0:
            raise ValueError("max_requests must be > 0")
        if self.window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")

    @classmethod
    def per_seconds(cls, requests: int, seconds: float = 1) -> RateLimitRule:
        """Create a rule like `N requests / seconds`."""

        return cls(max_requests=requests, window_seconds=seconds)

    @classmethod
    def per_n_minutes(cls, requests: int, minutes: float = 1) -> RateLimitRule:
        """Create a rule like `N requests / minutes`."""

        return cls(max_requests=requests, window_seconds=minutes * 60)


class MultiWindowRateLimiter:
    """Composite rate limiter that enforces all configured fixed windows."""

    def __init__(self, rules: list[RateLimitRule] | None = None) -> None:
        self._rules = rules or []
        self._events: list[deque[float]] = [deque() for _ in self._rules]
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Block until one request can be issued while honoring all rules."""

        if not self._rules:
            return

        while True:
            sleep_for = 0.0
            async with self._lock:
                now = time.monotonic()
                for bucket, rule in zip(self._events, self._rules, strict=False):
                    cutoff = now - rule.window_seconds
                    while bucket and bucket[0] <= cutoff:
                        bucket.popleft()

                for bucket, rule in zip(self._events, self._rules, strict=False):
                    if len(bucket) >= rule.max_requests:
                        wait_for = bucket[0] + rule.window_seconds - now
                        sleep_for = max(sleep_for, wait_for)

                if sleep_for <= 0:
                    stamp = time.monotonic()
                    for bucket in self._events:
                        bucket.append(stamp)
                    return

            await asyncio.sleep(sleep_for)


class _DateQueue:
    """Async deque with support for front insertion (priority retries)."""

    def __init__(self) -> None:
        self._items: deque[str] = deque()
        self._condition = asyncio.Condition()

    async def put(self, item: str) -> None:
        async with self._condition:
            self._items.append(item)
            self._condition.notify()

    async def put_front(self, item: str) -> None:
        async with self._condition:
            self._items.appendleft(item)
            self._condition.notify()

    async def get(self) -> str:
        async with self._condition:
            while not self._items:
                await self._condition.wait()
            return self._items.popleft()


class ResponsePayloadError(RuntimeError):
    """Raised for malformed response payloads where retry is not useful."""


@dataclass(frozen=True)
class SchemeListItem:
    """Metadata for a single scheme from populate-scheme API."""

    scheme_id: str
    scheme_name: str
    mf_id: str


class AmfiClient:
    """Async AMFI NAV client with queue-based date-range fetching.

    This client fetches AMFI NAV history JSON from:
    `https://www.amfiindia.com/api/nav-history`
    using query parameters:
    - `query_type=all_for_date`
    - `from_date=YYYY-MM-DD`
    """

    base_url = "https://www.amfiindia.com/api/nav-history"
    default_parallel_requests = 5

    def __init__(
        self,
        *,
        parallel_requests: int | None = None,
        rate_limits: list[RateLimitRule] | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int | None = None,
        base_url: str | None = None,
        headers: dict[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize the AMFI async client.

        Args:
            parallel_requests: Number of worker tasks used for range fetches.
            rate_limits: List of rate-limit rules applied globally across workers.
            timeout_seconds: Per-request timeout.
            max_retries: Max retries per date on failure. `None` means unlimited.
            base_url: Optional override for AMFI API base URL.
            headers: Optional headers merged on top of defaults.
            client: Optional pre-built `httpx.AsyncClient` (mainly for testing).
        """

        self.parallel_requests = parallel_requests or self.default_parallel_requests
        if self.parallel_requests <= 0:
            raise AppConfigError(
                "parallel_requests", "POSITIVE_INTEGER", self.parallel_requests
            )

        self.timeout_seconds = timeout_seconds
        if self.timeout_seconds <= 0:
            raise AppConfigError(
                "timeout_seconds", "POSITIVE_FLOAT", self.timeout_seconds
            )

        if max_retries is not None and max_retries < 0:
            raise AppConfigError(
                "max_retries", "NON_NEGATIVE_INTEGER_OR_NONE", max_retries
            )

        self.max_retries = max_retries
        self._rate_limiter = MultiWindowRateLimiter(rate_limits)
        self.base_url = base_url or type(self).base_url
        self._owns_client = client is None
        self._client = client

        default_headers = {
            "Accept": "application/json",
            "Referer": "https://www.amfiindia.com/net-asset-value/nav-history",
            "User-Agent": "amfi-async-client/0.1",
        }
        self._headers = default_headers | (headers or {})

    async def __aenter__(self) -> AmfiClient:
        """Open a managed HTTP client when used as an async context manager."""

        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        """Close managed HTTP resources on context manager exit."""

        await self.aclose()

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout_seconds,
                headers=self._headers,
            )
        return self._client

    async def aclose(self) -> None:
        """Close the internal HTTP client if owned by this wrapper."""

        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    async def fetch_fund_house_details(self) -> list[RawFundHouseResponse]:
        """Fetch and parse mutual fund scheme details from AMFI website.

        Returns:
            List of mutual fund scheme details containing fields like mf_name,
            amc_name, etc.
        """
        LOGGER.info("FETCH_FUND_HOUSE_DETAILS_START")
        LOGGER.debug("FETCH_FUND_HOUSE_DETAILS: Acquiring rate limit")
        url = "https://www.amfiindia.com/otherdata/scheme-details"

        await self._rate_limiter.acquire()

        if self._client is None:
            raise HttpClientNotInitializedError()

        LOGGER.debug("FETCH_FUND_HOUSE_DETAILS: Sending HTTP GET to %s", url)
        try:
            response = await self._client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RequestExecutionError(
                f"Failed to fetch scheme details: {exc}"
            ) from exc

        content = response.text
        LOGGER.debug(
            "FETCH_FUND_HOUSE_DETAILS: Response content length=%d", len(content)
        )

        matches = re.findall(r'self\.__next_f\.push\(\[\d+,"(.*?)"\]\)', content)
        LOGGER.debug("FETCH_FUND_HOUSE_DETAILS: Found %d regex matches", len(matches))

        fund_houses: list[RawFundHouseResponse] = []

        for match_idx, match in enumerate(matches):
            if "mutualFunds" not in match:
                continue

            LOGGER.debug(
                "FETCH_FUND_HOUSE_DETAILS: Processing match %d with mutualFunds",
                match_idx,
            )
            # Remove 'c:' prefix if present
            payload = match[2:] if match.startswith("c:") else match

            # The payload is a JS string literal content with escaped quotes.
            # Wrap in quotes and load as JSON to unescape it.
            unescaped_json = json.loads(f'"{payload}"')

            # Now parse the actual JSON structure
            data = json.loads(unescaped_json)

            # Search for the object containing 'mutualFunds'
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "mutualFunds" in item:
                        fund_houses_resp = item["mutualFunds"]
                        if isinstance(fund_houses_resp, list):
                            LOGGER.debug(
                                "FETCH_FUND_HOUSE_DETAILS: Found %d fund houses",
                                len(fund_houses_resp),
                            )
                            for fund_house in fund_houses_resp:
                                fund_house = RawFundHouseResponse.from_dict(fund_house)
                                fund_houses.append(fund_house)
            LOGGER.info(
                "FETCH_FUND_HOUSE_DETAILS_SUCCESS. Parsed fund houses: %d.",
                len(fund_houses),
            )
            return fund_houses

        return fund_houses

    # async def fetch_schemes(
    #     self,
    #     fund_houses: list[RawFundHouseResponse],
    # ) -> tuple[
    #     list[RawSchemeResponse],
    #     list[RawSchemeDocumentResponse],
    #     list[RawSchemeAumResponse],
    # ]:
    #     if self._client is None:
    #         raise RuntimeError("HTTP client not initialized")

    #     LOGGER.info(
    #         "FETCH_SCHEMES_START: Processing %d fund houses", len(fund_houses)
    #     )

    #     # Step 1: Fetch scheme list for all fund houses
    #     scheme_list = await self._fetch_scheme_list(fund_houses)
    #     LOGGER.info(
    #         "FETCH_SCHEME_LIST_COMPLETE: Collected %d schemes", len(scheme_list)
    #     )

    #     # Step 2: Fetch scheme details
    #     raw_schemes = await self._fetch_scheme_details(scheme_list)
    #     LOGGER.info(
    #         "FETCH_SCHEME_DETAILS_COMPLETE: Fetched %d scheme details",
    #         len(raw_schemes),
    #     )

    #     # Step 3: Fetch scheme documents
    #     raw_scheme_documents = await self._fetch_scheme_documents(scheme_list)
    #     LOGGER.info(
    #         "FETCH_SCHEME_DOCUMENTS_COMPLETE: Fetched %d scheme documents",
    #         len(raw_scheme_documents),
    #     )

    #     # Step 4: Fetch scheme AUM
    #     raw_scheme_aum = await self._fetch_scheme_aum(scheme_list)
    #     LOGGER.info(
    #         "FETCH_SCHEME_AUM_COMPLETE: Fetched %d scheme AUM records",
    #         len(raw_scheme_aum),
    #     )

    #     return raw_schemes, raw_scheme_documents, raw_scheme_aum

    async def fetch_scheme_list(
        self, fund_houses: list[RawFundHouseResponse]
    ) -> list[SchemeListItem]:
        """Fetch scheme list for all fund houses with progress tracking."""
        LOGGER.info("FETCH_SCHEME_LIST_START. FUND_HOUSE_COUNT=%d.", len(fund_houses))

        if self._client is None:
            raise HttpClientNotInitializedError()

        scheme_list: list[SchemeListItem] = []

        progress = tqdm_async(
            fund_houses,
            desc="FETCH_SCHEME_LIST",
            unit=" fund_houses",
            dynamic_ncols=True,
            leave=True,
        )

        for fund_house in progress:
            mf_id = fund_house.mf_id
            progress.set_description(f"FETCH_SCHEME_LIST [MF_ID={mf_id}]")
            LOGGER.debug("FETCH_SCHEME_LIST. Processing MF_ID=%s", mf_id)

            await self._rate_limiter.acquire()

            LOGGER.debug("FETCH_SCHEME_LIST: HTTP GET populate-scheme MF_ID=%s", mf_id)

            scheme_list_resp = await self._client.get(
                "https://www.amfiindia.com/api/populate-scheme",
                params={"MF_ID": mf_id},
            )
            scheme_list_resp.raise_for_status()
            schemes_meta = scheme_list_resp.json()

            for scheme_meta in schemes_meta:
                scheme_id_value = scheme_meta["scheme_id"]
                scheme_name_value = scheme_meta["scheme_name"]

                scheme_list.append(
                    SchemeListItem(
                        scheme_id=str(scheme_id_value),
                        scheme_name=str(scheme_name_value),
                        mf_id=mf_id,
                    )
                )

            LOGGER.debug(
                "FETCH_SCHEME_LIST: MF_ID=%s yielded %d schemes",
                mf_id,
                len(schemes_meta),
            )

        LOGGER.info("FETCH_SCHEME_LIST_SUCCESS. SCHEME_COUNT=%d.", len(scheme_list))
        return scheme_list

    async def fetch_scheme_details(self, scheme: SchemeListItem) -> RawSchemeResponse:
        """Fetch scheme details for all schemes with progress tracking."""
        scheme_id = scheme.scheme_id
        mf_id = scheme.mf_id

        LOGGER.debug(
            "FETCH_SCHEME_DETAILS: FOUND_HOUSE_ID: %s, SCHEME_ID: %s",
            mf_id,
            scheme_id,
        )

        details_rows = await self._fetch_data_rows(
            "https://www.amfiindia.com/api/scheme-details",
            params={"MF_ID": mf_id, "scheme_id": scheme_id},
            context=f"scheme-details MF_ID={mf_id} scheme_id={scheme_id}",
        )

        LOGGER.debug(
            "FETCH_SCHEME_DETAILS: scheme_id=%s yielded %d rows",
            scheme_id,
            len(details_rows),
        )

        if len(details_rows) > 1:
            LOGGER.error(details_rows)
        return RawSchemeResponse.from_dict(details_rows[0])

    async def fetch_scheme_documents(
        self, scheme: SchemeListItem
    ) -> RawSchemeDocumentResponse:
        """Fetch scheme documents for a single scheme."""
        scheme_id = scheme.scheme_id

        LOGGER.debug(
            "FETCH_SCHEME_DOCUMENTS: Processing scheme_id=%s",
            scheme_id,
        )

        document_rows = await self._fetch_data_rows(
            f"https://www.amfiindia.com/api/schemes/{scheme_id}/documents",
            context=f"documents scheme_id={scheme_id}",
        )

        LOGGER.debug(
            "FETCH_SCHEME_DOCUMENTS: scheme_id=%s yielded %d rows",
            scheme_id,
            len(document_rows),
        )

        return RawSchemeDocumentResponse.from_dict(document_rows[0])

    async def fetch_scheme_aum(
        self, scheme: SchemeListItem
    ) -> list[RawSchemeAumResponse]:
        """Fetch scheme AUM for a single scheme."""
        scheme_id = scheme.scheme_id
        mf_id = scheme.mf_id

        LOGGER.debug(
            "FETCH_SCHEME_AUM: Processing scheme_id=%s",
            scheme_id,
        )

        aum_rows = await self._fetch_json_list(
            "https://www.amfiindia.com/api/scheme-data",
            params={
                "strMFId": mf_id,
                "strSDId": scheme_id,
                "strOption": "AUM",
            },
            context=f"aum MF_ID={mf_id} scheme_id={scheme_id}",
        )

        LOGGER.debug(
            "FETCH_SCHEME_AUM: scheme_id=%s yielded %d rows",
            scheme_id,
            len(aum_rows),
        )

        return [RawSchemeAumResponse.from_dict(row) for row in aum_rows]

    async def fetch_date(
        self, nav_date: DateLike
    ) -> tuple[list[RawNavPlanDetailsResponse], list[RawNavResponse]]:
        """Fetch NAV JSON for a single date.

        Args:
            nav_date: Date input as `date`, `datetime`, or ISO string.

        Returns:
            JSON response as a dictionary.
        """
        date_str = _date_key(nav_date)
        await self._rate_limiter.acquire()

        if self._client is None:
            raise HttpClientNotInitializedError()

        response = await self._client.get(
            self.base_url,
            params={"query_type": "all_for_date", "from_date": date_str},
        )
        response.raise_for_status()

        parsed = response.json()

        nav_fund_details = []
        navs = []
        for fund_house in parsed["data"]:
            fund_house_name = fund_house["mfName"]
            for scheme in fund_house.get("schemes", []):
                scheme_name = scheme["schemeName"]
                for nav in scheme.get("navs", []):
                    raw_nav_fund_detail = RawNavPlanDetailsResponse(
                        nav["SD_ID"], fund_house_name, scheme_name, nav["NAV_Name"]
                    )
                    nav_fund_details.append(raw_nav_fund_detail)
                    raw_nav = RawNavResponse.from_dict(nav)
                    navs.append(raw_nav)
        return nav_fund_details, navs

    async def _fetch_data_rows(
        self,
        url: str,
        *,
        context: str,
        params: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        LOGGER.debug("FETCH_DATA_ROWS: %s", context)
        payload = await self._fetch_json_list_or_data_object(
            url,
            params=params,
            context=context,
        )
        if not isinstance(payload, dict):
            LOGGER.debug("FETCH_DATA_ROWS: Unexpected payload type for %s", context)
            raise ResponsePayloadError(f"Unexpected object payload for {context}")

        data_rows = payload.get("data")
        if not isinstance(data_rows, list):
            LOGGER.debug("FETCH_DATA_ROWS: Missing/invalid data list for %s", context)
            raise ResponsePayloadError(f"Missing/invalid data list for {context}")
        if not all(isinstance(item, dict) for item in data_rows):
            LOGGER.debug("FETCH_DATA_ROWS: Non-object row for %s", context)
            raise ResponsePayloadError(f"Non-object data row received for {context}")
        LOGGER.debug("FETCH_DATA_ROWS: %s returned %d rows", context, len(data_rows))
        return data_rows

    async def _fetch_json_list(
        self,
        url: str,
        *,
        context: str,
        params: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        LOGGER.debug("FETCH_JSON_LIST: %s", context)
        payload = await self._fetch_json_list_or_data_object(
            url,
            params=params,
            context=context,
        )
        if not isinstance(payload, list):
            LOGGER.debug("FETCH_JSON_LIST: Expected list for %s", context)
            raise ResponsePayloadError(f"Expected list payload for {context}")
        if not all(isinstance(item, dict) for item in payload):
            LOGGER.debug("FETCH_JSON_LIST: Non-object row for %s", context)
            raise ResponsePayloadError(f"Non-object list row received for {context}")
        LOGGER.debug("FETCH_JSON_LIST: %s returned %d items", context, len(payload))
        return payload

    async def _fetch_json_list_or_data_object(
        self,
        url: str,
        *,
        context: str,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        if self._client is None:
            raise RuntimeError("HTTP client not initialized")

        LOGGER.debug("FETCH_JSON: Acquiring rate limit for %s", context)
        await self._rate_limiter.acquire()
        LOGGER.debug("FETCH_JSON: HTTP GET %s params=%s", url, params)
        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
            LOGGER.debug("FETCH_JSON: %s status=%d", context, response.status_code)
        except (httpx.HTTPError, ValueError) as exc:
            LOGGER.debug("FETCH_JSON: Failed for %s: %s", context, exc)
            raise RequestExecutionError(f"Failed to fetch {context}: {exc}") from exc

        if not isinstance(payload, (dict, list)):
            LOGGER.debug("FETCH_JSON: Unexpected payload type for %s", context)
            raise ResponsePayloadError(f"Unexpected payload type for {context}")
        return payload
