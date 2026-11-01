"""SessionManager —— **非单例**（M1 FR8）。

为什么不能是单例：二期的 WebView 场景需要在**同一个 execution 内同时持有**
Appium（主）与 Playwright（次）两个 adapter，用上下文栈切换。若全局单例持有单个
adapter，这个能力直接做不出来，属架构级返工。

M2 的验证器也依赖多实例能力：验证要在独立会话里跑，绝不能干扰正在执行的用例。
"""
from __future__ import annotations

import logging

from app.engines.base import EngineAdapter, SessionConfig

logger = logging.getLogger(__name__)


class SessionManager:
    """一次 execution / 一次验证持有一个实例，内部按引擎 key 管理多个 adapter。"""

    def __init__(self, registry) -> None:
        self._registry = registry
        self._adapters: dict[str, EngineAdapter] = {}
        self._stack: list[str] = []          # 二期 WebView 上下文栈（M1 恒为单元素）

    async def open(self, config: SessionConfig) -> EngineAdapter:
        adapter = self._registry.create(config.engine_key)
        await adapter.start(config)
        self._adapters[config.engine_key] = adapter
        self._stack.append(config.engine_key)
        logger.info("session opened", extra={
            "event": "session.open", "engine_key": config.engine_key,
            "platform": config.platform, "session_id": adapter.session_id(),
        })
        return adapter

    def get(self, engine_key: str) -> EngineAdapter | None:
        return self._adapters.get(engine_key)

    @property
    def current(self) -> EngineAdapter | None:
        if not self._stack:
            return None
        return self._adapters.get(self._stack[-1])

    @property
    def active_engine(self) -> str | None:
        return self._stack[-1] if self._stack else None

    def push(self, engine_key: str) -> None:
        """二期 WebView：attach_webview 时压栈。M1 不使用。"""
        self._stack.append(engine_key)

    def pop(self) -> str | None:
        return self._stack.pop() if len(self._stack) > 1 else None

    async def close_all(self) -> None:
        for key, adapter in list(self._adapters.items()):
            try:
                await adapter.stop()
            except Exception:                      # stop 失败不能掩盖真正的错误
                logger.warning("adapter.stop failed: %s", key, exc_info=True)
            finally:
                self._adapters.pop(key, None)
        self._stack.clear()

    async def __aenter__(self) -> "SessionManager":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.close_all()
