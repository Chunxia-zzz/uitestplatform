"""用例集端点（M3.3）：CRUD + 成员 + 单次运行。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.schemas.requests import (
    SuiteCaseOrder,
    SuiteCasesAdd,
    SuiteCaseToggle,
    SuiteCreate,
    SuiteUpdate,
)
from app.schemas.serialize import suite_member_to_dict, suite_to_dict
from app.services import scheduler, suite_service

router = APIRouter(tags=["suites"])


@router.get("/projects/{project_id}/suites")
async def list_suites(project_id: int, db: AsyncSession = Depends(get_session)):
    rows = await suite_service.list_suites(db, project_id)
    return {
        "items": [suite_to_dict(r["suite"], r["case_count"]) for r in rows],
        "total": len(rows),
    }


@router.post("/projects/{project_id}/suites", status_code=201)
async def create_suite(project_id: int, body: SuiteCreate,
                       db: AsyncSession = Depends(get_session)):
    suite = await suite_service.create(
        db, project_id=project_id, name=body.name, description=body.description,
        schedule_cron=body.schedule_cron, schedule_enabled=body.schedule_enabled)
    scheduler.sync_suite(suite)
    return suite_to_dict(suite, case_count=0)


@router.get("/suites/{suite_id}")
async def get_suite(suite_id: int, db: AsyncSession = Depends(get_session)):
    suite = await suite_service.get_or_404(db, suite_id)
    cases = await suite_service.list_cases(db, suite_id)
    payload = suite_to_dict(suite, case_count=len(cases))
    payload["cases"] = [suite_member_to_dict(m["member"], m["case"]) for m in cases]
    return payload


@router.patch("/suites/{suite_id}")
async def update_suite(suite_id: int, body: SuiteUpdate,
                       db: AsyncSession = Depends(get_session)):
    suite = await suite_service.update(
        db, suite_id, name=body.name, description=body.description,
        schedule_cron=body.schedule_cron, schedule_enabled=body.schedule_enabled)
    scheduler.sync_suite(suite)
    return suite_to_dict(suite)


@router.delete("/suites/{suite_id}", status_code=204)
async def delete_suite(suite_id: int, db: AsyncSession = Depends(get_session)):
    suite = await suite_service.get_or_404(db, suite_id)
    await suite_service.delete(db, suite_id)
    scheduler.sync_suite(suite)          # is_deleted=True → 摘掉 job
    return Response(status_code=204)


@router.get("/suites/{suite_id}/cases")
async def list_suite_cases(suite_id: int, db: AsyncSession = Depends(get_session)):
    await suite_service.get_or_404(db, suite_id)
    rows = await suite_service.list_cases(db, suite_id)
    return {"items": [suite_member_to_dict(r["member"], r["case"]) for r in rows],
            "total": len(rows)}


@router.post("/suites/{suite_id}/cases", status_code=201)
async def add_suite_cases(suite_id: int, body: SuiteCasesAdd,
                          db: AsyncSession = Depends(get_session)):
    result = await suite_service.add_cases(db, suite_id, body.case_ids)
    return result


@router.delete("/suites/{suite_id}/cases/{case_id}", status_code=204)
async def remove_suite_case(suite_id: int, case_id: int,
                            db: AsyncSession = Depends(get_session)):
    await suite_service.remove_case(db, suite_id, case_id)
    return Response(status_code=204)


@router.patch("/suites/{suite_id}/cases/{case_id}")
async def toggle_suite_case(suite_id: int, case_id: int, body: SuiteCaseToggle,
                            db: AsyncSession = Depends(get_session)):
    """GAP-38：临时启用/跳过一次用例，保留成员与排序。"""
    member = await suite_service.set_member_enabled(
        db, suite_id, case_id, body.enabled)
    return {"suite_id": suite_id, "case_id": case_id, "enabled": bool(member.enabled)}


@router.put("/suites/{suite_id}/cases/order")
async def reorder_suite_cases(suite_id: int, body: SuiteCaseOrder,
                              db: AsyncSession = Depends(get_session)):
    await suite_service.reorder_cases(db, suite_id, body.ordered_case_ids)
    return {"suite_id": suite_id, "ordered_case_ids": body.ordered_case_ids}


@router.post("/suites/{suite_id}:run", status_code=202)
async def run_suite(suite_id: int, db: AsyncSession = Depends(get_session)):
    """单次运行用例集 → 立即返回 202，实际执行走队列。"""
    execution = await suite_service.run(db, suite_id, trigger_type="MANUAL")
    from app.services.execution_queue import execution_queue
    return {
        "id": execution.id, "status": str(execution.status),
        "suite_id": suite_id, "suite_name": execution.suite_name,
        "case_count": len(execution.case_ids or []),
        "queue_pending": execution_queue.pending,
    }
