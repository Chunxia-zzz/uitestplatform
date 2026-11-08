"""M3.8 网络 mock 与响应检索单测（GAP-09 / spec US1）。

策略：FakePage 记录 route/unroute 调用；收集器直接填 ``adapter._responses``
（与 page 事件解耦）。锁住语义：后写覆盖、解除不存在报错、时间窗过滤、
expect_status 过滤、超时附近邻摘要、用例边界清理。
"""
from __future__ import annotations

import asyncio

import pytest

from app.core.errors import ValidationFailed
from app.engines.adapters.playwright_adapter import (
    PlaywrightAdapter,
    _glob_to_regex,
)
from app.engines.base import ActionContext


class FakePage:
    def __init__(self):
        self.routes: list[tuple[str, object]] = []
        self.unrouted: list[tuple[str, object | None]] = []
        self.unroute_all_called = 0

    def on(self, *args, **kwargs):  # start() 才会调用；单测直接操纵内部状态
        pass

    async def route(self, pattern, handler):
        self.routes.append((pattern, handler))

    async def unroute(self, pattern, handler=None):
        self.unrouted.append((pattern, handler))

    async def unroute_all(self):
        self.unroute_all_called += 1


def net_adapter() -> tuple[PlaywrightAdapter, FakePage]:
    adapter = PlaywrightAdapter()
    page = FakePage()
    adapter._page = page          # type: ignore[assignment]
    adapter._frame_stack = []     # type: ignore[attr-defined]
    return adapter, page


def fill(adapter: PlaywrightAdapter, *records: tuple[float, str, int, str]) -> None:
    adapter._responses.clear()
    for rec in records:
        adapter._responses.append(rec)


# ─────────────────────────── _glob_to_regex ───────────────────────────
def test_glob_double_star_crosses_slash():
    assert _glob_to_regex("**/api/demo").match("http://h.local/api/demo")
    assert _glob_to_regex("**/api/demo").match("https://h.local/v2/api/demo")


def test_glob_single_star_does_not_cross_slash():
    assert _glob_to_regex("*/api/demo").match("http://h/api/demo") is None
    assert _glob_to_regex("http://h/*/demo").match("http://h/a/demo")
    assert _glob_to_regex("http://h/*/demo").match("http://h/a/b/demo") is None


# ─────────────────────────── mock_route / unmock_route ───────────────────────────
@pytest.mark.asyncio
async def test_mock_route_registers_and_overrides():
    adapter, page = net_adapter()
    ctx = ActionContext()
    await adapter.mock_route(None, ctx, pattern="**/api/demo", json={"ok": True})
    await adapter.mock_route(None, ctx, pattern="**/api/demo", json={"ok": 2})
    assert len(page.routes) == 2
    assert ("**/api/demo", page.routes[0][1]) in page.unrouted   # 旧 handler 被摘
    assert len(adapter._active_routes) == 1                      # 同 key 只剩一条


@pytest.mark.asyncio
async def test_mock_route_same_pattern_diff_method_coexists():
    adapter, page = net_adapter()
    ctx = ActionContext()
    await adapter.mock_route(None, ctx, pattern="**/api/x", method="get", status=200)
    await adapter.mock_route(None, ctx, pattern="**/api/x", method="post", status=500)
    assert len(adapter._active_routes) == 2
    assert len(page.routes) == 2


@pytest.mark.asyncio
async def test_unmock_route_unknown_key_fails():
    adapter, _ = net_adapter()
    with pytest.raises(ValidationFailed):
        await adapter.unmock_route(None, ActionContext(), pattern="**/none")


@pytest.mark.asyncio
async def test_unmock_route_exact_key():
    adapter, page = net_adapter()
    ctx = ActionContext()
    await adapter.mock_route(None, ctx, pattern="**/api/demo", method="GET")
    await adapter.unmock_route(None, ctx, pattern="**/api/demo", method="GET")
    assert adapter._active_routes == {}
    assert ("**/api/demo", page.unrouted[0][1]) in page.unrouted


@pytest.mark.asyncio
async def test_reset_case_scope_clears_routes_and_frames():
    adapter, page = net_adapter()
    ctx = ActionContext()
    await adapter.mock_route(None, ctx, pattern="**/api/demo")
    adapter._frame_stack.append(object())
    await adapter.reset_case_scope()
    assert adapter._active_routes == {}
    assert adapter._frame_stack == []
    assert page.unroute_all_called == 1


# ─────────────────────────── wait_for_response ───────────────────────────
@pytest.mark.asyncio
async def test_wait_for_response_hits_latest_since_case_start():
    adapter, _ = net_adapter()
    fill(adapter,
         (1.0, "http://h/api/old", 200, "GET"),        # 用例开始前 → 过滤掉
         (2.0, "http://h/api/demo", 200, "GET"),
         (3.0, "http://h/api/demo", 200, "GET"))       # 最新一条
    ctx = ActionContext(case_started_ts=1.5)
    hit = await adapter.wait_for_response(None, ctx, pattern="**/api/demo",
                                          output_var="resp")
    assert hit["url"] == "http://h/api/demo"
    assert ctx.variables["resp"] == hit


@pytest.mark.asyncio
async def test_wait_for_response_filters_status_and_method():
    adapter, _ = net_adapter()
    fill(adapter, (2.0, "http://h/api/demo", 500, "POST"))
    ctx = ActionContext(case_started_ts=1.0)
    with pytest.raises(ValidationFailed) as ei:
        await adapter.wait_for_response(None, ctx, pattern="**/api/demo",
                                        method="GET", expect_status=200)
    # 近邻摘要要能帮助排查：message 里带 url 与状态
    assert "http://h/api/demo -> 500" in str(ei.value)


@pytest.mark.asyncio
async def test_wait_for_response_respects_case_start_floor():
    """用例开始之前的响应不算（旧用例的响应不污染断言）。"""
    adapter, _ = net_adapter()
    fill(adapter, (1.0, "http://h/api/demo", 200, "GET"))
    ctx = ActionContext(case_started_ts=99.0, timeout_ms=120)
    with pytest.raises(ValidationFailed):
        await adapter.wait_for_response(None, ctx, pattern="**/api/demo")


@pytest.mark.asyncio
async def test_wait_for_response_polls_until_new_record():
    """窗口内新出现的记录（点击后响应）应被轮询命中。"""
    adapter, _ = net_adapter()
    ctx = ActionContext(case_started_ts=1.0, timeout_ms=2000)

    async def late_fill():
        await asyncio.sleep(0.15)
        adapter._responses.append((1.1, "http://h/api/demo", 201, "POST"))

    task = asyncio.create_task(late_fill())
    hit = await adapter.wait_for_response(None, ctx, pattern="**/api/demo",
                                          method="POST", expect_status=201)
    await task
    assert hit["status"] == 201
