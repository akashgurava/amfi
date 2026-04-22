from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from tqdm.asyncio import tqdm as tqdm_async

from .data import RawTable
from .db import Database
from .utils import LOGGER

TItem = TypeVar("TItem")


class ParallelRunner(Generic[TItem]):
    def __init__(
        self,
        *,
        label: str,
        unit: str,
        concurrency: int,
    ) -> None:
        self.label = label
        self.unit = unit
        self.concurrency = concurrency
        self.failed_by_type: dict[str, list[str]] = {}

    async def run(
        self,
        *,
        items: list[TItem],
        id_getter: Callable[[TItem], str],
        worker: Callable[[TItem], Awaitable[None]],
    ) -> set[str]:
        self.failed_by_type = {}
        failed_ids: set[str] = set()

        progress = tqdm_async(
            total=len(items),
            desc=self.label,
            unit=self.unit,
            dynamic_ncols=True,
            leave=True,
            bar_format=(
                "{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{postfix}]"
            ),
        )
        progress.set_postfix(active=0, success=0, fail=0, refresh=False)

        semaphore = asyncio.Semaphore(self.concurrency)
        active_count = 0
        success_count = 0
        fail_count = 0
        lock = asyncio.Lock()

        async def _task(item: TItem) -> None:
            nonlocal active_count, success_count, fail_count
            item_id = id_getter(item)
            async with semaphore:
                async with lock:
                    active_count += 1
                    progress.set_postfix(
                        active=active_count,
                        success=success_count,
                        fail=fail_count,
                        refresh=True,
                    )

                try:
                    await worker(item)
                    async with lock:
                        success_count += 1
                except Exception as exc:
                    failed_ids.add(item_id)
                    exc_type = type(exc).__name__
                    async with lock:
                        fail_count += 1
                        self.failed_by_type.setdefault(exc_type, []).append(item_id)
                    LOGGER.debug(
                        "%s_FETCH_ERROR. ITEM_ID=%s ERROR=%s",
                        self.label,
                        item_id,
                        exc,
                    )
                finally:
                    async with lock:
                        active_count -= 1
                        progress.set_postfix(
                            active=active_count,
                            success=success_count,
                            fail=fail_count,
                            refresh=False,
                        )
                        progress.update(1)

        tasks = [asyncio.create_task(_task(item)) for item in items]
        try:
            await asyncio.gather(*tasks)
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        finally:
            progress.close()

        return failed_ids


@dataclass(frozen=True)
class WriteJob:
    table: type[RawTable[Any]]
    row: Any
    item_id: str


class WriteQueue:
    def __init__(self, db: Database, *, label: str) -> None:
        self._db = db
        self._label = label
        self._queue: asyncio.Queue[WriteJob | None] = asyncio.Queue()
        self._consumer_task: asyncio.Task[None] | None = None
        self.failed_ids: set[str] = set()
        self.failed_by_type: dict[str, list[str]] = {}
        self.failed_count = 0
        self.success_count = 0

    async def start(self) -> None:
        if self._consumer_task is None:
            self._consumer_task = asyncio.create_task(self._consume())

    async def put(self, job: WriteJob) -> None:
        await self._queue.put(job)

    async def stop(self) -> None:
        await self._queue.put(None)
        if self._consumer_task is not None:
            await self._consumer_task
            self._consumer_task = None

    async def _consume(self) -> None:
        while True:
            item = await self._queue.get()
            if item is None:
                self._queue.task_done()
                return

            job: WriteJob = item
            try:
                self._db.insert(job.table, job.row)
                self.success_count += 1
            except Exception as exc:
                self.failed_count += 1
                self.failed_ids.add(job.item_id)
                exc_type = type(exc).__name__
                self.failed_by_type.setdefault(exc_type, []).append(job.item_id)
                LOGGER.debug(
                    "%s_WRITE_ERROR. ITEM_ID=%s TABLE=%s ERROR=%s",
                    self._label,
                    job.item_id,
                    job.table.name(),
                    exc,
                )
            finally:
                self._queue.task_done()
