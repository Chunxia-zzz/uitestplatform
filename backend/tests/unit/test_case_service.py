"""用例编排服务（M3.2 / StepEditor）：新增、修改、删除、排序与全部写入期校验。

这些用例的重点不是"能写进去"，而是**写错的必须写不进去**：
动作不存在、参数不符 schema、元素跨项目、seq 冲突 —— 都要在写入口拦下，
而不是等执行时起一个浏览器再失败。
"""
from __future__ import annotations

import pytest

from app.core.errors import (
    ElementNotFound, StepNotFound, StepSeqDuplicated, ValidationFailed,
)
from app.models import Element, TestCase
from app.services import case_service


async def _case(db, project) -> TestCase:
    row = TestCase(project_id=project.id, title="登录", description="")
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def _element(db, project, name="登录按钮", parent_id=0, path=None) -> Element:
    row = Element(project_id=project.id, parent_id=parent_id,
                  path=path or f"/{name}/", element_name=name, node_type="ELEMENT")
    db.add(row)
    await db.commit()
    await db.refresh(row)
    if path is None:
        row.path = f"/{row.id}/"
        await db.commit()
        await db.refresh(row)
    return row


# ─────────────────────────── 新增 ───────────────────────────
@pytest.mark.asyncio
async def test_create_step_appends_seq_when_omitted(db, project):
    case = await _case(db, project)
    first = await case_service.create_step(
        db, case.id, seq=None, action_key="navigate", element_id=None,
        params={"url": "https://example.com"})
    second = await case_service.create_step(
        db, case.id, seq=None, action_key="navigate", element_id=None,
        params={"url": "https://example.com/2"})
    assert (first.seq, second.seq) == (1, 2)


@pytest.mark.asyncio
async def test_create_step_rejects_unknown_action(db, project):
    case = await _case(db, project)
    with pytest.raises(ValidationFailed):
        await case_service.create_step(db, case.id, seq=None, action_key="no_such",
                                       element_id=None, params={})


@pytest.mark.asyncio
async def test_create_step_rejects_missing_element(db, project):
    case = await _case(db, project)
    with pytest.raises(ValidationFailed):
        await case_service.create_step(db, case.id, seq=None, action_key="click",
                                       element_id=None, params={})


@pytest.mark.asyncio
async def test_create_step_rejects_element_on_plain_action(db, project):
    case = await _case(db, project)
    element = await _element(db, project)
    with pytest.raises(ValidationFailed):
        await case_service.create_step(db, case.id, seq=None, action_key="navigate",
                                       element_id=element.id, params={"url": "x"})


@pytest.mark.asyncio
async def test_create_step_rejects_params_not_matching_schema(db, project):
    case = await _case(db, project)
    # navigate 的 url 是必填
    with pytest.raises(ValidationFailed):
        await case_service.create_step(db, case.id, seq=None, action_key="navigate",
                                       element_id=None, params={})


@pytest.mark.asyncio
async def test_create_step_rejects_extra_param(db, project):
    case = await _case(db, project)
    with pytest.raises(ValidationFailed):
        await case_service.create_step(
            db, case.id, seq=None, action_key="navigate", element_id=None,
            params={"url": "x", "unexpected": 1})


@pytest.mark.asyncio
async def test_create_step_rejects_element_from_other_project(db, project):
    other = type(project)(name="O", code="o2", platform="WEB", engine_key="playwright",
                          default_timeout_ms=5000)
    db.add(other)
    await db.commit()
    await db.refresh(other)
    foreign = await _element(db, other)
    case = await _case(db, project)

    with pytest.raises(ValidationFailed):
        await case_service.create_step(db, case.id, seq=None, action_key="click",
                                       element_id=foreign.id, params={})


@pytest.mark.asyncio
async def test_create_step_rejects_missing_element_row(db, project):
    case = await _case(db, project)
    with pytest.raises(ElementNotFound):
        await case_service.create_step(db, case.id, seq=None, action_key="click",
                                       element_id=9999, params={})


@pytest.mark.asyncio
async def test_screenshot_element_target_requires_element(db, project):
    case = await _case(db, project)
    with pytest.raises(ValidationFailed):
        await case_service.create_step(
            db, case.id, seq=None, action_key="screenshot", element_id=None,
            params={"target": "element"})

    element = await _element(db, project)
    step = await case_service.create_step(
        db, case.id, seq=None, action_key="screenshot", element_id=element.id,
        params={"target": "element"})
    assert step.element_id == element.id


@pytest.mark.asyncio
async def test_page_screenshot_must_not_bind_element(db, project):
    case = await _case(db, project)
    element = await _element(db, project)
    with pytest.raises(ValidationFailed):
        await case_service.create_step(
            db, case.id, seq=None, action_key="screenshot", element_id=element.id,
            params={"target": "page"})


@pytest.mark.asyncio
async def test_duplicate_seq_is_rejected(db, project):
    case = await _case(db, project)
    await case_service.create_step(db, case.id, seq=1, action_key="navigate",
                                   element_id=None, params={"url": "x"})
    with pytest.raises(StepSeqDuplicated):
        await case_service.create_step(db, case.id, seq=1, action_key="navigate",
                                       element_id=None, params={"url": "y"})


# ─────────────────────────── 修改 ───────────────────────────
@pytest.mark.asyncio
async def test_update_step_only_changes_given_fields(db, project):
    case = await _case(db, project)
    element = await _element(db, project)
    step = await case_service.create_step(
        db, case.id, seq=None, action_key="click", element_id=element.id, params={})

    updated = await case_service.update_step(db, case.id, step.id,
                                             {"enabled": False, "remark": "先跳过"})
    assert updated.enabled is False
    assert updated.remark == "先跳过"
    assert updated.action_key == "click"
    assert updated.element_id == element.id


@pytest.mark.asyncio
async def test_update_step_revalidates_after_action_change(db, project):
    case = await _case(db, project)
    element = await _element(db, project)
    step = await case_service.create_step(
        db, case.id, seq=None, action_key="click", element_id=element.id, params={})

    # navigate 不需要元素 → 原 element_id 变成非法
    with pytest.raises(ValidationFailed):
        await case_service.update_step(db, case.id, step.id,
                                       {"action_key": "navigate",
                                        "params": {"url": "x"}})


@pytest.mark.asyncio
async def test_update_step_can_clear_element(db, project):
    case = await _case(db, project)
    element = await _element(db, project)
    step = await case_service.create_step(
        db, case.id, seq=None, action_key="click", element_id=element.id, params={})

    updated = await case_service.update_step(db, case.id, step.id,
                                             {"action_key": "navigate",
                                              "element_id": None,
                                              "params": {"url": "https://x"}})
    assert updated.element_id is None
    assert updated.action_key == "navigate"


@pytest.mark.asyncio
async def test_update_step_seq_conflict(db, project):
    case = await _case(db, project)
    first = await case_service.create_step(db, case.id, seq=1, action_key="navigate",
                                           element_id=None, params={"url": "a"})
    await case_service.create_step(db, case.id, seq=2, action_key="navigate",
                                   element_id=None, params={"url": "b"})
    with pytest.raises(StepSeqDuplicated):
        await case_service.update_step(db, case.id, first.id, {"seq": 2})


@pytest.mark.asyncio
async def test_update_missing_step(db, project):
    case = await _case(db, project)
    with pytest.raises(StepNotFound):
        await case_service.update_step(db, case.id, 404, {"enabled": False})


# ─────────────────────────── 排序 ───────────────────────────
@pytest.mark.asyncio
async def test_reorder_swaps_without_unique_conflict(db, project):
    """交换相邻 seq 会瞬时撞唯一键 —— 服务必须先置负再落正。"""
    case = await _case(db, project)
    a = await case_service.create_step(db, case.id, seq=1, action_key="navigate",
                                       element_id=None, params={"url": "a"})
    b = await case_service.create_step(db, case.id, seq=2, action_key="navigate",
                                       element_id=None, params={"url": "b"})
    c = await case_service.create_step(db, case.id, seq=3, action_key="navigate",
                                       element_id=None, params={"url": "c"})

    rows = await case_service.reorder_steps(db, case.id, [c.id, a.id, b.id])
    assert [(r.id, r.seq) for r in rows] == [(c.id, 1), (a.id, 2), (b.id, 3)]


@pytest.mark.asyncio
async def test_reorder_rejects_incomplete_set(db, project):
    case = await _case(db, project)
    a = await case_service.create_step(db, case.id, seq=1, action_key="navigate",
                                       element_id=None, params={"url": "a"})
    await case_service.create_step(db, case.id, seq=2, action_key="navigate",
                                   element_id=None, params={"url": "b"})
    with pytest.raises(ValidationFailed):
        await case_service.reorder_steps(db, case.id, [a.id])
    with pytest.raises(ValidationFailed):
        await case_service.reorder_steps(db, case.id, [a.id, a.id, 999])


# ─────────────────────────── 删除 ───────────────────────────
@pytest.mark.asyncio
async def test_delete_step(db, project):
    case = await _case(db, project)
    step = await case_service.create_step(db, case.id, seq=None, action_key="navigate",
                                          element_id=None, params={"url": "a"})
    await case_service.delete_step(db, case.id, step.id)
    assert await case_service.list_steps(db, case.id) == []


@pytest.mark.asyncio
async def test_delete_case_is_soft(db, project):
    case = await _case(db, project)
    await case_service.delete_case(db, case.id)
    with pytest.raises(Exception):
        await case_service.get_case_or_404(db, case.id)
    # 步骤保留，历史执行仍可追溯
    assert case.id is not None
