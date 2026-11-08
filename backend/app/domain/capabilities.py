"""引擎能力矩阵 —— 能力的唯一事实来源（P3）。

启动时与数据库 ``action_catalog`` **双向强校验**（M1 FR7 / F2）：

* 方向一：DB 里某动作声明支持引擎 E，则 ``CAPABILITY_MATRIX[E]`` 必须含它
* 方向二：``CAPABILITY_MATRIX[E]`` 含某动作，则 DB 里该动作的 engines 必须含 E

单向校验只能发现"声明了但矩阵没有"；反方向的遗漏会让动作**永远选不到**（前端下拉由字典驱动），
形成死代码且无人发现。
"""
from __future__ import annotations

from dataclasses import dataclass

from app.domain.enums import PLATFORM_ENGINES, EngineKey, Platform

_WEB = {
    "click", "input", "get_text", "get_attribute", "wait_element", "check_exists",
    "hover", "select_option", "double_click", "scroll_to_element", "drag",
    "coordinate_click", "upload_file", "element_list",
    "navigate", "go_back", "go_forward", "refresh", "switch_to_iframe",
    "switch_to_page", "page_scroll",
    "screenshot", "get_url", "get_title", "get_cookies", "set_cookies",
    "delete_cookies", "accept_dialog",
}

_APPIUM = {
    "click", "input", "get_text", "get_attribute", "wait_element", "check_exists",
    "hover", "select_option", "double_click", "long_press", "scroll_to_element",
    "drag", "coordinate_click", "element_scroll", "page_swipe", "multi_finger_swipe",
    "swipe_up", "swipe_down", "element_list", "screenshot",
    "get_contexts", "switch_to_context",
    "start_app", "stop_app", "restart_app", "background_foreground", "go_home",
    "fix_orientation",
}

_U2 = {
    "click", "input", "get_text", "get_attribute", "wait_element", "check_exists",
    "double_click", "long_press", "scroll_to_element", "drag", "coordinate_click",
    "element_scroll", "page_swipe", "multi_finger_swipe", "swipe_up", "swipe_down",
    "element_list", "screenshot",
    "start_app", "stop_app", "restart_app", "background_foreground", "go_home",
    "fix_orientation",
}

#: 引擎 → 声明支持的动作集合
CAPABILITY_MATRIX: dict[str, frozenset[str]] = {
    EngineKey.PLAYWRIGHT: frozenset(_WEB),
    EngineKey.APPIUM: frozenset(_APPIUM),
    EngineKey.UIAUTOMATOR2: frozenset(_U2),
}


@dataclass(frozen=True, slots=True)
class EngineMeta:
    key: str
    label: str
    platforms: frozenset[str]
    implemented: bool
    adapter_path: str


ENGINES: dict[str, EngineMeta] = {
    EngineKey.PLAYWRIGHT: EngineMeta(
        EngineKey.PLAYWRIGHT, "Playwright", frozenset({Platform.WEB}), True,
        "app.engines.adapters.playwright_adapter:PlaywrightAdapter"),
    EngineKey.APPIUM: EngineMeta(
        EngineKey.APPIUM, "Appium", frozenset({Platform.ANDROID, Platform.IOS}), True,
        "app.engines.adapters.appium_adapter:AppiumAdapter"),
    EngineKey.UIAUTOMATOR2: EngineMeta(
        EngineKey.UIAUTOMATOR2, "uiautomator2", frozenset({Platform.ANDROID}), False,
        "app.engines.adapters.stub_adapter:UIAutomator2Adapter"),
}


def engines_for(platform: str) -> frozenset[str]:
    return PLATFORM_ENGINES.get(platform, frozenset())


def platforms_of(engine_key: str) -> frozenset[str]:
    meta = ENGINES.get(engine_key)
    return meta.platforms if meta else frozenset()


def supports(engine_key: str, action_key: str) -> bool:
    return action_key in CAPABILITY_MATRIX.get(engine_key, frozenset())


def assert_engine_platform_consistency() -> None:
    """引擎自述平台 vs 平台→引擎映射，必须互相覆盖。"""
    for platform, engine_keys in PLATFORM_ENGINES.items():
        for ek in engine_keys:
            meta = ENGINES.get(ek)
            assert meta is not None, f"平台 {platform} 引用了未注册引擎 {ek}"
            assert platform in meta.platforms, (
                f"引擎 {ek} 未声明支持平台 {platform}"
            )
    for ek, meta in ENGINES.items():
        for platform in meta.platforms:
            assert ek in PLATFORM_ENGINES.get(platform, frozenset()), (
                f"引擎 {ek} 声明支持 {platform}，但该平台未列出它"
            )
