"""执行目标端点（M3.6 GAP-42）。

四个新端点全部收在本文件（projects.py 的 GET /execution-targets 保持不动）；
TargetOut 序列化与既有列表项字段一致，前端零适配。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.schemas.requests import TargetCreate, TargetUpdate
from app.schemas.serialize import target_to_dict
from app.services import target_service

router = APIRouter(tags=["targets"])


@router.post("/projects/{project_id}/execution-targets", status_code=201)
async def create_target(project_id: int, body: TargetCreate,
                        db: AsyncSession = Depends(get_session)):
    target = await target_service.create(
        db, project_id, name=body.name, platform=body.platform,
        engine_key=body.engine_key, base_url=body.base_url,
        options=body.options, enabled=body.enabled,
    )
    return target_to_dict(target)


@router.get("/execution-targets/{target_id}")
async def get_target(target_id: int, db: AsyncSession = Depends(get_session)):
    return target_to_dict(await target_service.get_or_404(db, target_id))


@router.patch("/execution-targets/{target_id}")
async def update_target(target_id: int, body: TargetUpdate,
                        db: AsyncSession = Depends(get_session)):
    target = await target_service.update(db, target_id, **body.model_dump(exclude_unset=True))
    return target_to_dict(target)


@router.delete("/execution-targets/{target_id}", status_code=204)
async def delete_target(target_id: int, db: AsyncSession = Depends(get_session)):
    """204 软删；副作用：project.target_id 引用被置空（D29）。"""
    await target_service.delete(db, target_id)
    return Response(status_code=204)
