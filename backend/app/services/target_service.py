"""执行目标服务（M3.6 GAP-42）：创建 / 详情 / 更新 / 软删。

设计依据：D29（删除置空 project.target_id）、D30（项目内活记录 name 唯一，
软删后同名可重建）、D31（软删唯一键 uk_target_name）。
软删 / 409 模式与 ``suite_service`` 完全同款。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ProjectNotFound, TargetNameDuplicated, TargetNotFound, ValidationFailed,
)
from app.engines.registry import registry
from app.models import ExecutionTarget, Project


async def _project_or_404(db: AsyncSession, project_id: int) -> Project:
    """与 suite_service 同款的项目存在性校验。"""
    project = (await db.execute(
        select(Project).where(Project.id == project_id, Project.is_deleted.is_(False))
    )).scalar_one_or_none()
    if project is None:
        raise ProjectNotFound(f"项目 {project_id} 不存在", {"project_id": project_id})
    return project


async def get_or_404(db: AsyncSession, target_id: int) -> ExecutionTarget:
    """详情：软删或不存在一律 404（幂等删除语义与 suite 一致）。"""
    target = (await db.execute(
        select(ExecutionTarget).where(
            ExecutionTarget.id == target_id, ExecutionTarget.is_deleted.is_(False))
    )).scalar_one_or_none()
    if target is None:
        raise TargetNotFound(f"执行目标 {target_id} 不存在", {"target_id": target_id})
    return target


async def _assert_name_free(db: AsyncSession, project_id: int, name: str,
                            exclude_id: int | None = None) -> None:
    """项目内活记录同名唯一（D30）：软删行（deleted_seq=id）不算冲突。"""
    stmt = select(ExecutionTarget.id).where(
        ExecutionTarget.project_id == project_id, ExecutionTarget.name == name,
        ExecutionTarget.is_deleted.is_(False))
    if exclude_id:
        stmt = stmt.where(ExecutionTarget.id != exclude_id)
    if (await db.execute(stmt.limit(1))).scalar_one_or_none():
        raise TargetNameDuplicated(
            f"项目内已存在同名执行目标「{name}」", {"name": name, "project_id": project_id})


async def create(db: AsyncSession, project_id: int, *, name: str, platform: str,
                 engine_key: str, base_url: str | None = None,
                 options: dict | None = None, enabled: bool = True) -> ExecutionTarget:
    """创建。路由校验与 project.create 完全同一把尺子（P1 写入期拦截）。"""
    await _project_or_404(db, project_id)
    name = (name or "").strip()
    if not name:
        raise ValidationFailed("执行目标名称不能为空")
    registry.validate_route(platform, engine_key)
    await _assert_name_free(db, project_id, name)

    target = ExecutionTarget(
        project_id=project_id, name=name, platform=platform, engine_key=engine_key,
        base_url=base_url, options=dict(options or {}), enabled=bool(enabled),
        deleted_seq=0,
    )
    db.add(target)
    await db.commit()
    await db.refresh(target)
    return target


async def update(db: AsyncSession, target_id: int, **fields) -> ExecutionTarget:
    """部分更新：name 变更重跑查重；platform/engine_key 任一出现联合重跑路由校验。"""
    target = await get_or_404(db, target_id)

    if "name" in fields and fields["name"] is not None:
        new_name = str(fields["name"]).strip()
        if new_name and new_name != target.name:
            await _assert_name_free(db, target.project_id, new_name, exclude_id=target.id)
            target.name = new_name
    if "platform" in fields or "engine_key" in fields:
        platform = fields.get("platform") or str(target.platform)
        engine_key = fields.get("engine_key") or target.engine_key
        registry.validate_route(platform, engine_key)
        target.platform, target.engine_key = platform, engine_key
    # base_url/options/enabled：exclude_unset 语义；显式传 null 被忽略
    # （与 project_service.update 语义一致）；base_url 不支持置空，如需变更请直接传新值
    for key in ("base_url", "options", "enabled"):
        if key in fields and fields[key] is not None:
            setattr(target, key, fields[key])

    await db.commit()
    await db.refresh(target)
    return target


async def delete(db: AsyncSession, target_id: int) -> None:
    """软删（D29/D30）：三件套 + 置空 project.target_id 引用。

    * 不级联动任何 execution 行（历史快照自洽）；
    * UPDATE 置空语句无论当前是否被引用都执行（rowcount 不做条件）；
    * 已删再删走 get_or_404 抛 404（幂等语义与 suite 一致）。
    """
    target = await get_or_404(db, target_id)
    target.is_deleted = True
    target.deleted_at = datetime.now()
    target.deleted_seq = target.id          # 与 element / suite 同一套软删唯一键方案
    await db.execute(sa_update(Project).where(Project.target_id == target.id)
                     .values(target_id=None))
    await db.commit()
