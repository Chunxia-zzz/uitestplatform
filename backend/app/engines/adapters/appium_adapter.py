"""Appium 适配器（M4.1 / M4.2 / D42）。

设计取舍：**不复用同步的 Appium-Python-Client**，改为 async httpx 直连 Appium REST。
理由（都是实测代价换来的）：
1. 适配器接口本身是 async，直连不需要 ``asyncio.to_thread`` 包一层；
2. ``httpx.AsyncClient(trust_env=False)`` 能绕开 ``HTTP_PROXY`` 代理 localhost 的问题
   —— 本次真机联调时，代理把发往 ``127.0.0.1:4723`` 的定位请求体破坏，
   报 ``FindElementModel: ... 'selector' is not present``；
3. 不引入 selenium 依赖。

动作覆盖（M4.2）：
- **26 个 Android 可用动作**：核心 12 个 + 手势/滑动/上下文/生命周期 14 个；
- **2 个平台不适用**（``PLATFORM_INAPPLICABLE``）：``hover`` / ``select_option``
  —— 声明保留在能力矩阵（appium 也覆盖 iOS），但 Android 上必须明确报错，
  不允许"静默成功"，否则用户以为跑过了。
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import settings
from app.core.errors import LocatorNotFoundError, UnsupportedActionError, ValidationFailed
from app.domain.enums import Platform
from app.engines.base import (
    ActionContext,
    EngineAdapter,
    Locator,
    LocatorChain,
    LocatorProbe,
    SessionConfig,
)

logger = logging.getLogger(__name__)

DEFAULT_APPIUM_URL = "http://127.0.0.1:4723"
W3C_ELEMENT_KEY = "element-6066-11e4-a52e-4f735466cecf"


def _java_str(value: str) -> str:
    """把 Python 字符串变成 Java/UiSelector 可用的双引号字面量。"""
    return json.dumps(str(value), ensure_ascii=False)


def translate_locator(loc: Locator) -> tuple[str, str]:
    """语义层 locator_type → Appium (using, value)。

    只在这里出现引擎语汇；``element_locator`` 表里永远存语义类型。
    """
    t, v = loc.type, loc.value
    if t == "resource_id":
        return "id", v
    if t == "accessibility_id":
        return "accessibility id", v
    if t == "text":
        return "-android uiautomator", f"new UiSelector().text({_java_str(v)})"
    if t == "text_contains":
        return "-android uiautomator", f"new UiSelector().textContains({_java_str(v)})"
    if t == "class_name":
        return "class name", v
    if t == "xpath":
        return "xpath", v
    if t == "uiautomator":
        return "-android uiautomator", v
    raise ValueError(f"Appium 不支持的 Android 定位类型：{t}")


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _relative_activity(activity: str, package: str) -> str:
    """把 ``com.demo.app.MainActivity`` 归一化成 ``.MainActivity``。

    Appium 的 ``start_activity`` 会自己拼 ``appPackage``；传全限定名会变成
    ``com.demo.app.com.demo.app.MainActivity``，报 "never started"。
    """
    activity = (activity or "").strip()
    prefix = f"{package}."
    if package and activity.startswith(prefix):
        return "." + activity[len(prefix):]
    return activity


_DIRECTIONS = ("up", "down", "left", "right")

#: ``element_scroll`` 的 ``direction`` 是**内容方向**（与 Web ``page_scroll`` 一致），
#: 这里翻成手指方向；``page_swipe`` / ``swipe_*`` / ``multi_finger_swipe`` 直接用手指方向。
_CONTENT_TO_FINGER = {"down": "up", "up": "down", "right": "left", "left": "right"}


def _finger_direction(value: str) -> str:
    direction = str(value or "").strip().lower()
    if direction not in _DIRECTIONS:
        raise ValueError(f"direction 只能是 {'/'.join(_DIRECTIONS)}：{value}")
    return direction


def _content_direction(value: str) -> str:
    return _CONTENT_TO_FINGER[_finger_direction(value)]


def _clamp_percent(value: Any) -> float:
    """UiAutomator2 的 ``percent`` 必须在 (0, 1) 内，越界会被驱动拒绝。"""
    try:
        percent = float(value)
    except (TypeError, ValueError):
        percent = 0.5
    return round(max(0.05, min(0.95, percent)), 3)


#: 驱动传输层瞬时错误的特征串（App 启动瞬间 / uiautomator2 server 重启时高频出现）。
#: 这类错误重试有意义，但**必须限次** —— 真机上每次要 3 秒，无限重试会把一步拖到分钟级。
_TRANSIENT_MARKERS = (
    "could not proxy command",
    "cannot be proxied",
    "instrumentation process is not running",
    "socket hang up",
    "econnreset",
    "connection reset",
    "readtimeout",
    "unknown error",
)

MAX_TRANSIENT_RETRIES = 3


def _is_transient_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _TRANSIENT_MARKERS)


def _timeout_seconds(value: Any, default: float = 60.0) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    read = getattr(value, "read", None)
    return float(read) if isinstance(read, (int, float)) and read > 0 else default




class AppiumAdapter(EngineAdapter):
    key = "appium"
    platforms = frozenset({Platform.ANDROID, Platform.IOS})

    #: 声明在能力矩阵里、但 Android 上没有对应语义的动作（iOS/Web 才有）。
    #: 保留声明是为了不破坏跨平台契约；Android 上调用必须**明确报错**。
    PLATFORM_INAPPLICABLE = {
        "hover": "触屏无 pointer hover 语义；请改用 click / long_press",
        "select_option": "Android 原生无 select 下拉控件；请改用 click 展开 + click 选项",
    }

    def __init__(self) -> None:
        super().__init__()
        self._client: httpx.AsyncClient | None = None
        self._base_url = DEFAULT_APPIUM_URL
        self._options: dict[str, Any] = {}
        self._app_package = ""
        self._app_activity = ""

    # ───────────────────────── 生命周期 ─────────────────────────
    async def start(self, config: SessionConfig) -> None:
        if self._client is not None and self._session_id:
            return
        if str(config.platform) != str(Platform.ANDROID):
            raise UnsupportedActionError(
                "AppiumAdapter 目前仅实现 Android；iOS 需要 macOS 构建机或云真机（M4.3）",
                {"platform": str(config.platform)},
            )

        opts = dict(config.options or {})
        udid = str(opts.get("udid") or "").strip()
        package = str(opts.get("app_package") or opts.get("appPackage") or "").strip()
        if not udid:
            raise ValidationFailed(
                "Android 执行目标缺少 options.udid（adb devices 的序列号）",
                {"missing": "udid"},
            )
        if not package:
            raise ValidationFailed(
                "Android 执行目标缺少 options.app_package（被测 App 包名）",
                {"missing": "app_package"},
            )

        base_url = str(opts.get("appium_url") or opts.get("appiumServer")
                       or DEFAULT_APPIUM_URL).rstrip("/")
        activity = str(opts.get("app_activity") or opts.get("appActivity") or "").strip()
        caps: dict[str, Any] = {
            "platformName": "Android",
            "appium:automationName": "UiAutomator2",
            "appium:udid": udid,
            "appium:deviceName": str(opts.get("device_name") or udid),
            "appium:appPackage": package,
            "appium:noReset": _as_bool(opts.get("no_reset"), True),
            "appium:newCommandTimeout": _as_int(opts.get("new_command_timeout"), 180),
            "appium:autoGrantPermissions": _as_bool(opts.get("auto_grant_permissions"), True),
            "appium:adbExecTimeout": _as_int(opts.get("adb_exec_timeout"), 60_000),
        }
        if activity:
            caps["appium:appActivity"] = _relative_activity(activity, package)
        if opts.get("platform_version"):
            caps["appium:platformVersion"] = str(opts["platform_version"])

        self._client = httpx.AsyncClient(
            base_url=base_url, trust_env=False,
            timeout=httpx.Timeout(60.0, connect=10.0),
        )
        self._base_url = base_url
        try:
            value = await self._request(
                "POST", "/session",
                json_body={"capabilities": {"alwaysMatch": caps}},
                timeout=httpx.Timeout(180.0, connect=10.0),
            )
        except Exception:
            await self._client.aclose()
            self._client = None
            raise

        session_id = (value or {}).get("sessionId") if isinstance(value, dict) else None
        if not session_id:
            await self._client.aclose()
            self._client = None
            raise RuntimeError(f"Appium 未返回 sessionId：{value!r}"[:500])

        self._session_id = str(session_id)
        self._options = opts
        self._app_package = package
        self._app_activity = activity
        logger.info("appium session opened", extra={
            "event": "session.open", "engine_key": self.key,
            "platform": "ANDROID", "session_id": self._session_id,
        })

    async def stop(self) -> None:
        if self._client is None:
            self._session_id = None
            return
        if self._session_id:
            try:
                await self._cmd("DELETE", "", timeout=10.0)
            except Exception:                       # 会话已失效不能掩盖真正的错误
                logger.warning("appium session delete failed", exc_info=True)
        try:
            await self._client.aclose()
        finally:
            self._client = None
            self._session_id = None
            self._options = {}

    async def create(self, config: SessionConfig) -> str:
        await self.start(config)
        return self._session_id or ""

    def session_id(self) -> str | None:
        return self._session_id

    # ───────────────────────── HTTP 基础 ─────────────────────────
    async def _request(self, method: str, path: str, *,
                       json_body: dict | None = None,
                       timeout: httpx.Timeout | float | None = None) -> Any:
        if self._client is None:
            raise RuntimeError("Appium 客户端尚未初始化")
        # 命令级硬上限：httpx 的 read timeout 挡不住"慢速滴流"响应，这里再兜一层
        base_timeout = _timeout_seconds(timeout)
        hard_timeout = base_timeout + max(1.0, min(5.0, base_timeout * 0.1))
        try:
            resp = await asyncio.wait_for(
                self._client.request(method, path, json=json_body, timeout=timeout),
                timeout=hard_timeout)
        except TimeoutError as exc:
            raise RuntimeError(
                f"Appium {method} {path} 超过 {hard_timeout:.0f}s 未返回"
                f"（命令级硬上限，通常是设备/驱动卡死）") from exc
        try:
            data = resp.json()
        except ValueError as exc:
            raise RuntimeError(
                f"Appium 响应不是 JSON：HTTP {resp.status_code} {resp.text[:200]}") from exc
        value = data.get("value") if isinstance(data, dict) else None
        if resp.status_code >= 400 or (isinstance(value, dict) and value.get("error")):
            err = value.get("error") if isinstance(value, dict) else ""
            msg = value.get("message") if isinstance(value, dict) else str(value)
            raise RuntimeError(
                f"Appium {method} {path} 失败：HTTP {resp.status_code} {err} {msg}"[:600])
        return value

    async def _cmd(self, method: str, path: str, *,
                   json_body: dict | None = None,
                   timeout: httpx.Timeout | float | None = None) -> Any:
        if not self._session_id:
            raise RuntimeError("Appium 会话未建立")
        return await self._request(
            method, f"/session/{self._session_id}{path}",
            json_body=json_body, timeout=timeout)

    # ───────────────────────── 回退链 ─────────────────────────
    async def _find(self, chain: LocatorChain, ctx: ActionContext, *,
                    timeout_ms: int | None = None, multiple: bool = False):
        """沿回退链找元素；每条候选最多 ``min(总超时, 2500ms)``，末条用满。

        M4.2 加固（真机踩过）：用 ``time.perf_counter()`` 而不是事件循环时钟计时，
        并对**驱动传输层连续失败**（如 ``500 Could not proxy command``）快速放弃 ——
        否则 App 启动瞬间每次请求要 3 秒，重试会把一步拖到分钟级。
        """
        timeout = ctx.timeout_ms if timeout_ms is None else max(0, timeout_ms)
        total = len(chain.locators)
        last_error: Exception | None = None
        started = time.perf_counter()

        for index, loc in enumerate(chain.locators):
            per_timeout = timeout if index == total - 1 else min(timeout, 2500)
            loc_deadline = time.perf_counter() + per_timeout / 1000
            transient_failures = 0
            while True:
                try:
                    using, value = translate_locator(loc)
                    # 单次请求单独限时：避免一条卡死的命令吃掉整条候选的预算
                    remaining = max(0.5, loc_deadline - time.perf_counter())
                    elements = await self._cmd(
                        "POST", "/elements",
                        json_body={"using": using, "value": value},
                        timeout=max(3.0, min(8.0, remaining)))
                    transient_failures = 0
                    if isinstance(elements, list) and elements:
                        ctx.emit("locator.hit", element_id=chain.element_id,
                                 locator_id=loc.locator_id, fallback_index=index)
                        return elements if multiple else elements[0]
                except Exception as exc:            # 本条失败 → 回退下一条
                    last_error = exc
                    if _is_transient_error(exc):
                        transient_failures += 1
                        if transient_failures >= MAX_TRANSIENT_RETRIES:
                            break                   # 驱动连着不行 → 本条定位符直接放弃
                if time.perf_counter() >= loc_deadline:
                    break
                await asyncio.sleep(0.2)
            ctx.emit("locator.miss", element_id=chain.element_id,
                     locator_id=loc.locator_id, fallback_index=index,
                     error=str(last_error)[:200] if last_error else "no match")

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        raise LocatorNotFoundError(
            f"元素 {chain.element_id} 的全部 {total} 条定位符均未命中"
            f"（{elapsed_ms}ms）：{last_error}",
            {"element_id": chain.element_id, "locators": total, "elapsed_ms": elapsed_ms},
        )


    @staticmethod
    def _element_id(element: Any) -> str:
        if not isinstance(element, dict):
            raise RuntimeError(f"Appium 返回的元素结构异常：{element!r}"[:300])
        eid = element.get(W3C_ELEMENT_KEY) or element.get("ELEMENT")
        if not eid:
            raise RuntimeError(f"Appium 元素缺少 id：{element!r}"[:300])
        return str(eid)

    # ─────────────────────── 手势与几何（M4.2）───────────────────────
    async def _execute(self, script: str, args: list[dict] | None = None) -> Any:
        """执行 UiAutomator2 的 ``mobile:`` 命令（走 W3C ``/execute/sync``）。"""
        return await self._cmd("POST", "/execute/sync",
                               json_body={"script": script, "args": args or []})

    async def _gesture(self, name: str, params: dict[str, Any]) -> None:
        await self._execute(f"mobile: {name}", [params])

    async def _rect(self, element: Any) -> dict[str, int]:
        value = await self._cmd("GET", f"/element/{self._element_id(element)}/rect")
        if not isinstance(value, dict):
            raise RuntimeError(f"Appium 返回的 rect 异常：{value!r}"[:200])
        return {k: int(value.get(k) or 0) for k in ("x", "y", "width", "height")}

    @staticmethod
    def _center(rect: dict[str, int]) -> tuple[int, int]:
        return rect["x"] + rect["width"] // 2, rect["y"] + rect["height"] // 2

    async def _screen(self) -> dict[str, int]:
        value = await self._cmd("GET", "/window/rect")
        if not isinstance(value, dict):
            raise RuntimeError(f"Appium 返回的 window rect 异常：{value!r}"[:200])
        return {"left": 0, "top": 0,
                "width": int(value.get("width") or 0),
                "height": int(value.get("height") or 0)}

    async def _gesture_bounds(self) -> dict[str, int]:
        """整屏手势的安全区域：**必须避开状态栏/导航栏**。

        真机实测（M4.2）：从屏幕最顶部下滑会把系统通知栏拉下来，
        之后 ``mCurrentFocus=NotificationShade``，所有元素定位都会落空 ——
        表现为"上一步成功、下一步莫名找不到元素"。内缩由 ``options.gesture_inset_px``
        覆盖，默认取屏高的 8%（下限 120px）。
        """
        screen = await self._screen()
        inset = _as_int(self._options.get("gesture_inset_px"), 0)
        if inset <= 0:
            inset = max(120, int(screen["height"] * 0.08))
        return {"left": inset, "top": inset,
                "width": max(1, screen["width"] - inset * 2),
                "height": max(1, screen["height"] - inset * 2)}

    async def _swipe(self, finger_direction: str, percent: float, *,
                     element_id: str | None = None,
                     bounds: dict[str, int] | None = None) -> None:
        params: dict[str, Any] = {"direction": finger_direction,
                                  "percent": _clamp_percent(percent)}
        if element_id:
            params["elementId"] = element_id
        elif bounds:
            params.update(bounds)
        await self._gesture("swipeGesture", params)

    def _platform_inapplicable(self, action_key: str) -> None:
        reason = self.PLATFORM_INAPPLICABLE[action_key]
        raise UnsupportedActionError(
            f"appium(Android) 不适用动作 {action_key}：{reason}",
            {"engine_key": self.key, "action_key": action_key, "platform": "ANDROID"},
        )


    # ───────────────────────── 核心动作 ─────────────────────────
    async def click(self, chain: LocatorChain, ctx: ActionContext, **_) -> None:
        element = await self._find(chain, ctx)
        await self._cmd("POST", f"/element/{self._element_id(element)}/click",
                        json_body={})

    async def input(self, chain: LocatorChain, ctx: ActionContext, *,
                    text: str, clear: bool = False) -> None:
        element = await self._find(chain, ctx)
        eid = self._element_id(element)
        if clear:
            await self._cmd("POST", f"/element/{eid}/clear", json_body={})
        await self._cmd("POST", f"/element/{eid}/value",
                        json_body={"text": str(text), "value": list(str(text))})

    async def get_text(self, chain: LocatorChain, ctx: ActionContext, *,
                       output_var: str | None = None) -> str:
        element = await self._find(chain, ctx)
        text = await self._cmd("GET", f"/element/{self._element_id(element)}/text")
        return ctx.set_var(output_var, str(text or "").strip())

    async def get_attribute(self, chain: LocatorChain, ctx: ActionContext, *,
                            name: str, output_var: str | None = None) -> str | None:
        element = await self._find(chain, ctx)
        value = await self._cmd(
            "GET", f"/element/{self._element_id(element)}/attribute/{quote(str(name), safe='')}")
        return ctx.set_var(output_var, value)

    async def wait_element(self, chain: LocatorChain, ctx: ActionContext, *,
                           state: str = "visible", timeout_ms: int | None = None) -> None:
        """M4.2：四态都支持（visible / attached / hidden / detached）。

        ``hidden`` / ``detached`` 是**等待消失**，超时抛 ``TimeoutError`` → 步骤 ``ERROR``，
        与 Playwright 的 ``wait_for(state="hidden")`` 语义一致。
        """
        state = (state or "visible").strip().lower()
        timeout = ctx.timeout_ms if timeout_ms is None else max(0, timeout_ms)
        if state in ("visible", "attached"):
            await self._find(chain, ctx, timeout_ms=timeout)
            return
        if state not in ("hidden", "detached"):
            raise ValidationFailed(
                f"未知 wait_element(state={state})；支持 visible / attached / hidden / detached",
                {"state": state},
            )

        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout / 1000
        while True:
            try:
                await self._find(chain, ctx, timeout_ms=0)
            except LocatorNotFoundError:
                return
            if loop.time() >= deadline:
                raise TimeoutError(
                    f"等待元素消失超时（{timeout}ms）：元素 {chain.element_id} 仍然存在")
            await asyncio.sleep(0.2)


    async def check_exists(self, chain: LocatorChain, ctx: ActionContext, *,
                           output_var: str | None = None) -> bool:
        """沿回退链逐条试；不等待（轮询由 assert_* 在 timeout_ms 窗口内做）。"""
        try:
            await self._find(chain, ctx, timeout_ms=0)
            return ctx.set_var(output_var, True)
        except LocatorNotFoundError:
            return ctx.set_var(output_var, False)

    async def element_list(self, chain: LocatorChain, ctx: ActionContext, *,
                           output_var: str | None = None) -> list:
        """M4.2：返回形状与 Playwright 对齐 —— ``[{index, text, visible}]``（上限 200）。

        形状不一致会让"Web 用例换 Android 引擎就崩"，这是跨引擎一致性的硬要求。
        """
        elements = await self._find(chain, ctx, multiple=True)
        items: list[dict[str, Any]] = []
        for index, element in enumerate(elements[:200]):
            eid = self._element_id(element)
            text, visible = "", True
            try:
                text = str(await self._cmd("GET", f"/element/{eid}/text") or "")[:200]
            except Exception:                       # 单个元素取文本失败不影响整体
                text = ""
            try:
                visible = bool(await self._cmd("GET", f"/element/{eid}/displayed"))
            except Exception:
                visible = True
            items.append({"index": index, "text": text, "visible": visible})
        return ctx.set_var(output_var, items)


    # ───────────────────────── 手势与滑动（M4.2）─────────────────────────
    async def hover(self, chain, ctx, **_) -> None:
        """Android 无 hover 语义 —— 明确报错，不做"静默成功"。"""
        self._platform_inapplicable("hover")

    async def select_option(self, chain, ctx, *, value: str | None = None,
                            label: str | None = None, index: int | None = None) -> None:
        """Android 原生无 select 控件 —— 明确报错（该动作字典里本就标注 WEB/IOS）。"""
        self._platform_inapplicable("select_option")

    async def double_click(self, chain, ctx, **_) -> None:
        element = await self._find(chain, ctx)
        await self._gesture("doubleClickGesture",
                            {"elementId": self._element_id(element)})

    async def long_press(self, chain, ctx, *, duration_ms: int = 1000) -> None:
        element = await self._find(chain, ctx)
        await self._gesture("longClickGesture", {
            "elementId": self._element_id(element),
            "duration": max(1, int(duration_ms)),
        })

    async def coordinate_click(self, chain, ctx, *, x: int, y: int) -> None:
        await self._gesture("clickGesture", {"x": int(x), "y": int(y)})

    async def drag(self, chain, ctx, *, target_element_id: int | None = None,
                   duration_ms: int = 500) -> None:
        if target_element_id is None:
            raise ValueError("drag 需要 target_element_id")
        target_chain = ctx.resolved_chains.get(int(target_element_id))
        if target_chain is None:
            raise ValueError(f"执行器未预解析目标元素 {target_element_id} 的定位链")

        source = await self._find(chain, ctx)
        target = await self._find(target_chain, ctx)
        sx, sy = self._center(await self._rect(source))
        tx, ty = self._center(await self._rect(target))
        distance = max(1.0, ((tx - sx) ** 2 + (ty - sy) ** 2) ** 0.5)
        # duration_ms → 速度（px/s）：dragGesture 用 speed 而不是时长
        speed = max(200.0, min(10_000.0, distance / max(0.1, int(duration_ms) / 1000)))
        await self._gesture("dragGesture", {
            "elementId": self._element_id(source),
            "endX": tx, "endY": ty, "speed": int(speed),
        })

    async def element_scroll(self, chain, ctx, *, direction: str = "down",
                             distance: int = 300) -> None:
        """元素内滚动。``direction`` 是**内容方向**（down = 看更下面的内容）。"""
        finger = _content_direction(direction)
        element = await self._find(chain, ctx)
        rect = await self._rect(element)
        key = "width" if finger in ("left", "right") else "height"
        await self._swipe(finger, int(distance) / max(1, rect[key]),
                          element_id=self._element_id(element))

    async def page_swipe(self, chain, ctx, *, direction: str = "up",
                         distance: int = 300) -> None:
        """整屏滑动。``direction`` 是**手指方向**（up = 手指上划）。"""
        finger = _finger_direction(direction)
        bounds = await self._gesture_bounds()
        key = "width" if finger in ("left", "right") else "height"
        await self._swipe(finger, int(distance) / max(1, bounds[key]), bounds=bounds)


    async def swipe_up(self, chain, ctx, *, distance: int = 300) -> None:
        await self.page_swipe(chain, ctx, direction="up", distance=distance)

    async def swipe_down(self, chain, ctx, *, distance: int = 300) -> None:
        await self.page_swipe(chain, ctx, direction="down", distance=distance)

    async def multi_finger_swipe(self, chain, ctx, *, direction: str = "up",
                                 distance: int = 300) -> None:
        """双指同向滑动（捏合类场景用 ``pinch*``，这里只做平行双指）。"""
        finger = _finger_direction(direction)
        bounds = await self._gesture_bounds()
        cx = bounds["left"] + bounds["width"] // 2
        cy = bounds["top"] + bounds["height"] // 2
        spread = min(120, max(20, bounds["width"] // 6, bounds["height"] // 6))
        travel = min(int(distance), bounds["height"] // 2 if finger in ("up", "down")
                     else bounds["width"] // 2)
        dx, dy = {"up": (0, -travel), "down": (0, travel),
                  "left": (-travel, 0), "right": (travel, 0)}[finger]
        actions: list[dict[str, Any]] = []
        for index, offset in enumerate((-spread // 2, spread // 2), start=1):
            start_x, start_y = ((cx + offset, cy) if finger in ("up", "down")
                                else (cx, cy + offset))
            actions.append({
                "type": "pointer", "id": f"finger{index}",
                "parameters": {"pointerType": "touch"},
                "actions": [
                    {"type": "pointerMove", "duration": 0,
                     "x": start_x, "y": start_y},
                    {"type": "pointerDown", "button": 0},
                    {"type": "pointerMove", "duration": 600,
                     "x": start_x + dx, "y": start_y + dy},
                    {"type": "pointerUp", "button": 0},
                ],
            })
        await self._cmd("POST", "/actions", json_body={"actions": actions})

    async def scroll_to_element(self, chain, ctx, **_) -> None:
        """滑屏直到元素出现（上限 ``ctx.timeout_ms``，每次滑 40% 安全区高度）。"""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(500, ctx.timeout_ms) / 1000
        bounds = await self._gesture_bounds()
        while True:
            try:
                await self._find(chain, ctx, timeout_ms=0)
                return
            except LocatorNotFoundError:
                pass
            if loop.time() >= deadline:
                raise TimeoutError(
                    f"scroll_to_element 超时（{ctx.timeout_ms}ms）：元素 {chain.element_id} 未出现")
            await self._swipe("up", 0.4, bounds=bounds)   # 手指上划 = 看下面
            await asyncio.sleep(0.3)

    async def screenshot(self, chain: LocatorChain | None, ctx: ActionContext, *,
                         path: str | None = None, full_page: bool = False,
                         target: str = "page") -> str:
        if target not in ("page", "element"):
            raise ValueError(f"未知截图目标：{target}（只支持 page / element）")
        if target == "element":
            if chain is None:
                raise ValueError("screenshot(target=element) 需要绑定元素")
            element = await self._find(chain, ctx)
            b64 = await self._cmd(
                "GET", f"/element/{self._element_id(element)}/screenshot")
        else:
            b64 = await self._cmd("GET", "/screenshot")
        os.makedirs(settings.artifacts_dir, exist_ok=True)
        target_path = path or os.path.join(
            settings.artifacts_dir,
            f"shot-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.png")
        with open(target_path, "wb") as fh:
            fh.write(base64.b64decode(str(b64)))
        ctx.artifacts.append({"kind": "SCREENSHOT", "path": target_path,
                              "size_bytes": os.path.getsize(target_path)})
        return target_path

    # ─────────────────────── App 生命周期 ───────────────────────
    def _package(self, app_package: str | None) -> str:
        package = str(app_package or self._app_package or "").strip()
        if not package:
            raise ValidationFailed("未指定 app_package，且执行目标也没有配置",
                                   {"missing": "app_package"})
        return package

    async def _wait_for_package(self, package: str, timeout_s: float = 10.0) -> None:
        """等 App 真的到前台。

        真机实测：``terminate_app`` + ``activate_app`` 后 uiautomator2 的 instrumentation
        需要几百毫秒到几秒才恢复；这期间元素命令会挂到超时（表现为"点一下卡一分钟"）。
        先确认前台包名，把这段抖动挡在第一步动作之外。
        """
        deadline = time.perf_counter() + timeout_s
        while time.perf_counter() < deadline:
            try:
                current = await self._cmd("GET", "/appium/device/current_package",
                                          timeout=5.0)
                if str(current or "") == package:
                    return
            except Exception:                       # 会话刚恢复时命令可能失败，重试即可
                logger.debug("current_package probe failed", exc_info=True)
            await asyncio.sleep(0.3)
        logger.warning("App 未在前台（%s）：超时 %.0fs，后续元素命令可能失败",
                       package, timeout_s, extra={"event": "app.not_ready",
                                                  "app_package": package})

    async def start_app(self, chain, ctx, *, app_package: str | None = None,
                        app_activity: str | None = None) -> None:
        package = self._package(app_package)
        activity = _relative_activity(str(app_activity or self._app_activity or ""), package)
        # 只有相对 Activity（.Xxx）才走 start_activity；全限定名交给 activate_app。
        # 原因：部分 App 的 Activity 命名空间与包名不同（如 debug 包），
        # Appium 的 start_activity 仍会按 appPackage 前缀拼接，导致 "never started"。
        if activity.startswith("."):
            await self._cmd("POST", "/appium/device/start_activity", json_body={
                "appPackage": package, "appActivity": activity,
                "appWaitActivity": activity,
            })
        else:
            await self._cmd("POST", "/appium/device/activate_app",
                            json_body={"appId": package})
        await self._wait_for_package(package)


    async def stop_app(self, chain, ctx, *, app_package: str | None = None) -> None:
        await self._cmd("POST", "/appium/device/terminate_app",
                        json_body={"appId": self._package(app_package), "options": {}})

    async def restart_app(self, chain, ctx, *, app_package: str | None = None) -> None:
        package = self._package(app_package)
        try:
            await self._cmd("POST", "/appium/device/terminate_app",
                            json_body={"appId": package, "options": {}})
        except Exception:                           # 本来就没在跑 → 继续启动
            logger.debug("terminate_app before restart failed", exc_info=True)
        await self.start_app(chain, ctx, app_package=package)

    async def go_home(self, chain, ctx) -> None:
        await self._cmd("POST", "/appium/device/press_keycode",
                        json_body={"keycode": 3})

    async def background_foreground(self, chain, ctx, *, seconds: int = 3) -> None:
        """切后台 N 秒再切回前台（验证"杀后台恢复"这类场景）。"""
        package = self._package(None)
        await self._cmd("POST", "/appium/app/background",
                        json_body={"seconds": max(1, int(seconds))})
        await self._cmd("POST", "/appium/device/activate_app", json_body={"appId": package})

    async def fix_orientation(self, chain, ctx, *, orientation: str = "PORTRAIT") -> None:
        value = str(orientation or "").strip().upper()
        if value not in ("PORTRAIT", "LANDSCAPE"):
            raise ValueError(f"orientation 只能是 PORTRAIT / LANDSCAPE：{orientation}")
        try:
            await self._cmd("POST", "/orientation", json_body={"orientation": value})
        except RuntimeError as exc:
            message = str(exc)
            if "rotation cannot be changed" in message or "Is it locked" in message:
                # 真机实测：系统「自动旋转」关闭、或被测 App 自己锁了方向时，驱动会转不动。
                # 这不是平台 bug，但裸错误没法排障，补一句人话。
                raise RuntimeError(
                    f"设备旋转被锁定，无法切到 {value}：请在设备下拉通知栏打开「自动旋转」，"
                    f"或确认被测 App 没有锁定屏幕方向（原始错误：{message}）"[:600]) from exc
            raise


    # ───────────────────────── 上下文（M4.2）─────────────────────────
    async def get_contexts(self, chain, ctx, *, output_var: str | None = None) -> list:
        contexts = await self._cmd("GET", "/contexts")
        items = [str(item) for item in contexts] if isinstance(contexts, list) else []
        ctx.emit("context.list", contexts=items)
        return ctx.set_var(output_var, items)

    async def switch_to_context(self, chain, ctx, *, context: str) -> None:
        """切换上下文（``NATIVE_APP`` ↔ ``WEBVIEW_*``）。

        先查 ``/contexts`` 再切：不存在的名字直接给"可用列表"，
        比让 Appium 抛出裸错误更好排障。
        """
        name = str(context or "").strip()
        if not name:
            raise ValidationFailed("switch_to_context 需要 context 名称",
                                   {"missing": "context"})
        contexts = await self._cmd("GET", "/contexts")
        available = [str(item) for item in contexts] if isinstance(contexts, list) else []
        if name not in available:
            raise ValidationFailed(
                f"设备上不存在上下文 {name}；当前可用：{available or '无'}",
                {"context": name, "available": available},
            )
        await self._cmd("POST", "/context", json_body={"name": name})
        ctx.emit("context.switch", context=name)


    # ───────────────────────── 诊断 ─────────────────────────
    async def probe_locator(self, chain: LocatorChain, ctx: ActionContext) -> LocatorProbe:
        started = time.perf_counter()
        try:
            using, value = translate_locator(chain.first)
            elements = await self._cmd(
                "POST", "/elements", json_body={"using": using, "value": value})
            count = len(elements) if isinstance(elements, list) else 0
            return LocatorProbe(count=count,
                                elapsed_ms=int((time.perf_counter() - started) * 1000))
        except Exception as exc:
            return LocatorProbe(count=0, error=str(exc)[:300],
                                elapsed_ms=int((time.perf_counter() - started) * 1000))

    async def finalize_diagnostics(self, *, save_trace: bool) -> None:
        """M4.1 不产出 trace/video/HAR；保持基类 no-op 语义。"""
        return None
