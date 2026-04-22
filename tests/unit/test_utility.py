from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from amfi.data import RawFundHouse, RawFundHouseResponse
from amfi.db import Database
from amfi.utility import ParallelRunner, WriteJob, WriteQueue


def _fund_house(mf_id: str) -> RawFundHouseResponse:
    return RawFundHouseResponse.from_dict(
        {"mf_id": mf_id, "mf_name": f"MF {mf_id}", "amc_name": "AMC"}
    )


@pytest.mark.asyncio
async def test_parallel_runner_runs_all_items_and_records_no_failures() -> None:
    processed: list[int] = []

    async def worker(item: int) -> None:
        await asyncio.sleep(0)
        processed.append(item)

    runner = ParallelRunner[int](label="T", unit="i", concurrency=2)
    failed = await runner.run(items=[1, 2, 3], id_getter=str, worker=worker)
    assert failed == set()
    assert sorted(processed) == [1, 2, 3]
    assert runner.failed_by_type == {}


@pytest.mark.asyncio
async def test_parallel_runner_collects_failures_by_exception_type() -> None:
    async def worker(item: int) -> None:
        if item == 2:
            raise ValueError("boom")
        if item == 3:
            raise RuntimeError("boom")

    runner = ParallelRunner[int](label="T", unit="i", concurrency=3)
    failed = await runner.run(items=[1, 2, 3], id_getter=str, worker=worker)

    assert failed == {"2", "3"}
    assert runner.failed_by_type == {"ValueError": ["2"], "RuntimeError": ["3"]}


@pytest.mark.asyncio
async def test_parallel_runner_enforces_concurrency_limit() -> None:
    active = 0
    max_active = 0

    async def worker(item: int) -> None:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1

    runner = ParallelRunner[int](label="T", unit="i", concurrency=2)
    await runner.run(items=list(range(5)), id_getter=str, worker=worker)

    assert max_active <= 2


@pytest.mark.asyncio
async def test_write_queue_persists_jobs_and_tracks_success(tmp_path: Path) -> None:
    db = Database(db_path=str(tmp_path / "wq.duckdb"))
    db.create_raw()

    queue = WriteQueue(db, label="TEST")
    await queue.start()
    await queue.put(WriteJob(table=RawFundHouse, row=_fund_house("1"), item_id="1"))
    await queue.put(WriteJob(table=RawFundHouse, row=_fund_house("2"), item_id="2"))
    await queue.stop()

    assert queue.success_count == 2
    assert queue.failed_count == 0
    assert queue.failed_ids == set()


@pytest.mark.asyncio
async def test_write_queue_records_failures_per_item(tmp_path: Path) -> None:
    db = Database(db_path=str(tmp_path / "wq.duckdb"))
    db.create_raw()

    # Pass a non-dataclass row so `insert` raises TypeError.
    bad_job = WriteJob(table=RawFundHouse, row="not-a-dataclass", item_id="bad")

    queue = WriteQueue(db, label="TEST")
    await queue.start()
    await queue.put(bad_job)
    await queue.stop()

    assert queue.failed_count == 1
    assert queue.failed_ids == {"bad"}
    assert "TypeError" in queue.failed_by_type
