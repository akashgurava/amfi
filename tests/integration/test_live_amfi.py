from __future__ import annotations

import os

import pytest

from amfi import AmfiClient, RateLimitRule


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_fetch_date_2010_01_01() -> None:
    if os.getenv("AMFI_RUN_LIVE_TESTS") != "1":
        pytest.skip("Set AMFI_RUN_LIVE_TESTS=1 to run live integration tests")

    async with AmfiClient(
        parallel_requests=1,
        rate_limits=[RateLimitRule.per_seconds(1, 1)],
        max_retries=1,
    ) as client:
        payload = await client.fetch_date("2010-01-01")

    assert isinstance(payload, dict)
    assert "data" in payload
    assert isinstance(payload["data"], list)
