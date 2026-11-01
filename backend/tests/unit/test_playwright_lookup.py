"""Playwright 存在性判断必须走回退链（M3.2 修正）。

背景：``check_exists`` 原先只 ``_locator(chain.first).count()``。演示数据里
"登录按钮"的首选定位符是故意写错的（用来验证回退链），结果 ``assert_visible``
一律判为不可见 —— 断言绕过了平台最核心的能力。这里锁住修复后的语义。
"""
from __future__ import annotations

import pytest

from app.engines.adapters.playwright_adapter import PlaywrightAdapter
from app.engines.base import ActionContext, Locator, LocatorChain


class FakeLocator:
    def __init__(self, count: int):
        self._count = count

    async def count(self) -> int:
        return self._count


def chain(*counts: int) -> LocatorChain:
    return LocatorChain.of(1, [
        Locator(type="css", value=f"#x{index}", locator_id=index + 1)
        for index in range(len(counts))
    ])


def adapter_with(counts: list[int]) -> PlaywrightAdapter:
    adapter = PlaywrightAdapter()
    mapping = {index + 1: value for index, value in enumerate(counts)}
    adapter._locator = lambda loc: FakeLocator(mapping[loc.locator_id])  # type: ignore[method-assign]
    return adapter


@pytest.mark.asyncio
async def test_exists_when_first_locator_hits():
    assert await adapter_with([1, 0]).check_exists(chain(1, 0), ActionContext()) is True


@pytest.mark.asyncio
async def test_exists_when_only_fallback_hits():
    """首选 0 命中、第二条命中 → 元素存在。"""
    assert await adapter_with([0, 3]).check_exists(chain(0, 3), ActionContext()) is True


@pytest.mark.asyncio
async def test_not_exists_when_all_miss():
    assert await adapter_with([0, 0]).check_exists(chain(0, 0), ActionContext()) is False


@pytest.mark.asyncio
async def test_broken_locator_is_skipped():
    """某条定位符语法非法（抛异常）不应让整条链判为不存在。"""
    adapter = PlaywrightAdapter()

    def _locator(loc):
        if loc.locator_id == 1:
            raise ValueError("bad selector")
        return FakeLocator(2)

    adapter._locator = _locator  # type: ignore[method-assign]
    assert await adapter.check_exists(chain(0, 2), ActionContext()) is True


@pytest.mark.asyncio
async def test_output_var_is_set():
    ctx = ActionContext()
    await adapter_with([0, 1]).check_exists(chain(0, 1), ctx, output_var="present")
    assert ctx.variables["present"] is True
