"""Appium 适配器（M4.1 / D42）。

设计取舍：**不复用同步的 Appium-Python-Client**，改为 async httpx 直连 Appium REST。
理由（都是实测代价换来的）：
1. 适配器接口本身是 async，直连不需要 ``asyncio.to_thread`` 包一层；
2. ``httpx.AsyncClient(trust_env=False)`` 能绕开 ``HTTP_PROXY`` 代理 localhost 的问题
   —— 本次真机联调时，代理把发往 ``127.0.0.1:4723`` 的定位请求体破坏，
   报 ``FindElementModel: ... 'selector' is not present``；
3. 不引入 selenium 依赖。

M4.1 只实现 11 个核心动作；其余声明动作继续走基类 ``_not_supported()``
（``NotImplementedError`` = 该引擎应支持但尚未实现，FR15）。
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


class AppiumAdapter(EngineAdapter):
    key = "appium"
    platforms = frozenset({Platform.ANDROID, Platform.IOS})

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
        resp = await self._client.request(method, path, json=json_body, timeout=timeout)
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
        """沿回退链找元素；每条候选最多 ``min(总超时, 2500ms)``，末条用满。"""
        timeout = ctx.timeout_ms if timeout_ms is None else max(0, timeout_ms)
        total = len(chain.locators)
        last_error: Exception | None = None
        loop = asyncio.get_running_loop()

        for index, loc in enumerate(chain.locators):
            per_timeout = timeout if index == total - 1 else min(timeout, 2500)
            deadline = loop.time() + per_timeout / 1000
            while True:
                try:
                    using, value = translate_locator(loc)
                    elements = await self._cmd(
                        "POST", "/elements", json_body={"using": using, "value": value})
                    if isinstance(elements, list) and elements:
                        ctx.emit("locator.hit", element_id=chain.element_id,
                                 locator_id=loc.locator_id, fallback_index=index)
                        return elements if multiple else elements[0]
                except Exception as exc:            # 本条失败 → 回退下一条
                    last_error = exc
                if loop.time() >= deadline:
                    break
                await asyncio.sleep(0.2)
            ctx.emit("locator.miss", element_id=chain.element_id,
                     locator_id=loc.locator_id, fallback_index=index,
                     error=str(last_error)[:200] if last_error else "no match")

        raise LocatorNotFoundError(
            f"元素 {chain.element_id} 的全部 {total} 条定位符均未命中：{last_error}",
            {"element_id": chain.element_id, "locators": total},
        )

    @staticmethod
    def _element_id(element: Any) -> str:
        if not isinstance(element, dict):
            raise RuntimeError(f"Appium 返回的元素结构异常：{element!r}"[:300])
        eid = element.get(W3C_ELEMENT_KEY) or element.get("ELEMENT")
        if not eid:
            raise RuntimeError(f"Appium 元素缺少 id：{element!r}"[:300])
        return str(eid)

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
        state = (state or "visible").strip().lower()
        timeout = timeout_ms or ctx.timeout_ms
        if state not in ("visible", "attached"):
            # M4.1 只支持 positive wait；hidden 归 M4.2
            raise UnsupportedActionError(
                f"Appium 适配器暂不支持 wait_element(state={state})",
                {"state": state},
            )
        await self._find(chain, ctx, timeout_ms=timeout)

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
        elements = await self._find(chain, ctx, multiple=True)
        texts: list[str] = []
        for element in elements:
            try:
                text = await self._cmd("GET", f"/element/{self._element_id(element)}/text")
                texts.append(str(text or ""))
            except Exception:                       # 单个元素取文本失败不影响整体
                texts.append("")
        return ctx.set_var(output_var, texts)

    async def screenshot(self, chain: LocatorChain | None, ctx: ActionContext, *,
                         path: str | None = None, full_page: bool = False,
                         target: str = "page") -> str:
        if target not in ("page", "element"):
            raise ValueError(f"未知截图目标：{target}（只支持 page / element）")
        if target == "element":
            raise UnsupportedActionError(
                "Appium 元素级截图 M4.2 实现；当前请用 target=page",
                {"target": target},
            )
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
