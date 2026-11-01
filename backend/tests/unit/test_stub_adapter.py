"""桩适配器语义分界（FR15）：NotImplementedError vs UnsupportedActionError。"""
from __future__ import annotations

import pytest

from app.core.errors import UnsupportedActionError
from app.engines.adapters.stub_adapter import AppiumAdapter, UIAutomator2Adapter
from app.engines.base import ActionContext, Locator, LocatorChain


def chain() -> LocatorChain:
    return LocatorChain.of(1, [Locator(type="resource_id", value="com.x:id/y", locator_id=1)])


@pytest.mark.asyncio
async def test_declared_action_raises_not_implemented():
    """矩阵声明支持 → 未实现 → NotImplementedError（M4 工作量可追踪）。"""
    adapter = AppiumAdapter()
    with pytest.raises(NotImplementedError):
        await adapter.click(chain(), ActionContext())


@pytest.mark.asyncio
async def test_undeclared_action_raises_unsupported():
    """矩阵未声明 → 本来就不支持 → UnsupportedActionError。"""
    adapter = AppiumAdapter()
    with pytest.raises(UnsupportedActionError):
        await adapter.navigate(chain(), ActionContext(), url="https://x")
    with pytest.raises(UnsupportedActionError):
        await adapter.upload_file(chain(), ActionContext(), file_path="a.txt")


@pytest.mark.asyncio
async def test_u2_rejects_appium_only_action():
    adapter = UIAutomator2Adapter()
    with pytest.raises(UnsupportedActionError):
        await adapter.get_contexts(chain(), ActionContext())


@pytest.mark.asyncio
async def test_default_probe_never_raises_on_stub():
    """FR19：诊断方法对桩也必须可用，返回 error 而不是抛异常。"""
    adapter = AppiumAdapter()
    probe = await adapter.probe_locator(chain(), ActionContext())
    assert probe.count == 0
    assert probe.error and "尚未实现" in probe.error


@pytest.mark.asyncio
async def test_finalize_diagnostics_noop_on_stub():
    """M3.6 FR58：finalize_diagnostics 是诊断方法，桩适配器默认 no-op 不抛。"""
    adapter = AppiumAdapter()
    await adapter.finalize_diagnostics(save_trace=True)
    await adapter.finalize_diagnostics(save_trace=False)
