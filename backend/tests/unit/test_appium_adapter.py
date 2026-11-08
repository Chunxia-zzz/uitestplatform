"""Appium 适配器（M4.1 / D42）：caps / 定位映射 / 回退链 / 元素命令 / 截图。"""
from __future__ import annotations

import base64

import httpx
import pytest

from app.core.errors import LocatorNotFoundError, ValidationFailed
from app.engines.base import ActionContext, Locator, LocatorChain, SessionConfig
from app.engines.adapters import appium_adapter
from app.engines.adapters.appium_adapter import AppiumAdapter, translate_locator


def _config(**options) -> SessionConfig:
    opts = {"udid": "3149dfe3", "app_package": "com.demo.app"}
    opts.update(options)
    return SessionConfig(platform="ANDROID", engine_key="appium", options=opts)


def _chain(*pairs) -> LocatorChain:
    return LocatorChain.of(1, [Locator(t, v, locator_id=i + 1)
                               for i, (t, v) in enumerate(pairs)])


@pytest.fixture
def mock_transport(monkeypatch):
    """把适配器内的 httpx.AsyncClient 换成 MockTransport 版本。"""
    def install(handler):
        transport = httpx.MockTransport(handler)
        real_client = httpx.AsyncClient

        class _Client(real_client):
            def __init__(self, *a, **kw):
                kw["transport"] = transport
                super().__init__(*a, **kw)
        monkeypatch.setattr(appium_adapter.httpx, "AsyncClient", _Client)
    return install


def _session_handler(calls: list, *, elements=None, screenshot_b64="ZmFrZQ=="):
    """最小 Appium 路由：session / elements / click / screenshot / delete。"""
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        calls.append((request.method, path, request.content.decode() or "{}"))
        if path == "/session":
            return httpx.Response(200, json={"value": {
                "sessionId": "sid-1", "capabilities": {"deviceModel": "PJA110"}}})
        if path.endswith("/elements"):
            using = request.read().decode()
            if elements is None:
                return httpx.Response(200, json={"value": []})
            if isinstance(elements, dict):
                return httpx.Response(200, json={"value": elements.get(
                    "id" if '"id"' in using else "other", [])})
            return httpx.Response(200, json={"value": elements})
        if path.endswith("/click") or path.endswith("/value") or path.endswith("/clear"):
            return httpx.Response(200, json={"value": None})
        if path.endswith("/screenshot"):
            return httpx.Response(200, json={"value": screenshot_b64})
        if request.method == "DELETE":
            return httpx.Response(200, json={"value": None})
        return httpx.Response(200, json={"value": None})
    return handler


@pytest.mark.asyncio
async def test_start_builds_caps(mock_transport):
    calls = []
    mock_transport(_session_handler(calls))
    adapter = AppiumAdapter()
    await adapter.start(_config(app_activity=".MainActivity", platform_version="16",
                                no_reset=False, new_command_timeout=90))
    assert adapter.session_id() == "sid-1"
    body = calls[0][2]
    for expected in ('"platformName":"Android"', '"appium:automationName":"UiAutomator2"',
                     '"appium:udid":"3149dfe3"', '"appium:appPackage":"com.demo.app"',
                     '"appium:appActivity":".MainActivity"', '"appium:platformVersion":"16"',
                     '"appium:noReset":false', '"appium:newCommandTimeout":90'):
        assert expected in body
    await adapter.stop()


@pytest.mark.asyncio
async def test_start_requires_udid(mock_transport):
    mock_transport(_session_handler([]))
    with pytest.raises(ValidationFailed, match="udid"):
        await AppiumAdapter().start(_config(udid=""))


@pytest.mark.asyncio
async def test_start_requires_package(mock_transport):
    mock_transport(_session_handler([]))
    with pytest.raises(ValidationFailed, match="app_package"):
        await AppiumAdapter().start(_config(app_package=""))


@pytest.mark.parametrize("loc_type,value,using,expected", [
    ("resource_id", "com.demo:id/btn", "id", "com.demo:id/btn"),
    ("accessibility_id", "login", "accessibility id", "login"),
    ("text", '登 录"x', "-android uiautomator",
     'new UiSelector().text("登 录\\"x")'),
    ("text_contains", "登录", "-android uiautomator",
     'new UiSelector().textContains("登录")'),
    ("class_name", "android.widget.Button", "class name", "android.widget.Button"),
    ("xpath", "//*[@text='登录']", "xpath", "//*[@text='登录']"),
    ("uiautomator", "new UiSelector().clickable(true)", "-android uiautomator",
     "new UiSelector().clickable(true)"),
])
def test_translate_locator(loc_type, value, using, expected):
    assert translate_locator(Locator(loc_type, value)) == (using, expected)


@pytest.mark.asyncio
async def test_fallback_chain_hits_second(mock_transport):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = request.content.decode() or "{}"
        calls.append((request.method, path, body))
        if path == "/session":
            return httpx.Response(200, json={"value": {"sessionId": "sid-1"}})
        if path.endswith("/elements"):
            # 首条 resource_id（using=id）故意不命中，第二条 text 命中
            if '"using": "id"' in body or '"using":"id"' in body:
                return httpx.Response(200, json={"value": []})
            return httpx.Response(200, json={"value": [
                {appium_adapter.W3C_ELEMENT_KEY: "eid-2"}]})
        return httpx.Response(200, json={"value": None})

    mock_transport(handler)
    adapter = AppiumAdapter()
    await adapter.start(_config())
    events = []
    ctx = ActionContext(timeout_ms=150, log=lambda e, p: events.append((e, p)))
    chain = _chain(("resource_id", "com.demo:id/wrong"), ("text", "自选"))
    await adapter.click(chain, ctx)
    hit = [p for e, p in events if e == "locator.hit"][0]
    assert hit["fallback_index"] == 1 and hit["locator_id"] == 2
    assert any(c[1].endswith("/element/eid-2/click") for c in calls)
    await adapter.stop()


@pytest.mark.asyncio
async def test_all_locators_miss(mock_transport):
    mock_transport(_session_handler([]))
    adapter = AppiumAdapter()
    await adapter.start(_config())
    with pytest.raises(LocatorNotFoundError):
        await adapter.click(_chain(("text", "不存在")), ActionContext(timeout_ms=50))
    await adapter.stop()


@pytest.mark.asyncio
async def test_check_exists_false_does_not_raise(mock_transport):
    mock_transport(_session_handler([]))
    adapter = AppiumAdapter()
    await adapter.start(_config())
    assert await adapter.check_exists(_chain(("text", "不存在")),
                                      ActionContext(timeout_ms=50)) is False
    await adapter.stop()


@pytest.mark.asyncio
async def test_get_text_and_attribute(mock_transport):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/session":
            return httpx.Response(200, json={"value": {"sessionId": "sid-1"}})
        if path.endswith("/elements"):
            return httpx.Response(200, json={"value": [
                {appium_adapter.W3C_ELEMENT_KEY: "eid-1"}]})
        if path.endswith("/text"):
            return httpx.Response(200, json={"value": " 735.290 "})
        if "/attribute/" in path:
            return httpx.Response(200, json={"value": "true"})
        return httpx.Response(200, json={"value": None})
    mock_transport(handler)
    adapter = AppiumAdapter()
    await adapter.start(_config())
    ctx = ActionContext(timeout_ms=100)
    assert await adapter.get_text(_chain(("text", "价格")), ctx) == "735.290"
    assert await adapter.get_attribute(_chain(("text", "价格")), ctx, name="clickable") == "true"
    await adapter.stop()


@pytest.mark.asyncio
async def test_start_app_uses_target_package(mock_transport):
    calls = []
    mock_transport(_session_handler(calls))
    adapter = AppiumAdapter()
    await adapter.start(_config())
    await adapter.start_app(None, ActionContext())
    assert any("activate_app" in c[1] and "com.demo.app" in c[2] for c in calls)
    await adapter.stop()


def test_relative_activity_normalization():
    from app.engines.adapters.appium_adapter import _relative_activity
    assert _relative_activity("com.demo.app.MainActivity", "com.demo.app") == ".MainActivity"
    assert _relative_activity(".MainActivity", "com.demo.app") == ".MainActivity"
    assert _relative_activity("com.other.Main", "com.demo.app") == "com.other.Main"
    assert _relative_activity("", "com.demo.app") == ""


@pytest.mark.asyncio
async def test_start_app_with_relative_activity_uses_start_activity(mock_transport):
    calls = []
    mock_transport(_session_handler(calls))
    adapter = AppiumAdapter()
    await adapter.start(_config(app_activity=".MainActivity"))
    await adapter.start_app(None, ActionContext())
    start_calls = [c for c in calls if c[1].endswith("/appium/device/start_activity")]
    assert start_calls and '".MainActivity"' in start_calls[0][2]
    await adapter.stop()


@pytest.mark.asyncio
async def test_screenshot_writes_artifact(mock_transport, tmp_path):
    mock_transport(_session_handler([], screenshot_b64=base64.b64encode(b"png-bytes").decode()))
    adapter = AppiumAdapter()
    await adapter.start(_config())
    ctx = ActionContext()
    out = str(tmp_path / "shot.png")
    assert await adapter.screenshot(None, ctx, path=out) == out
    assert open(out, "rb").read() == b"png-bytes"
    assert ctx.artifacts[0]["kind"] == "SCREENSHOT"
    await adapter.stop()


@pytest.mark.asyncio
async def test_stop_is_idempotent(mock_transport):
    calls = []
    mock_transport(_session_handler(calls))
    adapter = AppiumAdapter()
    await adapter.start(_config())
    await adapter.stop()
    await adapter.stop()
    assert sum(1 for c in calls if c[0] == "DELETE") == 1
    assert adapter.session_id() is None
