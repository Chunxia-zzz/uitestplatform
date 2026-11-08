"""领域字典不变量（M2 U1 / U2 + M1 动作字典）。"""
from __future__ import annotations

import pytest

from app.domain.action_keys import ACTION_BY_KEY, ACTION_CATALOG, BUILTIN_ACTION_KEYS
from app.domain.capabilities import CAPABILITY_MATRIX, ENGINES, assert_engine_platform_consistency
from app.domain.enums import PLATFORM_ENGINES
from app.domain.locator_types import (
    FORBIDDEN_TYPE_TOKENS,
    LOCATOR_TYPES,
    default_priority,
    get_spec,
)


def test_action_catalog_is_51_and_unique():
    assert len(ACTION_CATALOG) == 51
    assert len(ACTION_BY_KEY) == 51
    keys = [a.key for a in ACTION_CATALOG]
    assert len(set(keys)) == 51
    # D6：英文 snake_case
    for key in keys:
        assert key.islower() and " " not in key, key


def test_builtin_actions_are_9():
    assert len(BUILTIN_ACTION_KEYS) == 9
    for key in BUILTIN_ACTION_KEYS:
        assert ACTION_BY_KEY[key].engines == ()
        assert ACTION_BY_KEY[key].is_builtin


def test_matrix_matches_catalog_bidirectionally():
    """矩阵 ↔ 字典双向一致（M1 F2 的守门测试）。"""
    for action in ACTION_CATALOG:
        for engine in action.engines:
            assert action.key in CAPABILITY_MATRIX[engine], (engine, action.key)
    for engine, actions in CAPABILITY_MATRIX.items():
        for key in actions:
            assert engine in ACTION_BY_KEY[key].engines, (engine, key)


def test_action_platforms_are_declared_for_engines():
    for action in ACTION_CATALOG:
        if action.is_builtin:
            continue
        for engine in action.engines:
            meta = ENGINES[engine]
            assert set(action.platforms) & set(meta.platforms), (action.key, engine)


def test_locator_types_semantic_only():
    """FR18：locator_type 不得含引擎语汇。"""
    for platform, spec in LOCATOR_TYPES.items():
        assert spec.types, platform
        ranks = [t.rank for t in spec.types.values()]
        assert len(set(ranks)) == len(ranks), f"{platform} rank 重复"
        for key, t in spec.types.items():
            assert key == t.key
            assert t.label and t.example
            assert t.engines, f"{platform}.{key} 未声明引擎"
            assert t.engines <= spec.engines
            lowered = key.lower()
            for token in FORBIDDEN_TYPE_TOKENS:
                assert token.lower() not in lowered, f"{platform}.{key} 含引擎语汇 {token}"


def test_every_platform_engine_has_at_least_one_type():
    """否则该引擎的元素永远配不出来（M2 §2.5.5 第 2 条）。"""
    for platform, engines in PLATFORM_ENGINES.items():
        for engine in engines:
            supported = [t for t in LOCATOR_TYPES[platform].types.values()
                         if engine in t.engines]
            assert supported, f"{platform}/{engine} 无可用定位类型"


def test_engine_platform_consistency():
    assert_engine_platform_consistency()


def test_default_priority_follows_rank():
    assert default_priority("WEB", "testid") == 10
    assert default_priority("IOS", "xpath") == 50
    assert get_spec("IOS", "css") is None


def test_wildcard_rules():
    """引擎专属类型不能通配（M2 F-M2-1 的核心约束）。"""
    from app.domain.locator_types import platform_engines

    uia = get_spec("ANDROID", "uiautomator")
    assert uia is not None
    assert uia.engines != platform_engines("ANDROID")

    resource = get_spec("ANDROID", "resource_id")
    assert resource is not None
    assert resource.engines == platform_engines("ANDROID")


@pytest.mark.parametrize("platform,expected", [
    ("WEB", 11), ("ANDROID", 7), ("IOS", 5),
])
def test_type_counts(platform, expected):
    assert len(LOCATOR_TYPES[platform].types) == expected
