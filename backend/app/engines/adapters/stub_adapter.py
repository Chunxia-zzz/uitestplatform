"""Appium / uiautomator2 桩适配器（D3：一期只留接口与注册位，不实现）。

语义分界（FR15）：
* 这里抛 ``NotImplementedError`` —— "该引擎应支持、但 M4 才实现"
* 基类 ``_not_supported`` 抛 ``UnsupportedActionError`` —— "该引擎本来就不支持"

两者混用会让 M4 的工作量彻底失去可追踪性。
"""
from __future__ import annotations

from app.domain.enums import Platform
from app.engines.base import EngineAdapter, SessionConfig

_HINT = "M4 计划：见 docs/UI自动化平台移动端对接方案.md"


class _StubBase(EngineAdapter):
    def __init__(self) -> None:
        super().__init__()
        self._config: SessionConfig | None = None

    async def start(self, config: SessionConfig) -> None:
        self._config = config
        raise NotImplementedError(f"{self.key} 适配器尚未实现（{_HINT}）")

    async def stop(self) -> None:
        self._session_id = None

    async def create(self, config: SessionConfig) -> str:
        await self.start(config)
        return ""

    def session_id(self) -> str | None:
        return self._session_id

    def _todo(self, action: str):
        raise NotImplementedError(f"{self.key}.{action} 尚未实现（{_HINT}）")

    async def click(self, chain, ctx, **_):
        self._todo("click")

    async def input(self, chain, ctx, *, text, clear: bool = False):
        self._todo("input")

    async def get_text(self, chain, ctx, *, output_var=None):
        self._todo("get_text")

    async def get_attribute(self, chain, ctx, *, name, output_var=None):
        self._todo("get_attribute")

    async def wait_element(self, chain, ctx, *, state="visible", timeout_ms=None):
        self._todo("wait_element")

    async def check_exists(self, chain, ctx, *, output_var=None):
        self._todo("check_exists")

    async def screenshot(self, chain, ctx, *, path=None, full_page=False,
                         target: str = "page"):
        self._todo("screenshot")


class AppiumAdapter(_StubBase):
    key = "appium"
    platforms = frozenset({Platform.ANDROID, Platform.IOS})


class UIAutomator2Adapter(_StubBase):
    key = "uiautomator2"
    platforms = frozenset({Platform.ANDROID})
