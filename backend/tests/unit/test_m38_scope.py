"""M3.8 执行级变量与绑定规则单测（GAP-13 / GAP-12 校验侧 / spec US4）。

锁住语义：scope=execution 写 shared 层、缺省写 case 层、
渲染"用例级优先、执行级兜底"、output_var 恒为 case 级；
switch_to_iframe 三态绑定 + 互斥；download_file 必须绑元素。
"""
from __future__ import annotations

import pytest

from app.engines.actions import dispatch
from app.engines.base import ActionContext
from app.services.case_service import (
    OPTIONAL_ELEMENT_ACTIONS,
    element_requirement,
    validate_action,
)


@pytest.mark.asyncio
async def test_set_variable_default_goes_to_case_scope():
    ctx = ActionContext(variables={}, shared_variables={})
    await dispatch("set_variable", None, None, {"name": "a", "value": "1"}, ctx)
    assert ctx.variables == {"a": "1"}
    assert ctx.shared_variables == {}


@pytest.mark.asyncio
async def test_set_variable_execution_scope_goes_to_shared():
    ctx = ActionContext(variables={}, shared_variables={})
    await dispatch("set_variable", None, None,
                   {"name": "token", "value": "T-123", "scope": "execution"}, ctx)
    assert ctx.shared_variables == {"token": "T-123"}
    assert ctx.variables == {}


@pytest.mark.asyncio
async def test_render_case_level_wins_over_execution_level():
    ctx = ActionContext(variables={"v": "from-case"},
                        shared_variables={"v": "from-execution"})
    await dispatch("set_variable", None, None,
                   {"name": "got", "value": "${v}"}, ctx)
    assert ctx.variables["got"] == "from-case"


@pytest.mark.asyncio
async def test_render_falls_back_to_execution_level():
    ctx = ActionContext(variables={}, shared_variables={"token": "T-123"})
    await dispatch("set_variable", None, None,
                   {"name": "got", "value": "${token}"}, ctx)
    assert ctx.variables["got"] == "T-123"


@pytest.mark.asyncio
async def test_missing_variable_kept_literal():
    """既有语义：变量缺失保留原样（不静默变空）。"""
    ctx = ActionContext(variables={}, shared_variables={})
    await dispatch("set_variable", None, None,
                   {"name": "got", "value": "${nope}"}, ctx)
    assert ctx.variables["got"] == "${nope}"


# ─────────────────────────── 绑定规则三态 ───────────────────────────
def test_switch_to_iframe_is_optional_element_action():
    assert "switch_to_iframe" in OPTIONAL_ELEMENT_ACTIONS
    assert element_requirement("switch_to_iframe", {}) is False


def test_switch_to_iframe_with_element_and_index_rejected():
    from app.core.errors import ValidationFailed

    with pytest.raises(ValidationFailed) as ei:
        validate_action("switch_to_iframe", True, {"index": 0})
    assert "二选一" in str(ei.value)


def test_switch_to_iframe_with_element_alone_ok():
    validate_action("switch_to_iframe", True, {})
    validate_action("switch_to_iframe", False, {"index": 0})
    validate_action("switch_to_iframe", False, {})          # 弹栈


def test_download_file_requires_element():
    from app.core.errors import ValidationFailed

    assert element_requirement("download_file", {}) is True
    with pytest.raises(ValidationFailed):
        validate_action("download_file", False, {})


def test_screenshot_target_element_still_special():
    """既有特例不回退：target=element 必须绑元素。"""
    assert element_requirement("screenshot", {"target": "element"}) is True
    assert element_requirement("screenshot", {"target": "page"}) is False


def test_mock_route_json_and_body_exclusive():
    from app.core.errors import ValidationFailed

    with pytest.raises(ValidationFailed) as ei:
        validate_action("mock_route", False,
                        {"pattern": "**/x", "body": "b", "json": {"a": 1}})
    assert "二选一" in str(ei.value)
    validate_action("mock_route", False, {"pattern": "**/x", "json": {"a": 1}})
    validate_action("mock_route", False,
                    {"pattern": "**/x", "abort": True})
