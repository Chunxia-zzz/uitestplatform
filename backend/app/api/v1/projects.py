"""项目与执行目标端点。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.schemas.requests import ProjectCreate, ProjectUpdate
from app.schemas.serialize import project_to_dict
from app.services import project_service

router = APIRouter(tags=["projects"])


@router.get("/projects")
async def list_projects(db: AsyncSession = Depends(get_session)):
    rows = await project_service.list_all(db)
    return {"items": [project_to_dict(p) for p in rows], "total": len(rows)}


@router.post("/projects", status_code=201)
async def create_project(body: ProjectCreate, db: AsyncSession = Depends(get_session)):
    project = await project_service.create(
        db, name=body.name, code=body.code, platform=body.platform,
        engine_key=body.engine_key, target_id=body.target_id,
        description=body.description,
    )
    return project_to_dict(project)


@router.get("/projects/{project_id}")
async def get_project(project_id: int, db: AsyncSession = Depends(get_session)):
    return project_to_dict(await project_service.get_or_404(db, project_id))


@router.patch("/projects/{project_id}")
async def update_project(project_id: int, body: ProjectUpdate,
                         db: AsyncSession = Depends(get_session)):
    project = await project_service.update(db, project_id, **body.model_dump(exclude_unset=True))
    return project_to_dict(project)


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: int, db: AsyncSession = Depends(get_session)):
    await project_service.delete(db, project_id)
    return None


@router.get("/execution-targets")
async def list_targets(project_id: int | None = None,
                       db: AsyncSession = Depends(get_session)):
    rows = await project_service.targets(db, project_id)
    return {
        "items": [
            {"id": t.id, "project_id": t.project_id, "name": t.name,
             "platform": str(t.platform), "engine_key": t.engine_key,
             "base_url": t.base_url, "options": t.options, "enabled": bool(t.enabled)}
            for t in rows
        ],
        "total": len(rows),
    }
