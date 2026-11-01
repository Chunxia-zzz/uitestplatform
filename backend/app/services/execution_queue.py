"""执行队列（M3.1 / D23 / FR30）。

进程内 FIFO + 固定 worker + 信号量限流。**单进程语义**（FR40）：
* 重启会丢队列 → 由 ``execution_service.reconcile_orphans()`` 把残留置 ERROR
* WS / 事件总线也只在同进程内有效
"""
from __future__ import annotations

import asyncio
import logging

from app.core.config import settings
from app.core.errors import QueueFull

logger = logging.getLogger(__name__)


class ExecutionQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[int] = asyncio.Queue(maxsize=settings.max_pending)
        self._workers: list[asyncio.Task] = []
        self._sem = asyncio.Semaphore(settings.max_concurrent_executions)
        self._closing = False

    async def start(self) -> None:
        self._closing = False
        for index in range(settings.max_concurrent_executions):
            task = asyncio.create_task(self._worker(index), name=f"exec-worker-{index}")
            self._workers.append(task)
        logger.info("execution queue started", extra={
            "event": "queue.start",
            "workers": settings.max_concurrent_executions,
            "max_pending": settings.max_pending,
        })

    async def stop(self) -> None:
        self._closing = True
        for task in self._workers:
            task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("execution queue stopped", extra={"event": "queue.stop"})

    async def submit(self, execution_id: int) -> None:
        try:
            self._queue.put_nowait(execution_id)
        except asyncio.QueueFull as exc:
            raise QueueFull(
                "执行队列已满，请稍后重试",
                {"max_pending": settings.max_pending,
                 "concurrency": settings.max_concurrent_executions},
            ) from exc

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    @property
    def running_workers(self) -> int:
        return len([t for t in self._workers if not t.done()])

    async def _worker(self, index: int) -> None:
        from app.services.execution_service import execute

        while not self._closing:
            execution_id = await self._queue.get()
            try:
                async with self._sem:          # 双保险：worker 数 == 上限时恒为 1
                    await execute(execution_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("worker %s failed on execution %s", index, execution_id)
            finally:
                self._queue.task_done()


execution_queue = ExecutionQueue()
