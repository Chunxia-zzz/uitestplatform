"""用例端点（M3.2：StepEditor 所需的完整 CRUD 与排序）。

写入口的校验全部在 ``case_service``，端点只负责收参数、转 DTO ——
这样"通过 API 改"和"通过服务改"走的是同一份规则。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models import TestCase
from app.schemas.requests import CaseCreate, CaseUpdate, StepCreate, StepOrder, StepUpdate
from app.schemas.serialize import case_to_dict, step_to_dict
from app.services import case_service

router = APIRouter(tags=["cases"])


@router.get("/projects/{project_id}/cases")
async def list_cases(project_id: int, db: AsyncSession = Depends(get_session)):
    rows = list((await db.execute(
        select(TestCase).where(TestCase.project_id == project_id,
                               TestCase.is_deleted.is_(False)).order_by(TestCase.id)
    )).scalars().all())
    return {"items": [case_to_dict(c) for c in rows], "total": len(rows)}


@router.post("/projects/{project_id}/cases", status_code=201)
async def create_case(project_id: int, body: CaseCreate,
                      db: AsyncSession = Depends(get_session)):
    case = await case_service.create_case(
        db, project_id=project_id, title=body.title, description=body.description)
    return case_to_dict(case)


@router.get("/cases/{case_id}")
async def get_case(case_id: int, db: AsyncSession = Depends(get_session)):
    case = await case_service.get_case_or_404(db, case_id)
    payload = case_to_dict(case)
    payload["steps"] = [step_to_dict(s) for s in await case_service.list_steps(db, case_id)]
    return payload


@router.patch("/cases/{case_id}")
async def update_case(case_id: int, body: CaseUpdate,
                      db: AsyncSession = Depends(get_session)):
    changes = body.model_dump(exclude_unset=True)
    case = await case_service.update_case(db, case_id, **changes)
    return case_to_dict(case)


@router.delete("/cases/{case_id}", status_code=204)
async def delete_case(case_id: int, db: AsyncSession = Depends(get_session)):
    await case_service.delete_case(db, case_id)


# ─────────────────────────── 步骤 ───────────────────────────
@router.get("/cases/{case_id}/steps")
async def list_steps(case_id: int, db: AsyncSession = Depends(get_session)):
    await case_service.get_case_or_404(db, case_id)
    rows = await case_service.list_steps(db, case_id)
    return {"items": [step_to_dict(s) for s in rows], "total": len(rows)}


@router.post("/cases/{case_id}/steps", status_code=201)
async def add_step(case_id: int, body: StepCreate, db: AsyncSession = Depends(get_session)):
    """seq 不传时自动追加到末尾；动作、参数、元素归属全部在写入期校验。"""
    step = await case_service.create_step(
        db, case_id, seq=body.seq, action_key=body.action_key,
        element_id=body.element_id, params=body.params or {},
        output_var=body.output_var, timeout_ms=body.timeout_ms,
        on_failure=body.on_failure, retry_times=body.retry_times,
        enabled=body.enabled, remark=body.remark,
    )
    return step_to_dict(step)


@router.patch("/cases/{case_id}/steps/{step_id}")
async def update_step(case_id: int, step_id: int, body: StepUpdate,
                      db: AsyncSession = Depends(get_session)):
    changes = body.model_dump(exclude_unset=True)
    step = await case_service.update_step(db, case_id, step_id, changes)
    return step_to_dict(step)


@router.delete("/cases/{case_id}/steps/{step_id}", status_code=204)
async def delete_step(case_id: int, step_id: int,
                      db: AsyncSession = Depends(get_session)):
    await case_service.delete_step(db, case_id, step_id)


@router.put("/cases/{case_id}/steps/order")
async def reorder_steps(case_id: int, body: StepOrder,
                        db: AsyncSession = Depends(get_session)):
    rows = await case_service.reorder_steps(db, case_id, body.ordered_ids)
    return {"items": [step_to_dict(s) for s in rows], "total": len(rows)}


__all__ = ["router"]
