"""用例与步骤的编排服务（M3.2 / GAP-19）。

写入期校验比读接口重要得多：一条 ``action_key`` 写错、``params`` 少一个必填字段，
要等到执行时才炸 —— 而执行要起浏览器、要几十秒。所以所有校验都放在写入口，
并且**新增与修改走同一份校验**，避免"新增严格、修改宽松"的不一致。
"""
from __future__ import annotations

from typing import Any

from jsonschema import validate as js_validate
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    CaseNotFound, ElementNotFound, StepNotFound, StepSeqDuplicated, ValidationFailed,
)
from app.domain.action_keys import ACTION_BY_KEY
from app.models import Element, TestCase, TestStep


async def create_case(db: AsyncSession, *, project_id: int, title: str,
                      description: str | None = None) -> TestCase:
    value = (title or "").strip()
    if not value:
        raise ValidationFailed("用例标题不能为空")
    case = TestCase(project_id=project_id, title=value, description=description)
    db.add(case)
    await db.commit()
    await db.refresh(case)
    return case


async def get_case_or_404(db: AsyncSession, case_id: int) -> TestCase:
    case = (await db.execute(
        select(TestCase).where(TestCase.id == case_id, TestCase.is_deleted.is_(False))
    )).scalar_one_or_none()
    if case is None:
        raise CaseNotFound(f"用例 {case_id} 不存在", {"case_id": case_id})
    return case


async def list_steps(db: AsyncSession, case_id: int) -> list[TestStep]:
    return list((await db.execute(
        select(TestStep).where(TestStep.case_id == case_id).order_by(TestStep.seq)
    )).scalars().all())


async def get_step_or_404(db: AsyncSession, case_id: int, step_id: int) -> TestStep:
    step = (await db.execute(
        select(TestStep).where(TestStep.id == step_id, TestStep.case_id == case_id)
    )).scalar_one_or_none()
    if step is None:
        raise StepNotFound(f"步骤 {step_id} 不存在或不属于用例 {case_id}",
                           {"step_id": step_id, "case_id": case_id})
    return step


# ─────────────────────────── 校验 ───────────────────────────
def _special_element_need(action_key: str, params: dict[str, Any]) -> bool:
    """screenshot(target=element) 需要元素，但动作本身声明 requires_element=False。"""
    return action_key == "screenshot" and params.get("target") == "element"


def element_requirement(action_key: str, params: dict[str, Any] | None) -> bool:
    """该动作是否需要绑定元素（含 screenshot(target=element) 特例）。

    M3.4 的 Scaffold 用它做专用错误码判断；Cases API 的校验仍走 validate_action。
    """
    spec = ACTION_BY_KEY.get(action_key)
    if spec is None:
        raise ValidationFailed(f"未知动作 {action_key}", {"action_key": action_key})
    return spec.requires_element or _special_element_need(action_key, params or {})


def validate_action(action_key: str, has_element: bool,
                    params: dict[str, Any] | None) -> None:
    """动作级校验（不依赖具体 case / element 行）。

    M3.4 起被 Scaffold 复用：装配阶段还没有 element_id，但必须能校验
    "这个动作需不需要元素、参数对不对"。所以把判断依据从 `element_id`
    换成 `has_element` —— 同一份规则，两处调用。
    """
    spec = ACTION_BY_KEY.get(action_key)
    if spec is None:
        raise ValidationFailed(f"未知动作 {action_key}", {"action_key": action_key})

    params = params or {}
    needs_element = spec.requires_element or _special_element_need(action_key, params)
    if needs_element and not has_element:
        hint = "（screenshot target=element）" if _special_element_need(action_key, params) else ""
        raise ValidationFailed(f"动作 {action_key} 需要绑定元素{hint}",
                               {"action_key": action_key})
    if not needs_element and has_element:
        raise ValidationFailed(f"动作 {action_key} 不应绑定元素",
                               {"action_key": action_key})

    try:
        js_validate(instance=params, schema=spec.params_schema)
    except Exception as exc:
        raise ValidationFailed(
            f"参数不符合 {action_key} 的 schema：{exc.message if hasattr(exc, 'message') else exc}",
            {"action_key": action_key, "params": params},
        ) from exc


def validate_step(case: TestCase, action_key: str, element_id: int | None,
                  params: dict[str, Any] | None) -> None:
    validate_action(action_key, bool(element_id), params)


async def assert_element_in_project(db: AsyncSession, element_id: int | None,
                                    project_id: int) -> None:
    """元素必须存在且属于同一项目 —— 否则跨项目引用会在执行时变成"定位符找不到"。"""
    if not element_id:
        return
    row = (await db.execute(
        select(Element).where(Element.id == element_id, Element.is_deleted.is_(False))
    )).scalar_one_or_none()
    if row is None:
        raise ElementNotFound(f"元素 {element_id} 不存在", {"element_id": element_id})
    if row.project_id != project_id:
        raise ValidationFailed(
            f"元素 {element_id} 不属于项目 {project_id}",
            {"element_id": element_id, "project_id": project_id,
             "element_project_id": row.project_id},
        )


async def _assert_seq_free(db: AsyncSession, case_id: int, seq: int,
                           exclude_id: int | None = None) -> None:
    stmt = select(TestStep.id).where(TestStep.case_id == case_id, TestStep.seq == seq)
    if exclude_id:
        stmt = stmt.where(TestStep.id != exclude_id)
    if (await db.execute(stmt.limit(1))).scalar_one_or_none():
        raise StepSeqDuplicated(f"用例内已存在 seq={seq} 的步骤",
                                {"case_id": case_id, "seq": seq})


async def _next_seq(db: AsyncSession, case_id: int) -> int:
    current = (await db.execute(
        select(func.max(TestStep.seq)).where(TestStep.case_id == case_id))).scalar_one()
    return int(current or 0) + 1


# ─────────────────────────── 写操作 ───────────────────────────
async def create_step(db: AsyncSession, case_id: int, *, seq: int | None,
                      action_key: str, element_id: int | None, params: dict[str, Any],
                      output_var: str | None = None, timeout_ms: int | None = None,
                      on_failure: str = "ABORT", retry_times: int = 0,
                      enabled: bool = True, remark: str | None = None) -> TestStep:
    case = await get_case_or_404(db, case_id)
    validate_step(case, action_key, element_id, params)
    await assert_element_in_project(db, element_id, case.project_id)

    target_seq = seq if seq is not None else await _next_seq(db, case_id)
    await _assert_seq_free(db, case_id, target_seq)

    step = TestStep(case_id=case_id, seq=target_seq, action_key=action_key,
                    element_id=element_id, params=params or {},
                    output_var=output_var, timeout_ms=timeout_ms,
                    on_failure=on_failure, retry_times=retry_times,
                    enabled=enabled, remark=remark)
    db.add(step)
    await db.commit()
    await db.refresh(step)
    return step


async def update_step(db: AsyncSession, case_id: int, step_id: int,
                      changes: dict[str, Any]) -> TestStep:
    """只更新传入的字段。动作/元素/参数任一变化都重新完整校验。"""
    case = await get_case_or_404(db, case_id)
    step = await get_step_or_404(db, case_id, step_id)

    action_key = changes.get("action_key", step.action_key)
    element_id = changes["element_id"] if "element_id" in changes else step.element_id
    params = changes["params"] if "params" in changes else (step.params or {})
    validate_step(case, action_key, element_id, params)
    if "element_id" in changes:
        await assert_element_in_project(db, element_id, case.project_id)

    if "seq" in changes and changes["seq"] is not None and changes["seq"] != step.seq:
        await _assert_seq_free(db, case_id, changes["seq"], exclude_id=step.id)

    for field in ("seq", "action_key", "element_id", "params", "output_var",
                  "timeout_ms", "on_failure", "retry_times", "enabled", "remark"):
        if field in changes:
            setattr(step, field, changes[field])
    await db.commit()
    await db.refresh(step)
    return step


async def delete_step(db: AsyncSession, case_id: int, step_id: int) -> None:
    step = await get_step_or_404(db, case_id, step_id)
    await db.delete(step)
    await db.commit()


async def reorder_steps(db: AsyncSession, case_id: int,
                        ordered_ids: list[int]) -> list[TestStep]:
    """全量重排：``ordered_ids`` 必须恰好等于该用例的步骤集合。

    两步写：先把 seq 全置负（避开 ``uk_step_seq`` 在交换时的瞬时冲突），再逐条落正。
    """
    await get_case_or_404(db, case_id)
    steps = await list_steps(db, case_id)
    if len(ordered_ids) != len(steps) or set(ordered_ids) != {s.id for s in steps}:
        raise ValidationFailed(
            "ordered_ids 必须恰好包含该用例的全部步骤，不能多、不能少、不能重复",
            {"case_id": case_id, "ordered_ids": ordered_ids},
        )

    await db.execute(
        update(TestStep).where(TestStep.case_id == case_id)
        .values(seq=-TestStep.seq))
    await db.flush()
    for index, step_id in enumerate(ordered_ids, start=1):
        await db.execute(
            update(TestStep).where(TestStep.id == step_id).values(seq=index))
    await db.commit()
    return await list_steps(db, case_id)


async def update_case(db: AsyncSession, case_id: int, *,
                      title: str | None = None,
                      description: str | None = None) -> TestCase:
    case = await get_case_or_404(db, case_id)
    if title is not None:
        value = title.strip()
        if not value:
            raise ValidationFailed("用例标题不能为空")
        case.title = value
    if description is not None:
        case.description = description
    await db.commit()
    await db.refresh(case)
    return case


async def delete_case(db: AsyncSession, case_id: int) -> None:
    """软删除。步骤保留 —— 历史 ``execution_step_result`` 仍要能追溯。"""
    case = await get_case_or_404(db, case_id)
    case.is_deleted = True
    case.deleted_seq = case.id
    from datetime import datetime
    case.deleted_at = datetime.now()
    await db.commit()
