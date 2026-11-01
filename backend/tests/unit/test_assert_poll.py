"""断言轮询（M3.2 / GAP-03 / Q-05）。

语义：在 ``ctx.timeout_ms`` 窗口内轮询，**不设固定重试次数**。
这些用例用"按序列返回的假适配器"验证：轮询到成功为止 / 超时才失败 / 超时为 0 只试一次。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.core.errors import ValidationFailed
from app.engines.actions import BUILTIN_HANDLERS
from app.engines.base import ActionContext


class SequenceAdapter:
    """按预置序列返回 ``check_exists``；序列用完后重复最后一个值。"""

    def __init__(self, sequence: list[bool]):
        self.sequence = sequence
        self.calls = 0

    async def check_exists(self, chain, ctx, **kwargs) -> bool:
        index = min(self.calls, len(self.sequence) - 1)
        self.calls += 1
        return self.sequence[index]


@pytest.fixture(autouse=True)
def fast_poll(monkeypatch):
    monkeypatch.setattr(settings, "assert_poll_interval_ms", 10)


def _ctx(timeout_ms: int) -> ActionContext:
    return ActionContext(timeout_ms=timeout_ms)


CHAIN = SimpleNamespace(element_id=42)


@pytest.mark.asyncio
async def test_assert_visible_passes_immediately():
    adapter = SequenceAdapter([True])
    await BUILTIN_HANDLERS["assert_visible"](adapter, CHAIN, _ctx(1000), {})
    assert adapter.calls == 1


@pytest.mark.asyncio
async def test_assert_visible_polls_until_visible():
    adapter = SequenceAdapter([False, False, True])
    await BUILTIN_HANDLERS["assert_visible"](adapter, CHAIN, _ctx(2000), {})
    assert adapter.calls == 3


@pytest.mark.asyncio
async def test_assert_visible_times_out():
    adapter = SequenceAdapter([False])
    with pytest.raises(AssertionError) as exc:
        await BUILTIN_HANDLERS["assert_visible"](adapter, CHAIN, _ctx(80), {})
    assert "不可见" in str(exc.value)
    assert adapter.calls >= 2                    # 真的轮询了，不是只试一次


@pytest.mark.asyncio
async def test_zero_timeout_tries_exactly_once():
    adapter = SequenceAdapter([False])
    with pytest.raises(AssertionError):
        await BUILTIN_HANDLERS["assert_visible"](adapter, CHAIN, _ctx(0), {})
    assert adapter.calls == 1


@pytest.mark.asyncio
async def test_assert_not_exists_polls_until_gone():
    adapter = SequenceAdapter([True, True, False])   # 前两次仍在，第三次消失
    await BUILTIN_HANDLERS["assert_not_exists"](adapter, CHAIN, _ctx(2000), {})
    assert adapter.calls == 3


@pytest.mark.asyncio
async def test_assert_not_exists_fails_when_still_present():
    adapter = SequenceAdapter([True])
    with pytest.raises(AssertionError) as exc:
        await BUILTIN_HANDLERS["assert_not_exists"](adapter, CHAIN, _ctx(60), {})
    assert "仍然存在" in str(exc.value)


@pytest.mark.asyncio
async def test_assert_visible_without_engine_is_rejected():
    with pytest.raises(ValidationFailed):
        await BUILTIN_HANDLERS["assert_visible"](None, CHAIN, _ctx(100), {})
