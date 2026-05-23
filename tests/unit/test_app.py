from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from amfi.app import BASE_START_DATE, App, parse_force_dates
from amfi.client import AmfiClient
from amfi.data import RawNavPlanDetailsResponse, RawNavResponse

# ---------------------------------------------------------------------------
# parse_force_dates
# ---------------------------------------------------------------------------


def test_parse_force_year_selector_capped_before_today() -> None:
    selected = parse_force_dates("2026", today=date(2026, 4, 10))
    assert selected[0] == date(2026, 1, 1)
    assert selected[-1] == date(2026, 4, 10)
    assert len(selected) == 100


def test_parse_force_month_selector_capped_before_today() -> None:
    selected = parse_force_dates("2026-02", today=date(2026, 2, 3))
    assert selected == [date(2026, 2, 1), date(2026, 2, 2), date(2026, 2, 3)]


def test_parse_force_day_selector() -> None:
    selected = parse_force_dates("2026-02-01", today=date(2026, 2, 10))
    assert selected == [date(2026, 2, 1)]


def test_parse_force_mixed_selectors_sorted_and_unique() -> None:
    selected = parse_force_dates(
        "2025,2026-02,2024-01-02,2026-02-01", today=date(2026, 3, 1)
    )
    assert selected[0] == date(2024, 1, 2)
    assert selected[1] == date(2025, 1, 1)
    assert selected[-1] == date(2026, 2, 28)
    assert selected.count(date(2026, 2, 1)) == 1


def test_parse_force_excludes_dates_before_base_start() -> None:
    selected = parse_force_dates("2009,2010-01", today=date(2010, 1, 3))
    assert selected == [BASE_START_DATE, date(2010, 1, 2), date(2010, 1, 3)]


def test_parse_force_future_only_raises() -> None:
    with pytest.raises(ValueError, match="do not include any valid date"):
        parse_force_dates("2026-01-11", today=date(2026, 1, 10))


def test_parse_force_invalid_tokens_raise() -> None:
    with pytest.raises(ValueError, match="Invalid force token"):
        parse_force_dates("2026-1", today=date(2026, 2, 1))
    with pytest.raises(ValueError, match="Invalid date in force token"):
        parse_force_dates("2026-02-30", today=date(2026, 3, 1))
    with pytest.raises(ValueError, match="comma-separated list"):
        parse_force_dates("2026,,2026-01", today=date(2026, 3, 1))


# ---------------------------------------------------------------------------
# App.save_nav
# ---------------------------------------------------------------------------


def _fake_fetch_date_factory(calls: list[date]) -> object:
    async def fetch_date(nav_date: date) -> tuple[list, list]:  # type: ignore[type-arg]
        calls.append(nav_date)
        plan_details = [
            RawNavPlanDetailsResponse(sd_id="1", fund_house="FH", scheme="S", plan="P")
        ]
        navs = [
            RawNavResponse.from_dict(
                {
                    "SD_ID": "1",
                    "NAV_Name": "P",
                    "hNAV_Amt": "10",
                    "ISIN_RI": "",
                    "ISIN_PO": "",
                    "hNAV_Date": nav_date.isoformat(),
                    "hNAV_Dtstamp": "",
                    "hNAV_reissue": "",
                    "hNAV_repurchase": "",
                    "hNAV_Upload_display": "",
                }
            )
        ]
        return plan_details, navs

    return fetch_date


def _mock_app() -> tuple[App, MagicMock, MagicMock]:
    client = MagicMock(spec=AmfiClient)
    client.parallel_requests = 2
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    db = MagicMock()
    db.insert_or_ignore_nav_plan_details = MagicMock()
    db.bulk_insert_nav = MagicMock()

    return App(client=client, db=db), client, db


@pytest.mark.asyncio
async def test_save_nav_with_force_selector_fetches_only_requested_dates() -> None:
    app, client, db = _mock_app()
    calls: list[date] = []
    client.fetch_date = AsyncMock(side_effect=_fake_fetch_date_factory(calls))

    await app.save_nav(force="2024-01-01")

    assert calls == [date(2024, 1, 1)]
    assert db.insert_or_ignore_nav_plan_details.call_count == 1
    assert db.bulk_insert_nav.call_count == 1


@pytest.mark.asyncio
async def test_save_nav_missing_uses_db_get_missing_nav_dates() -> None:
    app, client, db = _mock_app()
    db.get_missing_nav_dates = MagicMock(
        return_value={date(2024, 1, 1), date(2024, 1, 2)}
    )
    calls: list[date] = []
    client.fetch_date = AsyncMock(side_effect=_fake_fetch_date_factory(calls))

    await app.save_nav()

    assert sorted(calls) == [date(2024, 1, 1), date(2024, 1, 2)]


@pytest.mark.asyncio
async def test_save_nav_skips_when_no_dates_to_fetch() -> None:
    app, client, db = _mock_app()
    db.get_missing_nav_dates = MagicMock(return_value=set())
    client.fetch_date = AsyncMock()

    await app.save_nav()

    client.fetch_date.assert_not_called()
    db.bulk_insert_nav.assert_not_called()


def test_init_db_creates_database_objects() -> None:
    client = MagicMock(spec=AmfiClient)
    db = MagicMock()
    App(client=client, db=db).init_db()
    db.create_database_objects.assert_called_once()
