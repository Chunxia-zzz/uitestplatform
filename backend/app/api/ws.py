"""WebSocket：执行事件推送（M3.1 / FR36）。

    /ws/executions/{execution_id}

服务端只推不读；终态事件后关闭。单进程语义（FR40）。
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.event_bus import bus

logger = logging.getLogger(__name__)

router = APIRouter()

_TERMINAL_EVENTS = {"execution.finished", "execution.cancelled"}
_IDLE_TIMEOUT_S = 60


@router.websocket("/ws/executions/{execution_id}")
async def execution_stream(websocket: WebSocket, execution_id: int) -> None:
    await websocket.accept()
    queue = bus.subscribe(execution_id)
    try:
        await websocket.send_json(
            {"event": "subscribed", "payload": {"execution_id": execution_id}})
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=_IDLE_TIMEOUT_S)
            except TimeoutError:
                await websocket.send_json({"event": "ping", "payload": {}})
                continue
            await websocket.send_json(message)
            if message.get("event") in _TERMINAL_EVENTS:
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.warning("ws stream error for execution %s", execution_id, exc_info=True)
    finally:
        bus.unsubscribe(execution_id, queue)
        try:
            await websocket.close()
        except Exception:
            pass
