"""适配器契约测试（GAP-24 / M1 §5 承诺但之前缺失）。

参数化跑全部 adapter：任何"声明支持却没实现""实现了但不在能力矩阵"都会被抓住。
"""
from __future__ import annotations

import inspect

import pytest

from app.core.errors import UnsupportedActionError
from app.domain.capabilities import CAPABILITY_MATRIX
from app.domain.enums import PLATFORM_ENGINES
from app.engines.adapters.playwright_adapter import PlaywrightAdapter
from app.engines.adapters.stub_adapter import AppiumAdapter, UIAutomator2Adapter
from app.engines.base import ActionContext, EngineAdapter, Locator, LocatorChain

ADAPTERS = [PlaywrightAdapter, AppiumAdapter, UIAutomator2Adapter]


@pytest.mark.parametrize("cls", ADAPTERS, ids=lambda c: c.key)
def test_adapter_instantiable_and_key_declared(cls):
    adapter = cls()
    assert adapter.key
    assert adapter.key in CAPABILITY_MATRIX
    assert adapter.platforms == PLATFORM_ENGINES_OF(adapter.key)


def PLATFORM_ENGINES_OF(engine_key: str) -> frozenset[str]:
    return frozenset(p for p, engines in PLATFORM_ENGINES.items() if engine_key in engines)


@pytest.mark.parametrize("cls", ADAPTERS, ids=lambda c: c.key)
def test_every_declared_capability_has_method(cls):
    for action_key in CAPABILITY_MATRIX[cls.key]:
        method = getattr(cls, action_key, None)
        assert method is not None, f"{cls.key} 声明了 {action_key} 但没有同名方法"
        assert callable(method)


@pytest.mark.parametrize("cls", ADAPTERS, ids=lambda c: c.key)
def test_no_leftover_abstract_methods(cls):
    """少了抽象方法实现会在实例化时炸 —— 这里显式固化。"""
    assert inspect.isabstract(cls) is False, f"{cls.key} 仍有未实现的抽象方法"


@pytest.mark.parametrize("cls", [AppiumAdapter, UIAutomator2Adapter], ids=lambda c: c.key)
@pytest.mark.asyncio
async def test_stub_semantics_declared_vs_undeclared(cls):
    """FR15：声明的动作 → NotImplementedError；未声明的 → UnsupportedActionError。"""
    adapter = cls()
    chain = LocatorChain.of(1, [Locator(type="resource_id", value="com.x:id/y")])
    declared = sorted(CAPABILITY_MATRIX[cls.key])
    assert declared
    with pytest.raises(NotImplementedError):
        await getattr(adapter, declared[0])(chain, ActionContext())

    undeclared = next(
        key for key in ("go_back", "refresh", "get_cookies", "delete_cookies")
        if key not in CAPABILITY_MATRIX[cls.key])
    with pytest.raises(UnsupportedActionError):
        await getattr(adapter, undeclared)(chain, ActionContext())


def test_playwright_implements_every_declared_action_with_fr4_signature():
    """Playwright 必须真覆写（不是继承基类默认实现），且参数名与 params_schema 一致。"""
    from app.domain.action_keys import ACTION_BY_KEY

    for action_key in CAPABILITY_MATRIX[PlaywrightAdapter.key]:
        own = PlaywrightAdapter.__dict__.get(action_key)
        assert own is not None, f"playwright.{action_key} 仍是基类默认实现"
        assert own is not getattr(EngineAdapter, action_key, None)

        params = inspect.signature(own).parameters
        accepted = {name for name, p in params.items()
                    if p.kind == p.KEYWORD_ONLY and name not in ("chain", "ctx")}
        has_var_kw = any(p.kind == p.VAR_KEYWORD for p in params.values())
        expected = set(ACTION_BY_KEY[action_key].props)
        assert has_var_kw or expected == accepted, (
            f"{action_key} 参数与 schema 不一致：期望 {sorted(expected)}，实得 {sorted(accepted)}")
