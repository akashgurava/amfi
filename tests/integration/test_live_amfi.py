"""Live integration tests that call the public AMFI API.

These tests are skipped by default. Set ``AMFI_RUN_LIVE_TESTS=1`` to run them.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from amfi import AmfiClient, App, Database, RateLimitRule


def _live_skip() -> None:
    if os.getenv("AMFI_RUN_LIVE_TESTS") != "1":
        pytest.skip("Set AMFI_RUN_LIVE_TESTS=1 to run live integration tests")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_fetch_date_returns_plan_details_and_navs() -> None:
    _live_skip()

    async with AmfiClient(
        parallel_requests=1,
        rate_limits=[RateLimitRule.per_seconds(1, 1)],
        max_retries=1,
    ) as client:
        plan_details, navs = await client.fetch_date("2024-01-02")

    assert isinstance(plan_details, list)
    assert isinstance(navs, list)
    assert plan_details, "expected at least one plan detail row"
    assert navs, "expected at least one NAV row"
    assert plan_details[0].sd_id
    assert navs[0].sd_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_fetch_fund_house_details_returns_houses() -> None:
    _live_skip()

    async with AmfiClient(
        parallel_requests=1,
        rate_limits=[RateLimitRule.per_seconds(1, 1)],
    ) as client:
        fund_houses = await client.fetch_fund_house_details()

    assert fund_houses, "expected non-empty fund-house list"
    assert all(fh.mf_id.isdigit() for fh in fund_houses)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_app_save_nav_single_date_end_to_end(tmp_path: Path) -> None:
    _live_skip()

    db = Database(db_path=str(tmp_path / "live.duckdb"))
    client = AmfiClient(
        parallel_requests=1,
        rate_limits=[RateLimitRule.per_seconds(1, 1)],
        max_retries=1,
    )
    app = App(client=client, db=db)
    app.init_db()

    await app.save_nav(force="2024-01-02")

    row = db.conn.execute("SELECT COUNT(*) FROM raw_nav").fetchone()
    assert row is not None and row[0] > 0
