"""引擎适配层基类与值对象。

冻结约定（M1 FR4）：
    适配器 **方法名 == action_key**、**关键字参数名 == params_schema 的属性名**
→ ``getattr(adapter, action_key)(chain, ctx, **params)`` 可直接转发，**不写动作映射表**。
这是"加一个引擎 = 加一个文件 + 注册一行"成立的前提。

语义分界（M1 FR15）：
* ``NotImplementedError`` —— 该引擎应支持、但本里程碑未实现（M4 待办，工作量可追踪）
* ``UnsupportedActionError`` —— 该引擎本来就不支持（能力边界）
由 ``_not_supported()`` 依据 ``CAPABILITY_MATRIX`` 自动区分。
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.core.errors import LocatorNotFoundError, UnsupportedActionError
from app.domain.capabilities import CAPABILITY_MATRIX
from app.domain.enums import Platform


# ─────────────────────────── 值对象 ───────────────────────────
@dataclass(frozen=True, slots=True)
class Locator:
    """单条定位符（语义层，不含引擎前缀）。"""
    type: str
    value: str
    locator_id: int | None = None


@dataclass(frozen=True, slots=True)
class LocatorChain:
    """有序回退链。第一条失败试第二条，命中即止。"""
    element_id: int
    locators: tuple[Locator, ...] = ()

    @classmethod
    def of(cls, element_id: int, locators) -> LocatorChain:
        items = tuple(locators)
        assert all(isinstance(x, Locator) for x in items), "LocatorChain 只能装 Locator"
        return cls(element_id, items)

    def __bool__(self) -> bool:
        return bool(self.locators)

    def __len__(self) -> int:
        return len(self.locators)

    @property
    def first(self) -> Locator:
        if not self.locators:
            raise LocatorNotFoundError(f"元素 {self.element_id} 的回退链为空")
        return self.locators[0]


@dataclass(frozen=True, slots=True)
class LocatorProbe:
    """定位符探测结果（诊断用，不是用例动作 —— M2 FR19）。"""
    count: int
    sample: dict | None = None
    elapsed_ms: int = 0
    error: str | None = None


@dataclass
class ActionContext:
    """一次动作调用所需的运行时上下文。"""
    execution_id: int | None = None
    case_id: int | None = None
    step_seq: int = 0
    timeout_ms: int = 15_000
    variables: dict[str, Any] = field(default_factory=dict)
    log: Callable[[str, dict], None] | None = None
    #: 供 drag 之类"双元素动作"使用：执行器预先解析好的目标元素链
    resolved_chains: dict[int, LocatorChain] = field(default_factory=dict)
    #: 适配器产生的产物（只记路径事实，落库由执行器负责 —— FR34）
    artifacts: list[dict[str, Any]] = field(default_factory=list)

    def emit(self, event: str, **payload: Any) -> None:
        if self.log:
            self.log(event, payload)

    def set_var(self, name: str | None, value: Any) -> Any:
        if name:
            self.variables[name] = value
        return value


@dataclass(frozen=True, slots=True)
class SessionConfig:
    """建会话所需的全部信息（来自 project + execution_target）。"""
    platform: str
    engine_key: str
    base_url: str | None = None
    options: dict[str, Any] = field(default_factory=dict)
    headless: bool = True
    timeout_ms: int = 15_000
    #: M3.6 GAP-08（D36）：诊断产物目录 ``{artifacts_dir}/exec-{id}``。
    #: additive 默认 None —— locator_verify_service 等旧调用点不传即 None，行为不变。
    diagnostics_dir: str | None = None


# ─────────────────────────── 适配器基类 ───────────────────────
class EngineAdapter(ABC):
    """所有 UI 引擎的统一接口。

    抽象成员（任何引擎的"最小完整闭环"）：
        start / stop / create / session_id + click / input / get_text / get_attribute
        / wait_element / check_exists / screenshot
    其余动作默认 ``_not_supported()`` —— 桩适配器只需实现 11 个成员。
    """

    #: 引擎标识，必须与 ``EngineKey`` 一致
    key: str = ""
    #: 支持的平台集合
    platforms: frozenset[str] = frozenset()

    def __init__(self) -> None:
        self._session_id: str | None = None

    # ── 生命周期 ────────────────────────────────────────────
    @abstractmethod
    async def start(self, config: SessionConfig) -> None:
        ...

    @abstractmethod
    async def stop(self) -> None:
        ...

    @abstractmethod
    async def create(self, config: SessionConfig) -> str:
        """建会话并返回 session_id。"""

    @abstractmethod
    def session_id(self) -> str | None:
        ...

    # ── 核心动作（7）─────────────────────────────────────────
    @abstractmethod
    async def click(self, chain: LocatorChain, ctx: ActionContext) -> None:
        ...

    @abstractmethod
    async def input(self, chain: LocatorChain, ctx: ActionContext, *,
                    text: str, clear: bool = False) -> None:
        ...

    @abstractmethod
    async def get_text(self, chain: LocatorChain, ctx: ActionContext, *,
                       output_var: str | None = None) -> str:
        ...

    @abstractmethod
    async def get_attribute(self, chain: LocatorChain, ctx: ActionContext, *,
                            name: str, output_var: str | None = None) -> str | None:
        ...

    @abstractmethod
    async def wait_element(self, chain: LocatorChain, ctx: ActionContext, *,
                           state: str = "visible", timeout_ms: int | None = None) -> None:
        ...

    @abstractmethod
    async def check_exists(self, chain: LocatorChain, ctx: ActionContext, *,
                           output_var: str | None = None) -> bool:
        ...

    @abstractmethod
    async def screenshot(self, chain: LocatorChain | None, ctx: ActionContext, *,
                         path: str | None = None, full_page: bool = False) -> str:
        ...

    # ── 诊断（非动作，不进 action_catalog —— M2 FR19 / M3.5 FR62）───
    async def probe_locator(self, chain: LocatorChain, ctx: ActionContext) -> LocatorProbe:
        """默认实现：用 check_exists 兜底，count ∈ {0,1}。

        桩适配器无需覆写；能精确计数的引擎（Playwright）应覆写。
        """
        started = time.perf_counter()
        try:
            ok = await self.check_exists(chain, ActionContext(
                timeout_ms=ctx.timeout_ms, log=ctx.log))
            return LocatorProbe(count=1 if ok else 0,
                                elapsed_ms=int((time.perf_counter() - started) * 1000))
        except NotImplementedError as exc:
            return LocatorProbe(count=0, error=str(exc),
                                elapsed_ms=int((time.perf_counter() - started) * 1000))

    async def scan_dom(self, ctx: ActionContext, *,
                       max_elements: int = 200) -> list[dict]:
        """抓取当前页面的可交互元素（M3.5，D28）。

        诊断方法，不进 action_catalog：扫描是平台能力，不是用例步骤。
        桩适配器（Appium/u2）默认不支持；Playwright 覆写。
        返回原始 DOM 项，候选分类与定位符生成在 ``domain.scan``。
        """
        raise NotImplementedError(f"{self.key} 不支持页面扫描")

    async def finalize_diagnostics(self, *, save_trace: bool) -> None:
        """诊断收尾（M3.6 GAP-08，D36）：按终态保存或丢弃 trace。

        非动作诊断方法，**不进 action_catalog**（probe_locator / scan_dom 先例）。
        基类 no-op：桩适配器零改动；Playwright 覆写。
        必须在 context close **之前**调用（tracing.stop 先于 close —— D37）。
        """
        return None

    # ── 其余 35 个动作：默认不支持（由矩阵决定语义）──────────
    def _not_supported(self, action_key: str):
        declared = CAPABILITY_MATRIX.get(self.key, frozenset())
        if action_key in declared:
            raise NotImplementedError(
                f"{self.key} 声明支持 {action_key} 但尚未实现（计划 M4）")
        raise UnsupportedActionError(
            f"{self.key} 不支持动作 {action_key}",
            {"engine_key": self.key, "action_key": action_key},
        )

    async def hover(self, chain, ctx) -> None:
        self._not_supported("hover")

    async def select_option(self, chain, ctx, *, value: str | None = None,
                            label: str | None = None, index: int | None = None) -> None:
        self._not_supported("select_option")

    async def double_click(self, chain, ctx) -> None:
        self._not_supported("double_click")

    async def long_press(self, chain, ctx, *, duration_ms: int = 1000) -> None:
        self._not_supported("long_press")

    async def scroll_to_element(self, chain, ctx) -> None:
        self._not_supported("scroll_to_element")

    async def drag(self, chain, ctx, *, target_element_id: int | None = None,
                   duration_ms: int = 500) -> None:
        self._not_supported("drag")

    async def coordinate_click(self, chain, ctx, *, x: int, y: int) -> None:
        self._not_supported("coordinate_click")

    async def upload_file(self, chain, ctx, *, file_path: str) -> None:
        self._not_supported("upload_file")

    async def element_scroll(self, chain, ctx, *, direction: str = "down",
                             distance: int = 300) -> None:
        self._not_supported("element_scroll")

    async def page_swipe(self, chain, ctx, *, direction: str = "up",
                         distance: int = 300) -> None:
        self._not_supported("page_swipe")

    async def multi_finger_swipe(self, chain, ctx, *, direction: str = "up",
                                 distance: int = 300) -> None:
        self._not_supported("multi_finger_swipe")

    async def swipe_up(self, chain, ctx, *, distance: int = 300) -> None:
        self._not_supported("swipe_up")

    async def swipe_down(self, chain, ctx, *, distance: int = 300) -> None:
        self._not_supported("swipe_down")

    async def element_list(self, chain, ctx, *, output_var: str | None = None) -> list:
        self._not_supported("element_list")

    async def navigate(self, chain, ctx, *, url: str) -> None:
        self._not_supported("navigate")

    async def go_back(self, chain, ctx) -> None:
        self._not_supported("go_back")

    async def go_forward(self, chain, ctx) -> None:
        self._not_supported("go_forward")

    async def refresh(self, chain, ctx) -> None:
        self._not_supported("refresh")

    async def switch_to_iframe(self, chain, ctx, *, index: int | None = None) -> None:
        self._not_supported("switch_to_iframe")

    async def switch_to_page(self, chain, ctx, *, index: int = -1) -> None:
        self._not_supported("switch_to_page")

    async def page_scroll(self, chain, ctx, *, direction: str = "down",
                          distance: int = 500, to: str | None = None) -> None:
        self._not_supported("page_scroll")

    async def get_contexts(self, chain, ctx, *, output_var: str | None = None) -> list:
        self._not_supported("get_contexts")

    async def switch_to_context(self, chain, ctx, *, context: str) -> None:
        self._not_supported("switch_to_context")

    async def start_app(self, chain, ctx, *, app_package: str | None = None,
                        app_activity: str | None = None) -> None:
        self._not_supported("start_app")

    async def stop_app(self, chain, ctx, *, app_package: str | None = None) -> None:
        self._not_supported("stop_app")

    async def restart_app(self, chain, ctx, *, app_package: str | None = None) -> None:
        self._not_supported("restart_app")

    async def background_foreground(self, chain, ctx, *, seconds: int = 3) -> None:
        self._not_supported("background_foreground")

    async def go_home(self, chain, ctx) -> None:
        self._not_supported("go_home")

    async def fix_orientation(self, chain, ctx, *, orientation: str = "PORTRAIT") -> None:
        self._not_supported("fix_orientation")

    async def get_url(self, chain, ctx, *, output_var: str | None = None) -> str:
        self._not_supported("get_url")

    async def get_title(self, chain, ctx, *, output_var: str | None = None) -> str:
        self._not_supported("get_title")

    async def get_cookies(self, chain, ctx, *, output_var: str | None = None) -> list:
        self._not_supported("get_cookies")

    async def set_cookies(self, chain, ctx, *, cookies: list) -> None:
        self._not_supported("set_cookies")

    async def delete_cookies(self, chain, ctx) -> None:
        self._not_supported("delete_cookies")

    async def accept_dialog(self, chain, ctx, *, accept: bool = True,
                            dialog_text: str | None = None) -> None:
        self._not_supported("accept_dialog")

    # ── 能力自述 ────────────────────────────────────────────
    @property
    def capabilities(self) -> frozenset[str]:
        return CAPABILITY_MATRIX.get(self.key, frozenset())

    def supports(self, platform: str | None = None) -> bool:
        return platform is None or platform in self.platforms

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{type(self).__name__} key={self.key} session={self._session_id}>"


__all__ = [
    "ActionContext", "EngineAdapter", "Locator", "LocatorChain", "LocatorProbe",
    "Platform", "SessionConfig",
]
