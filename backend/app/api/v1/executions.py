"""执行端点（M3.1：提交即返回 202 / 取消 / 报告 / 进度查询；M3.2：产物访问）。"""
from __future__ import annotations

import asyncio
import mimetypes
import os

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.errors import ExecutionNotFound, ReportNotReady
from app.models import Execution, ExecutionStepResult, TestCase
from app.schemas.requests import ExecutionCreate
from app.schemas.serialize import execution_to_dict
from app.services import artifact_service, execution_service, report_service

router = APIRouter(tags=["executions"])

TERMINAL = execution_service.TERMINAL


@router.post("/executions", status_code=202)
async def create_execution(body: ExecutionCreate,
                           db: AsyncSession = Depends(get_session)):
    """FR28：**只入队不等待**，202 返回。

    两种触发方式（M3.3）：
    * ``suite_id`` —— 执行整个用例集（推荐，报告会带上用例集名）
    * ``case_ids`` —— 临时选几条用例
    """
    if body.suite_id:
        from app.services import suite_service
        execution = await suite_service.run(
            db, body.suite_id, trigger_type="MANUAL", target_id=body.target_id)
    else:
        execution = await execution_service.submit(
            db, project_id=body.project_id, case_ids=body.case_ids,
            target_id=body.target_id)

    from app.services.execution_queue import execution_queue
    return {
        "id": execution.id,
        "status": str(execution.status),
        "suite_id": execution.suite_id,
        "suite_name": execution.suite_name,
        "queued_at": execution.created_at.isoformat(timespec="seconds")
        if execution.created_at else None,
        "queue_pending": execution_queue.pending,
    }


@router.get("/executions")
async def list_executions(project_id: int | None = None, suite_id: int | None = None,
                          limit: int = 50,
                          db: AsyncSession = Depends(get_session)):
    """GAP-39：支持按用例集筛选 —— "某个用例集最近跑得怎样"。"""
    stmt = select(Execution)
    if project_id:
        stmt = stmt.where(Execution.project_id == project_id)
    if suite_id:
        stmt = stmt.where(Execution.suite_id == suite_id)
    rows = list((await db.execute(
        stmt.order_by(Execution.id.desc()).limit(min(limit, 200)))).scalars().all())
    return {"items": [execution_to_dict(e) for e in rows], "total": len(rows)}


@router.get("/executions/{execution_id}")
async def get_execution(execution_id: int, db: AsyncSession = Depends(get_session)):
    execution = await _get(db, execution_id)
    payload = await _detail(db, execution)
    from app.services.execution_queue import execution_queue
    if str(execution.status) == "PENDING":
        payload["queue_pending"] = execution_queue.pending
    return payload


@router.post("/executions/{execution_id}:cancel")
async def cancel_execution(execution_id: int, db: AsyncSession = Depends(get_session)):
    execution = await execution_service.request_cancel(db, execution_id)
    return {"id": execution.id, "status": str(execution.status),
            "message": execution.message}


@router.get("/executions/{execution_id}/report")
async def get_report(execution_id: int, format: str = "html", download: bool = False,
                     db: AsyncSession = Depends(get_session)):
    execution = await _get(db, execution_id)
    fmt = format.lower()
    if fmt not in ("html", "json"):
        raise ReportNotReady("format 只支持 html / json", {"format": format})

    record = await report_service.find(db, execution_id, fmt)
    if record is None:
        if str(execution.status) not in TERMINAL:
            raise ReportNotReady(
                f"执行尚未结束（{execution.status}），报告未生成",
                {"execution_id": execution_id, "status": str(execution.status)})
        await report_service.generate(db, execution_id)      # 终态但缺报告 → 补生成
        record = await report_service.find(db, execution_id, fmt)
        if record is None:
            raise ReportNotReady("报告生成失败", {"execution_id": execution_id})

    if fmt == "json":
        import json
        with open(record.path, encoding="utf-8") as fp:
            return JSONResponse(content=json.load(fp))
    # 默认 inline：报告页要用 iframe 内嵌；加 ?download=1 才是附件下载
    return FileResponse(
        record.path, media_type="text/html; charset=utf-8",
        filename=f"execution-{execution_id}.html",
        content_disposition_type="attachment" if download else "inline",
    )


@router.get("/executions/{execution_id}/artifacts")
async def list_artifacts(execution_id: int, db: AsyncSession = Depends(get_session)):
    """GAP-34：列出该执行的全部产物（只给元数据 + 下载 URL）。"""
    await _get(db, execution_id)
    items = await artifact_service.list_for_execution(db, execution_id)
    return {"items": [artifact_service.to_dict(a, execution_id) for a in items],
            "total": len(items)}


@router.get("/executions/{execution_id}/artifacts/{artifact_id}")
async def download_artifact(execution_id: int, artifact_id: int,
                            db: AsyncSession = Depends(get_session)):
    """GAP-34：下载产物文件。

    归属校验（必须属于该执行）+ 目录校验（必须落在 artifacts_dir 内）都在
    ``artifact_service`` 里，端点本身不重复实现。
    """
    await _get(db, execution_id)
    artifact = await artifact_service.get_or_404(db, execution_id, artifact_id)
    path = artifact_service.resolve_path(artifact)
    media_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    # inline：截图要能直接在浏览器里预览，而不是每次都下载
    return FileResponse(path, media_type=media_type,
                        filename=os.path.basename(path),
                        content_disposition_type="inline")


async def _get(db: AsyncSession, execution_id: int) -> Execution:
    execution = (await db.execute(
        select(Execution).where(Execution.id == execution_id))).scalar_one_or_none()
    if execution is None:
        raise ExecutionNotFound(f"执行 {execution_id} 不存在", {"execution_id": execution_id})
    return execution


async def _detail(db: AsyncSession, execution: Execution) -> dict:
    results = list((await db.execute(
        select(ExecutionStepResult)
        .where(ExecutionStepResult.execution_id == execution.id)
        .order_by(ExecutionStepResult.case_id, ExecutionStepResult.seq,
                  ExecutionStepResult.attempt)
    )).scalars().all())
    case_ids = list(execution.case_ids or [])
    titles = {c.id: c.title for c in (await db.execute(
        select(TestCase).where(TestCase.id.in_(case_ids or [0])))).scalars().all()}
    payload = execution_to_dict(execution, results=results, case_titles=titles)

    # 进度：已出结果的步骤数 / 总步骤数（PENDING 时为 0）
    if str(execution.status) in ("PENDING",):
        payload["progress"] = {"done_steps": 0, "total_steps": None}
    else:
        total_steps = len({(r.case_id, r.seq) for r in results})
        done_steps = len({(r.case_id, r.seq) for r in results
                          if str(r.status) in ("PASSED", "FAILED", "ERROR")})
        payload["progress"] = {"done_steps": done_steps, "total_steps": total_steps}
    return payload
