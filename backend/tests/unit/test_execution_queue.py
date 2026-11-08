"""执行队列：FIFO / 并发上限 / 队列满（M3.1 V3）。"""
from __future__ import annotations

import asyncio

import pytest

from app.core.config import settings
from app.services.execution_queue import ExecutionQueue


@pytest.mark.asyncio
async def test_fifo_and_concurrency_limit(monkeypatch):
    monkeypatch.setattr(settings, "max_concurrent_executions", 2)
    monkeypatch.setattr(settings, "max_pending", 10)

    seen: list[int] = []
    running = {"now": 0, "max": 0}

    async def fake_execute(execution_id: int) -> None:
        running["now"] += 1
        running["max"] = max(running["max"], running["now"])
        seen.append(execution_id)
        await asyncio.sleep(0.05)
        running["now"] -= 1

    monkeypatch.setattr("app.services.execution_service.execute", fake_execute)
    # 队列 worker 是 `from ... import execute`，在 worker 启动时绑定 → 需在 start 前替换

    queue = ExecutionQueue()
    await queue.start()
    try:
        for execution_id in (1, 2, 3, 4):
            await queue.submit(execution_id)
        await asyncio.wait_for(queue._queue.join(), timeout=5)
    finally:
        await queue.stop()

    assert seen == [1, 2, 3, 4], "FIFO 顺序被破坏"
    assert running["max"] <= 2, f"并发超过上限：{running['max']}"


@pytest.mark.asyncio
async def test_queue_full_raises(monkeypatch):
    monkeypatch.setattr(settings, "max_pending", 1)
    monkeypatch.setattr(settings, "max_concurrent_executions", 1)
    queue = ExecutionQueue()          # 不启动 worker，让队列保持满
    await queue.submit(1)
    with pytest.raises(Exception) as exc:
        await queue.submit(2)
    assert exc.value.code == "QUEUE_FULL"
