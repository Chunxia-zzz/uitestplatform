"""用例集服务（M3.3）：CRUD / 成员 / 排序 / 运行前置校验。"""
from __future__ import annotations

import pytest

from app.core.errors import (
    SuiteCronInvalid,
    SuiteEmpty,
    SuiteMemberNotFound,
    SuiteNameDuplicated,
    ValidationFailed,
)
from app.models import Project, TestCase
from app.services import suite_service


async def _project(db, code="p1") -> Project:
    row = Project(name="P", code=code, platform="WEB", engine_key="playwright",
                  default_timeout_ms=5000)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def _case(db, project_id: int, title: str) -> TestCase:
    row = TestCase(project_id=project_id, title=title)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@pytest.mark.asyncio
async def test_create_and_duplicate_name(db):
    project = await _project(db)
    suite = await suite_service.create(db, project_id=project.id, name="冒烟")
    assert suite.schedule_enabled is False
    assert suite.schedule_cron is None

    with pytest.raises(SuiteNameDuplicated):
        await suite_service.create(db, project_id=project.id, name="冒烟")


@pytest.mark.asyncio
async def test_soft_delete_allows_recreate_same_name(db):
    project = await _project(db)
    first = await suite_service.create(db, project_id=project.id, name="回归")
    await suite_service.delete(db, first.id)
    second = await suite_service.create(db, project_id=project.id, name="回归")
    assert second.id != first.id


@pytest.mark.asyncio
async def test_cron_validation(db):
    project = await _project(db)
    suite = await suite_service.create(
        db, project_id=project.id, name="定时", schedule_cron="0 9 * * 1-5",
        schedule_enabled=True)
    assert suite.schedule_cron == "0 9 * * 1-5"
    assert suite.schedule_enabled is True

    with pytest.raises(SuiteCronInvalid):
        await suite_service.create(db, project_id=project.id, name="坏 cron",
                                   schedule_cron="每天九点")

    # 没有 cron 时不应保持启用态
    updated = await suite_service.update(db, suite.id, schedule_cron="")
    assert updated.schedule_cron is None
    assert updated.schedule_enabled is False


@pytest.mark.asyncio
async def test_add_remove_and_reorder_cases(db):
    project = await _project(db)
    c1 = await _case(db, project.id, "用例1")
    c2 = await _case(db, project.id, "用例2")
    suite = await suite_service.create(db, project_id=project.id, name="集合")

    result = await suite_service.add_cases(db, suite.id, [c1.id, c2.id, c1.id])
    assert result["added"] == [c1.id, c2.id]
    assert result["skipped"] == [c1.id]

    rows = await suite_service.list_cases(db, suite.id)
    assert [r["case"].id for r in rows] == [c1.id, c2.id]

    await suite_service.reorder_cases(db, suite.id, [c2.id, c1.id])
    rows = await suite_service.list_cases(db, suite.id)
    assert [r["case"].id for r in rows] == [c2.id, c1.id]

    await suite_service.remove_case(db, suite.id, c2.id)
    with pytest.raises(SuiteMemberNotFound):
        await suite_service.remove_case(db, suite.id, c2.id)


@pytest.mark.asyncio
async def test_add_case_from_other_project_is_rejected(db):
    p1 = await _project(db, code="p1")
    p2 = await _project(db, code="p2")
    foreign = await _case(db, p2.id, "别人的用例")
    suite = await suite_service.create(db, project_id=p1.id, name="集合")
    result = await suite_service.add_cases(db, suite.id, [foreign.id])
    assert result["invalid"] == [foreign.id]
    assert result["added"] == []


@pytest.mark.asyncio
async def test_run_empty_suite_rejected(db):
    project = await _project(db)
    suite = await suite_service.create(db, project_id=project.id, name="空集")
    with pytest.raises(SuiteEmpty):
        await suite_service.run(db, suite.id)


@pytest.mark.asyncio
async def test_run_creates_execution_with_suite_snapshot(db):
    project = await _project(db)
    case = await _case(db, project.id, "用例")
    suite = await suite_service.create(db, project_id=project.id, name="可跑")
    await suite_service.add_cases(db, suite.id, [case.id])

    execution = await suite_service.run(db, suite.id)
    assert execution.suite_id == suite.id
    assert execution.suite_name == "可跑"
    assert execution.case_ids == [case.id]
    assert str(execution.status) == "PENDING"
    assert execution.trigger_type == "MANUAL"

    refreshed = await suite_service.get_or_404(db, suite.id)
    assert refreshed.last_run_at is not None


@pytest.mark.asyncio
async def test_add_cases_requires_non_empty(db):
    project = await _project(db)
    suite = await suite_service.create(db, project_id=project.id, name="集合")
    with pytest.raises(ValidationFailed):
        await suite_service.add_cases(db, suite.id, [])
