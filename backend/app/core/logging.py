"""结构化日志（单行 JSON）与 trace_id 中间件。

M1 §2.8 冻结字段：ts / level / logger / trace_id / execution_id / case_id / step_seq /
event / payload。
"""
from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")

_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message", "asctime", "taskName",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "trace_id": getattr(record, "trace_id", trace_id_var.get("")),
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())


class TraceMiddleware(BaseHTTPMiddleware):
    """每个请求一个 trace_id；回写响应头，错误体里也带。"""

    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("x-trace-id") or uuid.uuid4().hex
        trace_id_var.set(trace_id)
        request.state.trace_id = trace_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logging.getLogger("app.http").exception(
                "request failed", extra={"path": request.url.path, "method": request.method}
            )
            raise
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        response.headers["x-trace-id"] = trace_id
        logging.getLogger("app.http").info(
            "request", extra={
                "event": "http.request", "method": request.method,
                "path": request.url.path, "status": response.status_code,
                "duration_ms": elapsed_ms,
            },
        )
        return response


def log_event(event: str, payload: dict[str, Any] | None = None,
              level: int = logging.INFO) -> None:
    logging.getLogger("app.event").log(
        level, event, extra={"event": event, "payload": payload or {}})
