"""进程内事件总线 + 事件持久化（M3.1 / FR36–FR37）。

单进程语义（FR40）：WS 与队列只在同进程内有效；换多 worker 时这里要改成 Redis pub/sub。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import defaultdict
from datetime import datetime
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

#: 每个订阅者队列上限；满了丢最旧（慢客户端不应拖慢执行）
_SUB_QUEUE_SIZE = 200


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[int, set[asyncio.Queue]] = defaultdict(set)
        self.dropped = 0

    def subscribe(self, execution_id: int) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=_SUB_QUEUE_SIZE)
        self._subscribers[execution_id].add(queue)
        return queue

    def unsubscribe(self, execution_id: int, queue: asyncio.Queue) -> None:
        subscribers = self._subscribers.get(execution_id)
        if not subscribers:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(execution_id, None)

    def publish(self, execution_id: int, event: str, payload: dict[str, Any]) -> None:
        message = {
            "event": event,
            "payload": payload,
            "ts": datetime.now().isoformat(timespec="milliseconds"),
        }
        for queue in list(self._subscribers.get(execution_id, ())):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                # 丢最旧，保最新 —— 最终状态还能通过 GET 补齐
                try:
                    queue.get_nowait()
                    queue.put_nowait(message)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass
                self.dropped += 1


bus = EventBus()


class ExecutionEvents:
    """一次执行的事件出口：广播 + 写 JSONL（WS 断开后可回放）。"""

    def __init__(self, execution_id: int) -> None:
        self.execution_id = execution_id
        self.path = os.path.join(settings.event_log_dir, f"execution-{execution_id}.jsonl")
        os.makedirs(settings.event_log_dir, exist_ok=True)

    def emit(self, event: str, **payload: Any) -> None:
        bus.publish(self.execution_id, event, payload)
        record = {
            "ts": datetime.now().isoformat(timespec="milliseconds"),
            "event": event,
            "payload": payload,
        }
        try:
            with open(self.path, "a", encoding="utf-8") as fp:
                fp.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            logger.warning("event log write failed: %s", self.path, exc_info=True)
