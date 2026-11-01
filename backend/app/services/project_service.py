"""项目服务：P1 的写入期拦截（端与引擎必须匹配）。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import ProjectNotFound, ValidationFailed
from app.engines.registry import registry
from app.models import ExecutionTarget, Project


async def get_or_404(db: AsyncSession, project_id: int) -> Project:
    project = (await db.execute(
        select(Project).where(Project.id == project_id, Project.is_deleted.is_(False))
    )).scalar_one_or_none()
    if project is None:
        raise ProjectNotFound(f"项目 {project_id} 不存在", {"project_id": project_id})
    return project


async def list_all(db: AsyncSession) -> list[Project]:
    return list((await db.execute(
        select(Project).where(Project.is_deleted.is_(False)).order_by(Project.id)
    )).scalars().all())


async def create(db: AsyncSession, *, name: str, code: str, platform: str,
                 engine_key: str, target_id: int | None = None,
                 description: str | None = None) -> Project:
    if not name.strip() or not code.strip():
        raise ValidationFailed("项目名称与 code 不能为空")
    registry.validate_route(platform, engine_key)     # P1：写入期拦截

    existing = (await db.execute(select(Project).where(Project.code == code))).scalar_one_or_none()
    if existing:
        raise ValidationFailed(f"项目 code 已存在：{code}", {"code": code})

    project = Project(name=name.strip(), code=code.strip(), platform=platform,
                      engine_key=engine_key, target_id=target_id, description=description,
                      default_timeout_ms=settings.default_timeout_ms)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


async def update(db: AsyncSession, project_id: int, **fields) -> Project:
    project = await get_or_404(db, project_id)
    platform = fields.get("platform") or str(project.platform)
    engine_key = fields.get("engine_key") or project.engine_key
    if "platform" in fields or "engine_key" in fields:
        registry.validate_route(platform, engine_key)
        project.platform, project.engine_key = platform, engine_key
    for key in ("name", "description", "target_id", "default_timeout_ms"):
        if key in fields and fields[key] is not None:
            setattr(project, key, fields[key])
    await db.commit()
    await db.refresh(project)
    return project


async def delete(db: AsyncSession, project_id: int) -> None:
    project = await get_or_404(db, project_id)
    project.is_deleted = True
    await db.commit()


async def targets(db: AsyncSession, project_id: int | None = None) -> list[ExecutionTarget]:
    """执行目标列表（M3.6 GAP-42：排除软删行，execution/verify/scan/scaffold 自动受益）。"""
    stmt = select(ExecutionTarget).where(
        ExecutionTarget.enabled.is_(True),
        ExecutionTarget.is_deleted.is_(False),
    )
    if project_id:
        stmt = stmt.where(ExecutionTarget.project_id == project_id)
    return list((await db.execute(stmt.order_by(ExecutionTarget.id))).scalars().all())
