"""Appium 适配器（M4.1 / D42）：caps / 定位映射 / 回退链 / 元素命令 / 截图。"""
from __future__ import annotations

import base64

import httpx
import pytest

from app.core.errors import LocatorNotFoundError, ValidationFailed
from app.engines.adapters import appium_adapter
from app.engines.adapters.appium_adapter import AppiumAdapter, translate_locator
from app.engines.base import ActionContext, Locator, LocatorChain, SessionConfig


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
        if path.endswith("/current_package"):
            return httpx.Response(200, json={"value": "com.demo.app"})
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


# ═════════════════════ M4.2：手势 / 滑动 / 上下文 ═════════════════════
import json  # noqa: E402

from app.core.errors import UnsupportedActionError  # noqa: E402


def _base_handler(calls, *, element="eid-1", rect=None, window=None,
                  contexts=("NATIVE_APP",), elements=None, extra=None):
    """最小 Appium 路由桩：session / elements / rect / window / contexts / text / displayed。"""
    rect = rect or {"x": 100, "y": 900, "width": 400, "height": 1000}
    window = window or {"x": 0, "y": 0, "width": 1240, "height": 2772}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = request.content.decode() or "{}"
        calls.append((request.method, path, body))
        if path == "/session":
            return httpx.Response(200, json={"value": {"sessionId": "sid-1"}})
        if extra is not None:                   # 先给测试留覆盖点，再走默认路由
            response = extra(request, path, body)
            if response is not None:
                return response
        if path.endswith("/elements"):
            value = elements if elements is not None else [
                {appium_adapter.W3C_ELEMENT_KEY: element}]
            return httpx.Response(200, json={"value": value})
        if path.endswith("/window/rect"):
            return httpx.Response(200, json={"value": window})
        if path.endswith("/rect"):
            return httpx.Response(200, json={"value": rect})
        if path.endswith("/current_package"):
            return httpx.Response(200, json={"value": "com.demo.app"})
        if path.endswith("/contexts"):
            return httpx.Response(200, json={"value": list(contexts)})
        if path.endswith("/displayed"):
            return httpx.Response(200, json={"value": True})
        if path.endswith("/text"):
            return httpx.Response(200, json={"value": "item"})
        if path.endswith("/screenshot"):
            return httpx.Response(200, json={"value": base64.b64encode(b"png").decode()})
        return httpx.Response(200, json={"value": None})
    return handler


async def _prepare(mock_transport, handler) -> AppiumAdapter:
    mock_transport(handler)
    adapter = AppiumAdapter()
    await adapter.start(_config())
    return adapter


def _gestures(calls) -> list[tuple[str, dict]]:
    """从 /execute/sync 调用里抽出 (mobile: 命令名, 参数)。"""
    out = []
    for _method, path, body in calls:
        if path.endswith("/execute/sync"):
            payload = json.loads(body)
            args = payload.get("args") or [{}]
            out.append((payload["script"], args[0]))
    return out


@pytest.mark.asyncio
async def test_long_press_uses_long_click_gesture(mock_transport):
    calls = []
    adapter = await _prepare(mock_transport, _base_handler(calls))
    await adapter.long_press(_chain(("text", "WLAN")), ActionContext(), duration_ms=1500)
    script, params = _gestures(calls)[0]
    assert script == "mobile: longClickGesture"
    assert params["elementId"] == "eid-1" and params["duration"] == 1500
    await adapter.stop()


@pytest.mark.asyncio
async def test_double_click_and_coordinate_click(mock_transport):
    calls = []
    adapter = await _prepare(mock_transport, _base_handler(calls))
    await adapter.double_click(_chain(("text", "WLAN")), ActionContext())
    await adapter.coordinate_click(None, ActionContext(), x=620, y=1386)
    gestures = _gestures(calls)
    assert gestures[0] == ("mobile: doubleClickGesture", {"elementId": "eid-1"})
    assert gestures[1] == ("mobile: clickGesture", {"x": 620, "y": 1386})
    await adapter.stop()


@pytest.mark.asyncio
async def test_drag_requires_target_element_id(mock_transport):
    adapter = await _prepare(mock_transport, _base_handler([]))
    with pytest.raises(ValueError, match="target_element_id"):
        await adapter.drag(_chain(("text", "源")), ActionContext())
    await adapter.stop()


@pytest.mark.asyncio
async def test_drag_without_resolved_chain_raises(mock_transport):
    adapter = await _prepare(mock_transport, _base_handler([]))
    with pytest.raises(ValueError, match="未预解析"):
        await adapter.drag(_chain(("text", "源")), ActionContext(), target_element_id=9)
    await adapter.stop()


@pytest.mark.asyncio
async def test_drag_uses_target_center_and_speed(mock_transport):
    calls = []
    rects = {"eid-1": {"x": 100, "y": 900, "width": 400, "height": 100},
             "eid-2": {"x": 100, "y": 1500, "width": 400, "height": 100}}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = request.content.decode() or "{}"
        calls.append((request.method, path, body))
        if path == "/session":
            return httpx.Response(200, json={"value": {"sessionId": "sid-1"}})
        if path.endswith("/elements"):
            eid = "eid-2" if "目标" in body else "eid-1"
            return httpx.Response(200, json={"value": [
                {appium_adapter.W3C_ELEMENT_KEY: eid}]})
        if path.endswith("/rect"):
            for eid, rect in rects.items():
                if f"/element/{eid}/" in path:
                    return httpx.Response(200, json={"value": rect})
        return httpx.Response(200, json={"value": None})

    adapter = await _prepare(mock_transport, handler)
    ctx = ActionContext()
    ctx.resolved_chains[2] = _chain(("text", "目标"))
    await adapter.drag(_chain(("text", "源")), ctx, target_element_id=2, duration_ms=600)
    script, params = _gestures(calls)[0]
    assert script == "mobile: dragGesture"
    assert params["elementId"] == "eid-1"
    assert (params["endX"], params["endY"]) == (300, 1550)   # 目标元素中心
    assert 900 <= params["speed"] <= 1100                    # 600px / 0.6s ≈ 1000 px/s
    await adapter.stop()


@pytest.mark.asyncio
async def test_element_scroll_maps_content_direction_to_finger(mock_transport):
    calls = []
    adapter = await _prepare(mock_transport, _base_handler(calls, rect={
        "x": 40, "y": 900, "width": 400, "height": 1000}))
    await adapter.element_scroll(_chain(("text", "列表")), ActionContext(),
                                 direction="down", distance=300)
    script, params = _gestures(calls)[0]
    assert script == "mobile: swipeGesture"
    # 内容向下 → 手指向上
    assert params["direction"] == "up" and params["percent"] == 0.3
    assert params["elementId"] == "eid-1"
    await adapter.stop()


@pytest.mark.asyncio
async def test_element_scroll_percent_is_clamped(mock_transport):
    calls = []
    adapter = await _prepare(mock_transport, _base_handler(calls, rect={
        "x": 40, "y": 900, "width": 400, "height": 100}))
    await adapter.element_scroll(_chain(("text", "列表")), ActionContext(),
                                 direction="down", distance=5000)
    _, params = _gestures(calls)[0]
    assert params["percent"] == 0.95        # 300% → 上限
    await adapter.stop()


@pytest.mark.asyncio
async def test_page_swipe_uses_safe_bounds_and_finger_direction(mock_transport):
    """整屏手势必须内缩：从屏幕最顶部下滑会拉下系统通知栏（真机踩过）。"""
    calls = []
    adapter = await _prepare(mock_transport, _base_handler(calls))
    await adapter.page_swipe(None, ActionContext(), direction="up", distance=600)
    _, params = _gestures(calls)[0]
    assert params["direction"] == "up"
    inset = max(120, int(2772 * 0.08))            # 221
    assert (params["left"], params["top"]) == (inset, inset)
    assert (params["width"], params["height"]) == (1240 - inset * 2, 2772 - inset * 2)
    assert params["percent"] == round(600 / (2772 - inset * 2), 3)
    await adapter.stop()


@pytest.mark.asyncio
async def test_page_swipe_respects_gesture_inset_option(mock_transport):
    calls = []
    adapter = await _prepare(mock_transport, _base_handler(calls))
    adapter._options = {"gesture_inset_px": 60}
    await adapter.page_swipe(None, ActionContext(), direction="down", distance=300)
    _, params = _gestures(calls)[0]
    assert (params["left"], params["top"], params["height"]) == (60, 60, 2772 - 120)
    await adapter.stop()



@pytest.mark.asyncio
async def test_swipe_up_and_down_delegate_to_page_swipe(mock_transport):
    calls = []
    adapter = await _prepare(mock_transport, _base_handler(calls))
    await adapter.swipe_up(None, ActionContext(), distance=500)
    await adapter.swipe_down(None, ActionContext(), distance=500)
    directions = [params["direction"] for _, params in _gestures(calls)]
    assert directions == ["up", "down"]
    await adapter.stop()


@pytest.mark.asyncio
async def test_invalid_direction_rejected(mock_transport):
    adapter = await _prepare(mock_transport, _base_handler([]))
    with pytest.raises(ValueError, match="direction"):
        await adapter.page_swipe(None, ActionContext(), direction="sideways")
    await adapter.stop()


@pytest.mark.asyncio
async def test_multi_finger_swipe_sends_two_pointers(mock_transport):
    calls = []
    adapter = await _prepare(mock_transport, _base_handler(calls))
    await adapter.multi_finger_swipe(None, ActionContext(), direction="up", distance=400)
    action_calls = [c for c in calls if c[1].endswith("/actions")]
    assert len(action_calls) == 1
    payload = json.loads(action_calls[0][2])
    pointers = payload["actions"]
    assert [p["id"] for p in pointers] == ["finger1", "finger2"]
    assert all(p["parameters"]["pointerType"] == "touch" for p in pointers)
    for pointer in pointers:
        steps = pointer["actions"]
        assert [s["type"] for s in steps] == [
            "pointerMove", "pointerDown", "pointerMove", "pointerUp"]
        start, end = steps[0], steps[2]
        assert end["y"] - start["y"] == -400          # 手指上划
        assert end["duration"] == 600
    # 两指水平错开
    assert pointers[0]["actions"][0]["x"] != pointers[1]["actions"][0]["x"]
    await adapter.stop()


@pytest.mark.asyncio
async def test_scroll_to_element_swipes_until_found(mock_transport):
    calls = []
    state = {"n": 0}

    def extra(request, path, body):
        if path.endswith("/elements"):
            state["n"] += 1
            if state["n"] == 1:
                return httpx.Response(200, json={"value": []})
            return httpx.Response(200, json={"value": [
                {appium_adapter.W3C_ELEMENT_KEY: "eid-9"}]})
        return None

    adapter = await _prepare(mock_transport, _base_handler(calls, extra=extra))
    await adapter.scroll_to_element(_chain(("text", "关于手机")), ActionContext(timeout_ms=3000))
    assert any(script == "mobile: swipeGesture" for script, _ in _gestures(calls))
    await adapter.stop()


@pytest.mark.asyncio
async def test_scroll_to_element_timeout(mock_transport):
    calls = []
    adapter = await _prepare(mock_transport, _base_handler(calls, elements=[]))
    with pytest.raises(TimeoutError, match="scroll_to_element"):
        await adapter.scroll_to_element(_chain(("text", "永远不会出现")),
                                        ActionContext(timeout_ms=50))
    await adapter.stop()


@pytest.mark.asyncio
async def test_background_foreground(mock_transport):
    calls = []
    adapter = await _prepare(mock_transport, _base_handler(calls))
    await adapter.background_foreground(None, ActionContext(), seconds=2)
    background = [c for c in calls if c[1].endswith("/appium/app/background")]
    assert background and json.loads(background[0][2])["seconds"] == 2
    assert any(c[1].endswith("/appium/device/activate_app") and "com.demo.app" in c[2]
               for c in calls)
    await adapter.stop()


@pytest.mark.asyncio
async def test_fix_orientation(mock_transport):
    calls = []
    adapter = await _prepare(mock_transport, _base_handler(calls))
    await adapter.fix_orientation(None, ActionContext(), orientation="landscape")
    orient = [c for c in calls if c[1].endswith("/orientation")]
    assert json.loads(orient[0][2])["orientation"] == "LANDSCAPE"
    with pytest.raises(ValueError, match="PORTRAIT"):
        await adapter.fix_orientation(None, ActionContext(), orientation="SIDEWAYS")
    await adapter.stop()


@pytest.mark.asyncio
async def test_get_contexts_stores_variable(mock_transport):
    calls = []
    events = []
    adapter = await _prepare(mock_transport, _base_handler(
        calls, contexts=("NATIVE_APP", "WEBVIEW_chrome")))
    ctx = ActionContext(log=lambda e, p: events.append((e, p)))
    contexts = await adapter.get_contexts(None, ctx, output_var="ctxs")
    assert contexts == ["NATIVE_APP", "WEBVIEW_chrome"]
    assert ctx.variables["ctxs"] == contexts
    assert events[0][0] == "context.list"
    await adapter.stop()


@pytest.mark.asyncio
async def test_switch_to_context_ok(mock_transport):
    calls = []
    adapter = await _prepare(mock_transport, _base_handler(
        calls, contexts=("NATIVE_APP", "WEBVIEW_chrome")))
    await adapter.switch_to_context(None, ActionContext(), context="WEBVIEW_chrome")
    switch = [c for c in calls if c[0] == "POST" and c[1].endswith("/context")]
    assert json.loads(switch[0][2])["name"] == "WEBVIEW_chrome"
    await adapter.stop()


@pytest.mark.asyncio
async def test_switch_to_unknown_context_reports_available(mock_transport):
    adapter = await _prepare(mock_transport, _base_handler(
        [], contexts=("NATIVE_APP",)))
    with pytest.raises(ValidationFailed, match="WEBVIEW_x"):
        await adapter.switch_to_context(None, ActionContext(), context="WEBVIEW_x")
    await adapter.stop()


@pytest.mark.asyncio
async def test_wait_element_hidden_returns_when_gone(mock_transport):
    adapter = await _prepare(mock_transport, _base_handler([], elements=[]))
    await adapter.wait_element(_chain(("text", "加载中")), ActionContext(timeout_ms=500),
                               state="hidden")
    await adapter.stop()


@pytest.mark.asyncio
async def test_wait_element_hidden_times_out(mock_transport):
    adapter = await _prepare(mock_transport, _base_handler([]))
    with pytest.raises(TimeoutError, match="消失"):
        await adapter.wait_element(_chain(("text", "一直存在")),
                                   ActionContext(timeout_ms=100), state="hidden")
    await adapter.stop()


@pytest.mark.asyncio
async def test_wait_element_unknown_state(mock_transport):
    adapter = await _prepare(mock_transport, _base_handler([]))
    with pytest.raises(ValidationFailed, match="state"):
        await adapter.wait_element(_chain(("text", "x")), ActionContext(), state="blinking")
    await adapter.stop()


@pytest.mark.asyncio
async def test_element_screenshot_uses_element_endpoint(mock_transport, tmp_path):
    calls = []
    adapter = await _prepare(mock_transport, _base_handler(calls))
    ctx = ActionContext()
    out = str(tmp_path / "el.png")
    await adapter.screenshot(_chain(("text", "WLAN")), ctx, path=out, target="element")
    assert open(out, "rb").read() == b"png"
    assert any(c[1].endswith("/element/eid-1/screenshot") for c in calls)
    assert ctx.artifacts[0]["kind"] == "SCREENSHOT"
    await adapter.stop()


@pytest.mark.asyncio
async def test_element_screenshot_without_chain_raises(mock_transport):
    adapter = await _prepare(mock_transport, _base_handler([]))
    with pytest.raises(ValueError, match="绑定元素"):
        await adapter.screenshot(None, ActionContext(), target="element")
    await adapter.stop()


@pytest.mark.asyncio
async def test_element_list_matches_playwright_shape(mock_transport):
    elements = [{appium_adapter.W3C_ELEMENT_KEY: "eid-1"},
                {appium_adapter.W3C_ELEMENT_KEY: "eid-2"}]
    adapter = await _prepare(mock_transport, _base_handler([], elements=elements))
    items = await adapter.element_list(_chain(("class_name", "android.widget.TextView")),
                                       ActionContext(), output_var="rows")
    assert items == [{"index": 0, "text": "item", "visible": True},
                     {"index": 1, "text": "item", "visible": True}]
    await adapter.stop()


@pytest.mark.asyncio
async def test_hover_and_select_option_are_platform_inapplicable(mock_transport):
    adapter = await _prepare(mock_transport, _base_handler([]))
    with pytest.raises(UnsupportedActionError, match="hover"):
        await adapter.hover(_chain(("text", "x")), ActionContext())
    with pytest.raises(UnsupportedActionError, match="select_option"):
        await adapter.select_option(_chain(("text", "x")), ActionContext(), value="a")
    await adapter.stop()


@pytest.mark.asyncio
async def test_fix_orientation_explains_locked_rotation(mock_transport):
    """真机踩过：系统「自动旋转」关闭时驱动转不动，裸错误没法排障。"""
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/session":
            return httpx.Response(200, json={"value": {"sessionId": "sid-1"}})
        if path.endswith("/orientation"):
            return httpx.Response(400, json={"value": {
                "error": "invalid element state",
                "message": "Screen rotation cannot be changed to ROTATION_270 after 2000ms. "
                           "Is it locked programmatically?",
            }})
        return httpx.Response(200, json={"value": None})

    adapter = await _prepare(mock_transport, handler)
    with pytest.raises(RuntimeError, match="自动旋转"):
        await adapter.fix_orientation(None, ActionContext(), orientation="LANDSCAPE")
    await adapter.stop()


@pytest.mark.asyncio
async def test_find_gives_up_after_transient_driver_failures(mock_transport):
    """驱动连续 500（App 启动瞬间）时不能死等到超时预算用尽 —— 真机一次要 3 秒。"""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        calls.append((request.method, path))
        if path == "/session":
            return httpx.Response(200, json={"value": {"sessionId": "sid-1"}})
        if path.endswith("/elements"):
            return httpx.Response(500, json={"value": {
                "error": "unknown error",
                "message": "An unknown server-side error occurred. "
                           "Original error: Could not proxy command to the remote server",
            }})
        return httpx.Response(200, json={"value": None})

    adapter = await _prepare(mock_transport, handler)
    t0 = __import__("time").perf_counter()
    with pytest.raises(LocatorNotFoundError):
        await adapter.click(_chain(("text", "自选")), ActionContext(timeout_ms=15000))
    elapsed = __import__("time").perf_counter() - t0
    element_calls = [c for c in calls if c[1].endswith("/elements")]
    assert len(element_calls) == appium_adapter.MAX_TRANSIENT_RETRIES
    assert elapsed < 5, f"应该在限次后立即放弃，实际 {elapsed:.1f}s"
    await adapter.stop()


@pytest.mark.asyncio
async def test_request_has_hard_timeout(mock_transport):
    """httpx 的 read timeout 挡不住慢速滴流，_request 必须再兜一层硬上限。"""
    import asyncio

    class _SlowClient:
        async def request(self, *a, **kw):          # noqa: D401 - 测试桩
            await asyncio.sleep(3)
            raise AssertionError("不应该走到这里")

    mock_transport(_session_handler([]))
    adapter = AppiumAdapter()
    adapter._client = _SlowClient()
    adapter._session_id = "sid-1"
    with pytest.raises(RuntimeError, match="硬上限"):
        await adapter._request("GET", "/screenshot", timeout=0.2)
