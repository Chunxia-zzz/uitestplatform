"""适配器契约测试（GAP-24 / M1 §5）。

**2026-11-08 修正**：以前这里直接 import 桩类来跑契约，测的是 `stub_adapter`，
真实现（`appium_adapter`）的签名漂移根本不会被发现。现在一律从 **registry** 取
（与运行时同一条加载路径），并额外断言 appium 解析到的是真实现而不是桩。
"""
from __future__ import annotations

import inspect

import pytest

from app.core.errors import UnsupportedActionError
from app.domain.action_keys import ACTION_BY_KEY
from app.domain.capabilities import CAPABILITY_MATRIX, ENGINES
from app.engines.adapters.stub_adapter import StubAppiumAdapter, StubUIAutomator2Adapter
from app.engines.base import ActionContext, EngineAdapter, Locator, LocatorChain
from app.engines.registry import registry


def _adapter_class(engine_key: str) -> type[EngineAdapter]:
    """从注册表拿**运行时真正会用**的适配器类（不是硬编码 import）。"""
    return type(registry.create(engine_key))


ENGINE_KEYS = registry.keys
REAL_ENGINE_KEYS = [key for key in ENGINE_KEYS if ENGINES[key].implemented]


def _platform_engines_of(engine_key: str) -> frozenset[str]:
    from app.domain.enums import PLATFORM_ENGINES

    return frozenset(p for p, engines in PLATFORM_ENGINES.items() if engine_key in engines)


@pytest.mark.parametrize("engine_key", ENGINE_KEYS)
def test_registered_adapter_is_instantiable_and_key_matches(engine_key):
    adapter = registry.create(engine_key)
    assert adapter.key == engine_key
    assert adapter.key in CAPABILITY_MATRIX
    assert adapter.platforms == _platform_engines_of(adapter.key)


def test_appium_registry_resolves_to_real_adapter_not_stub():
    """回归：包级同名桩曾让 `from app.engines.adapters import AppiumAdapter` 拿到桩。"""
    from app.engines.adapters import AppiumAdapter as PackageLevelAppium

    real = registry.create("appium")
    assert type(real) is PackageLevelAppium
    assert type(real).__module__ == "app.engines.adapters.appium_adapter"
    assert not isinstance(real, StubAppiumAdapter)
    assert ENGINES["appium"].adapter_path.endswith("appium_adapter:AppiumAdapter")


@pytest.mark.parametrize("engine_key", ENGINE_KEYS)
def test_every_declared_capability_has_method(engine_key):
    cls = _adapter_class(engine_key)
    for action_key in CAPABILITY_MATRIX[engine_key]:
        method = getattr(cls, action_key, None)
        assert method is not None, f"{engine_key} 声明了 {action_key} 但没有同名方法"
        assert callable(method)


@pytest.mark.parametrize("engine_key", ENGINE_KEYS)
def test_no_leftover_abstract_methods(engine_key):
    """少了抽象方法实现会在实例化时炸 —— 这里显式固化。"""
    cls = _adapter_class(engine_key)
    assert inspect.isabstract(cls) is False, f"{engine_key} 仍有未实现的抽象方法"


@pytest.mark.parametrize("cls", [StubAppiumAdapter, StubUIAutomator2Adapter], ids=lambda c: c.key)
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


@pytest.mark.parametrize("engine_key", REAL_ENGINE_KEYS)
def test_real_engines_override_every_declared_action_with_fr4_signature(engine_key):
    """`implemented=True` 的引擎必须真覆写（不是继承基类默认），且参数名与 schema 一致。"""
    cls = _adapter_class(engine_key)
    for action_key in CAPABILITY_MATRIX[engine_key]:
        own = cls.__dict__.get(action_key)
        assert own is not None, f"{engine_key}.{action_key} 仍是基类默认实现"
        assert own is not getattr(EngineAdapter, action_key, None)

        params = inspect.signature(own).parameters
        accepted = {name for name, p in params.items()
                    if p.kind == p.KEYWORD_ONLY and name not in ("chain", "ctx")}
        has_var_kw = any(p.kind == p.VAR_KEYWORD for p in params.values())
        expected = set(ACTION_BY_KEY[action_key].props)
        assert has_var_kw or expected == accepted, (
            f"{engine_key}.{action_key} 参数与 schema 不一致："
            f"期望 {sorted(expected)}，实得 {sorted(accepted)}")
