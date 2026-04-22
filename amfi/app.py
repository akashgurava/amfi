from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from .client import AmfiClient, SchemeListItem
from .data import (
    RawFundHouseResponse,
    RawScheme,
    RawSchemeAum,
    RawSchemeDocument,
    RawTable,
)
from .db import Database
from .utility import ParallelRunner, WriteJob, WriteQueue
from .utils import LOGGER

BASE_START_DATE = date(2010, 1, 1)


def _log_failures_by_type(
    label: str,
    failed_by_type: dict[str, list[str]],
    max_ids: int = 5,
) -> None:
    """Log one WARNING line per exception type, each with up to max_ids sample IDs."""
    for exc_type, ids in sorted(failed_by_type.items()):
        LOGGER.warning("%s %s: %s", label, exc_type, ids[:max_ids])


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - timedelta(days=1)).day


def _expand_force_token(token: str, today: date) -> list[date]:
    parts = token.split("-")

    if len(parts) == 1:
        year_str = parts[0]
        if len(year_str) != 4 or not year_str.isdigit():
            raise ValueError(f"Invalid force token: {token!r}")

        year = int(year_str)
        start = date(year, 1, 1)
        end = date(year, 12, 31)

    elif len(parts) == 2:
        year_str, month_str = parts
        if (
            len(year_str) != 4
            or not year_str.isdigit()
            or len(month_str) != 2
            or not month_str.isdigit()
        ):
            raise ValueError(f"Invalid force token: {token!r}")

        year = int(year_str)
        month = int(month_str)
        if month < 1 or month > 12:
            raise ValueError(f"Invalid month in force token: {token!r}")

        start = date(year, month, 1)
        end = date(year, month, _days_in_month(year, month))

    elif len(parts) == 3:
        year_str, month_str, day_str = parts
        if (
            len(year_str) != 4
            or not year_str.isdigit()
            or len(month_str) != 2
            or not month_str.isdigit()
            or len(day_str) != 2
            or not day_str.isdigit()
        ):
            raise ValueError(f"Invalid force token: {token!r}")

        try:
            selected = date(int(year_str), int(month_str), int(day_str))
        except ValueError as exc:
            raise ValueError(f"Invalid date in force token: {token!r}") from exc

        return [selected] if selected <= today else []

    else:
        raise ValueError(f"Invalid force token: {token!r}")

    cap_end = min(end, today)
    if cap_end < start:
        return []

    day_count = (cap_end - start).days + 1
    return [start + timedelta(days=i) for i in range(day_count)]


def parse_force_dates(force: str, *, today: date | None = None) -> list[date]:
    """Parse and expand force selectors into a sorted unique date list.

    Supported tokens (comma-separated):
    - `YYYY`
    - `YYYY-MM`
    - `YYYY-MM-DD`
    """
    today = today or date.today()
    if today <= BASE_START_DATE:
        raise ValueError("Current date must be after base start date")

    tokens = [token.strip() for token in force.split(",")]
    if not tokens or any(not token for token in tokens):
        raise ValueError("--force must be a comma-separated list of date selectors")

    selected_dates: set[date] = set()
    for token in tokens:
        for selected_date in _expand_force_token(token, today):
            if selected_date >= BASE_START_DATE:
                selected_dates.add(selected_date)

    if not selected_dates:
        raise ValueError("--force selectors do not include any valid date")

    return sorted(selected_dates)


class App:
    def __init__(self, client: AmfiClient | None = None, db: Database | None = None):
        self.client = client or AmfiClient()
        self.db = db or Database(db_path="amfi.db")

    def init_db(self) -> None:
        self.db.create_raw()
        self.db.create_views()

    async def _run_stage(
        self,
        *,
        label: str,
        scheme_list: list[SchemeListItem],
        table: type[RawTable[Any]],
        fetcher: Callable[[AmfiClient, SchemeListItem], Any],
        row_builder: Callable[[Any], list[Any]],
    ) -> None:
        existing_ids = set(self.db.get_existing_raw_table_ids(table))
        pending_schemes = [
            scheme for scheme in scheme_list if scheme.scheme_id not in existing_ids
        ]
        LOGGER.info(
            "%s_FILTERED. EXISTING=%d PENDING=%d.",
            label,
            len(existing_ids),
            len(pending_schemes),
        )

        if not pending_schemes:
            LOGGER.info("%s_SKIP. No pending schemes.", label)
            return

        async with self.client as client:
            writer = WriteQueue(self.db, label=label)
            await writer.start()

            async def process_scheme(scheme: SchemeListItem) -> None:
                payload = await fetcher(client, scheme)
                rows = row_builder(payload)
                for row in rows:
                    await writer.put(
                        WriteJob(
                            table=table,
                            row=row,
                            item_id=scheme.scheme_id,
                        )
                    )

            runner = ParallelRunner[SchemeListItem](
                label=label,
                unit="sch",
                concurrency=client.parallel_requests,
            )

            try:
                failed_fetch_ids = await runner.run(
                    items=pending_schemes,
                    id_getter=lambda scheme: scheme.scheme_id,
                    worker=process_scheme,
                )
            finally:
                await writer.stop()

        failed_write_ids = writer.failed_ids
        failed_ids = failed_fetch_ids | failed_write_ids
        success_count = len(pending_schemes) - len(failed_ids)

        LOGGER.info(
            (
                "%s_SUMMARY. TOTAL=%d PENDING=%d SUCCESS=%d "
                "FAILED_FETCH=%d FAILED_WRITE=%d"
            ),
            label,
            len(scheme_list),
            len(pending_schemes),
            success_count,
            len(failed_fetch_ids),
            len(failed_write_ids),
        )
        if failed_fetch_ids:
            _log_failures_by_type(f"{label}_FAILED_FETCH", runner.failed_by_type)
        if failed_write_ids:
            _log_failures_by_type(f"{label}_FAILED_WRITE", writer.failed_by_type)

    async def save_fund_houses(self) -> list[RawFundHouseResponse]:
        """Save fund house data to database."""
        LOGGER.info("SAVE_FUND_HOUSES_START")

        async with self.client as client:
            fund_houses = await client.fetch_fund_house_details()
        self.db.insert_fund_houses(fund_houses)

        LOGGER.info("SAVE_FUND_HOUSES_SUCCESS. FUND_HOUSE_COUNT=%d.", len(fund_houses))
        return fund_houses

    async def save_fund_schemes(self, scheme_list: list[SchemeListItem]) -> None:
        """Save fund schemes data to database."""
        LOGGER.info("SAVE_FUND_SCHEMES_START. SCHEME_COUNT=%d.", len(scheme_list))

        await self._run_stage(
            label="SAVE_FUND_SCHEMES",
            scheme_list=scheme_list,
            table=RawScheme,
            fetcher=lambda client, scheme: client.fetch_scheme_details(scheme),
            row_builder=lambda payload: [payload],
        )

        LOGGER.info("SAVE_FUND_SCHEMES_SUCCESS")

    async def save_fund_documents(self, scheme_list: list[SchemeListItem]) -> None:
        """Save fund documents data to database."""
        LOGGER.info("SAVE_FUND_DOCUMENTS_START. SCHEME_COUNT=%d.", len(scheme_list))

        await self._run_stage(
            label="SAVE_FUND_DOCUMENTS",
            scheme_list=scheme_list,
            table=RawSchemeDocument,
            fetcher=lambda client, scheme: client.fetch_scheme_documents(scheme),
            row_builder=lambda payload: [payload],
        )

        LOGGER.info("SAVE_FUND_DOCUMENTS_SUCCESS")

    async def save_fund_aum(self, scheme_list: list[SchemeListItem]) -> None:
        """Save fund AUM data to database."""
        LOGGER.info("SAVE_FUND_AUM_START. SCHEME_COUNT=%d.", len(scheme_list))

        await self._run_stage(
            label="SAVE_FUND_AUM",
            scheme_list=scheme_list,
            table=RawSchemeAum,
            fetcher=lambda client, scheme: client.fetch_scheme_aum(scheme),
            row_builder=lambda payload: payload,
        )

        LOGGER.info("SAVE_FUND_AUM_SUCCESS")

    async def save_all_fund_details(
        self, fund_houses: list[RawFundHouseResponse]
    ) -> None:
        """Save all fund details (schemes, documents, AUM) to database."""
        LOGGER.info(
            "SAVE_ALL_FUND_DETAILS_START. FUND_HOUSE_COUNT=%d.", len(fund_houses)
        )

        async with self.client as client:
            scheme_list = await client.fetch_scheme_list(fund_houses)

        await self.save_fund_schemes(scheme_list)
        await self.save_fund_documents(scheme_list)
        await self.save_fund_aum(scheme_list)

        LOGGER.info("SAVE_ALL_FUND_DETAILS_SUCCESS.")

    async def save_fund_details(self) -> None:
        """Save all fund details starting from fund houses."""
        LOGGER.info("SAVE_FUND_DETAILS_START")

        fund_houses = await self.save_fund_houses()
        await self.save_all_fund_details(fund_houses)

        LOGGER.info("SAVE_FUND_DETAILS_SUCCESS")

    async def save_nav(self, fetch_all: bool = False, force: str | None = None) -> None:
        """Save NAV data to the database.

        Fetches daily NAV data in parallel across dates and persists two datasets:

        - ``raw_nav``: all NAV rows for the date (bulk appended, no deduplication).
        - ``raw_nav_plan_details``: scheme/plan metadata keyed by ``sd_id``
          (inserted with ``ON CONFLICT DO NOTHING``, so re-runs are safe).

        Args:
            fetch_all: When ``True``, fetch every date from ``BASE_START_DATE``
                       through today, including dates already present in the database.
                       Ignored when ``force`` is provided.
            force: Comma-separated date selectors, e.g. ``"2024"``, ``"2024-01"``,
                   ``"2024-01-15"``.  Expands to an explicit list of dates and
                   overrides ``fetch_all``.
        """
        LOGGER.info("SAVE_NAV_START")

        if force is not None:
            nav_dates = parse_force_dates(force)
            LOGGER.info(
                "SAVE_NAV_FORCE. SELECTOR=%r DATE_COUNT=%d", force, len(nav_dates)
            )
        elif fetch_all:
            day_count = (date.today() - BASE_START_DATE).days + 1
            nav_dates = [BASE_START_DATE + timedelta(days=i) for i in range(day_count)]
            LOGGER.info("SAVE_NAV_ALL. DATE_COUNT=%d", len(nav_dates))
        else:
            nav_dates = sorted(self.db.get_missing_nav_dates())
            LOGGER.info("SAVE_NAV_MISSING. DATE_COUNT=%d", len(nav_dates))

        if not nav_dates:
            LOGGER.info("SAVE_NAV_SKIP. No dates to fetch.")
            return

        async with self.client as client:

            async def process_date(nav_date: date) -> None:
                plan_details, navs = await client.fetch_date(nav_date)
                self.db.insert_or_ignore_nav_plan_details(plan_details)
                self.db.bulk_insert_nav(navs)

            runner = ParallelRunner[date](
                label="SAVE_NAV",
                unit="date",
                concurrency=client.parallel_requests,
            )
            failed_ids = await runner.run(
                items=nav_dates,
                id_getter=lambda d: d.isoformat(),
                worker=process_date,
            )

        success_count = len(nav_dates) - len(failed_ids)
        LOGGER.info(
            "SAVE_NAV_SUMMARY. TOTAL=%d SUCCESS=%d FAILED=%d",
            len(nav_dates),
            success_count,
            len(failed_ids),
        )
        if failed_ids:
            _log_failures_by_type("SAVE_NAV_FAILED", runner.failed_by_type)

        LOGGER.info("SAVE_NAV_SUCCESS")
