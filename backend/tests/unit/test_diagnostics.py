"""诊断解析纯函数（M3.6 GAP-08，D34）：options > 全局 env，非法值回退 + warning。"""
from __future__ import annotations

from app.domain.action_keys import ACTION_BY_KEY
from app.domain.diagnostics import DEFAULT_TRACE, TRACE_MODES, resolve_diagnostics


def test_defaults_without_options():
    plan = resolve_diagnostics("on-failure", False, False, None)
    assert plan.trace == "on-failure"
    assert plan.video is False
    assert plan.har is False
    assert plan.warnings == ()


def test_options_trace_override():
    plan = resolve_diagnostics("off", False, False, {"trace": "always"})
    assert plan.trace == "always"
    assert plan.warnings == ()


def test_options_video_bool_overrides_global():
    plan = resolve_diagnostics("off", False, False, {"video": True, "har": True})
    assert plan.video is True and plan.har is True
    plan2 = resolve_diagnostics("off", True, True, {"video": False, "har": False})
    assert plan2.video is False and plan2.har is False   # 显式 false 覆盖全局 true


def test_options_invalid_trace_falls_back_to_global():
    plan = resolve_diagnostics("always", False, False, {"trace": "sometimes"})
    assert plan.trace == "always"                        # options 非法 → 回退合法全局
    assert len(plan.warnings) == 1 and "options.trace" in plan.warnings[0]


def test_options_invalid_trace_and_global_invalid_falls_back_default():
    plan = resolve_diagnostics("bogus", False, False, {"trace": "sometimes"})
    assert plan.trace == DEFAULT_TRACE                   # 双非法 → 默认 on-failure
    assert len(plan.warnings) == 2                       # options 一条 + 全局一条


def test_global_invalid_falls_back_default_with_warning():
    plan = resolve_diagnostics("bogus", False, False, None)
    assert plan.trace == "on-failure"
    assert len(plan.warnings) == 1 and "全局 trace" in plan.warnings[0]


def test_video_non_bool_ignored_with_warning():
    plan = resolve_diagnostics("off", False, False, {"video": "yes"})
    assert plan.video is False                           # 不做真值转换
    assert len(plan.warnings) == 1 and "options.video" in plan.warnings[0]
    plan2 = resolve_diagnostics("off", True, False, {"har": "false"})
    assert plan2.har is False and plan2.video is True    # 字符串 "false" 不能意外为真
    assert plan2.video is True                           # 全局 true 保持


def test_finalize_diagnostics_not_in_action_catalog():
    """FR58：finalize_diagnostics 是诊断方法，绝不进 51 条动作字典。"""
    assert len(ACTION_BY_KEY) == 51
    for mode in TRACE_MODES:                             # 顺带守住合法值集合
        assert mode in {"off", "on-failure", "always"}
    assert "finalize_diagnostics" not in ACTION_BY_KEY
