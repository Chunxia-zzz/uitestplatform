"""执行目标服务（M3.6 GAP-42）：CRUD / 路由校验 / 软删 / 引用置空。"""
from __future__ import annotations

import pytest

from app.core.errors import (
    EngineNotFound,
    ProjectNotFound,
    ProjectPlatformEngineMismatch,
    TargetNameDuplicated,
    TargetNotFound,
    ValidationFailed,
)
from app.models import Project
from app.services import project_service, target_service


async def _project(db, code: str = "p1") -> Project:
    row = Project(name="P", code=code, platform="WEB", engine_key="playwright",
                  default_timeout_ms=5000)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def _target(db, project: Project, name: str = "t1", **kw):
    return await target_service.create(
        db, project.id, name=name, platform="WEB", engine_key="playwright", **kw)


# ─────────────────────────── 创建 ───────────────────────────
@pytest.mark.asyncio
async def test_create_ok(db):
    project = await _project(db)
    target = await _target(db, project, name="线上环境", base_url="http://x",
                           options={"browser": "chromium"})
    assert target.id and target.project_id == project.id
    assert target.name == "线上环境"
    assert str(target.platform) == "WEB"
    assert target.engine_key == "playwright"
    assert target.base_url == "http://x"
    assert target.options == {"browser": "chromium"}
    assert target.enabled is True
    assert target.deleted_seq == 0          # D30：活记录 deleted_seq=0


@pytest.mark.asyncio
async def test_create_duplicate_name_409(db):
    project = await _project(db)
    await _target(db, project, name="同名字")
    with pytest.raises(TargetNameDuplicated):
        await _target(db, project, name="同名字")


@pytest.mark.asyncio
async def test_create_project_not_found_404(db):
    with pytest.raises(ProjectNotFound):
        await target_service.create(db, 9999, name="x", platform="WEB",
                                    engine_key="playwright")


@pytest.mark.asyncio
async def test_create_route_mismatch_422(db):
    """WEB + appium → 422 PROJECT_PLATFORM_ENGINE_MISMATCH（与 project.create 同尺子）。"""
    project = await _project(db)
    with pytest.raises(ProjectPlatformEngineMismatch):
        await target_service.create(db, project.id, name="错路由", platform="WEB",
                                    engine_key="appium")


@pytest.mark.asyncio
async def test_create_engine_not_registered_404(db):
    project = await _project(db)
    with pytest.raises(EngineNotFound):
        await target_service.create(db, project.id, name="x", platform="WEB",
                                    engine_key="nope")


@pytest.mark.asyncio
async def test_create_empty_name_422(db):
    project = await _project(db)
    with pytest.raises(ValidationFailed):
        await target_service.create(db, project.id, name="  ", platform="WEB",
                                    engine_key="playwright")


# ─────────────────────────── 详情 / 更新 ───────────────────────
@pytest.mark.asyncio
async def test_get_or_404(db):
    project = await _project(db)
    target = await _target(db, project)
    got = await target_service.get_or_404(db, target.id)
    assert got.id == target.id
    with pytest.raises(TargetNotFound):
        await target_service.get_or_404(db, 99999)


@pytest.mark.asyncio
async def test_update_partial_fields_kept(db):
    """exclude_unset 语义：只改 base_url，其他字段不动。"""
    project = await _project(db)
    target = await _target(db, project, name="原名", base_url="http://a",
                           options={"browser": "chromium"})
    updated = await target_service.update(db, target.id, base_url="http://b")
    assert updated.base_url == "http://b"
    assert updated.name == "原名"
    assert updated.options == {"browser": "chromium"}
    assert updated.enabled is True


@pytest.mark.asyncio
async def test_update_rename_conflict_409(db):
    project = await _project(db)
    first = await _target(db, project, name="甲")
    second = await _target(db, project, name="乙")
    with pytest.raises(TargetNameDuplicated):
        await target_service.update(db, second.id, name=first.name)
    # 改成自己名字不算冲突
    ok = await target_service.update(db, second.id, name="乙")
    assert ok.name == "乙"


@pytest.mark.asyncio
async def test_update_route_joint_validation_422(db):
    """platform / engine_key 任一出现即联合重跑 validate_route（与 project.update 同款）。"""
    project = await _project(db)
    target = await _target(db, project)
    with pytest.raises(ProjectPlatformEngineMismatch):
        await target_service.update(db, target.id, platform="ANDROID")


# ─────────────────────────── 软删（D29/D30）────────────────────
@pytest.mark.asyncio
async def test_soft_delete_then_recreate_same_name(db):
    project = await _project(db)
    first = await _target(db, project, name="环境")
    await target_service.delete(db, first.id)
    assert first.deleted_seq == first.id    # D30：deleted_seq=id
    assert first.is_deleted is True
    second = await _target(db, project, name="环境")   # 同名可重建
    assert second.id != first.id and second.deleted_seq == 0


@pytest.mark.asyncio
async def test_delete_clears_project_target_id(db):
    project = await _project(db)
    target = await _target(db, project)
    project.target_id = target.id
    await db.commit()
    await target_service.delete(db, target.id)
    await db.refresh(project)
    assert project.target_id is None        # D29：引用置空


@pytest.mark.asyncio
async def test_delete_twice_404(db):
    """幂等：已删再删返回 404（与 suite 一致）。"""
    project = await _project(db)
    target = await _target(db, project)
    await target_service.delete(db, target.id)
    with pytest.raises(TargetNotFound):
        await target_service.delete(db, target.id)


@pytest.mark.asyncio
async def test_target_list_excludes_deleted(db):
    """project_service.targets() 加 is_deleted 过滤，软删行不再出现。"""
    project = await _project(db)
    target = await _target(db, project)
    assert [t.id for t in await project_service.targets(db)] == [target.id]
    await target_service.delete(db, target.id)
    assert await project_service.targets(db) == []
