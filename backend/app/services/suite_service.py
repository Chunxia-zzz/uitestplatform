"""用例集服务（M3.3）：项目 → **用例集** → 用例 → 元素+动作。

用例集是**执行单元**：单次手动运行，或按 cron 定时运行，产出报告。
本模块只管"成员与调度配置"，真正的执行交给 ``execution_service.submit``。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ProjectNotFound, SuiteCronInvalid, SuiteEmpty, SuiteMemberNotFound,
    SuiteNameDuplicated, SuiteNotFound, ValidationFailed,
)
from app.models import Project, TestCase, TestSuite, TestSuiteCase
from app.services import tree_service


def validate_cron(expr: str | None) -> str | None:
    """5 段 cron 校验（分 时 日 月 周）。空串归一为 None（只手动运行）。"""
    if expr is None:
        return None
    value = expr.strip()
    if not value:
        return None
    from apscheduler.triggers.cron import CronTrigger

    try:
        CronTrigger.from_crontab(value)
    except (ValueError, TypeError) as exc:
        raise SuiteCronInvalid(
            f"cron 表达式不合法：{value}（需 5 段：分 时 日 月 周）",
            {"cron": value, "reason": str(exc)},
        ) from exc
    return value


async def get_or_404(db: AsyncSession, suite_id: int) -> TestSuite:
    suite = (await db.execute(
        select(TestSuite).where(TestSuite.id == suite_id, TestSuite.is_deleted.is_(False))
    )).scalar_one_or_none()
    if suite is None:
        raise SuiteNotFound(f"用例集 {suite_id} 不存在", {"suite_id": suite_id})
    return suite


async def _project_or_404(db: AsyncSession, project_id: int) -> Project:
    project = (await db.execute(
        select(Project).where(Project.id == project_id, Project.is_deleted.is_(False))
    )).scalar_one_or_none()
    if project is None:
        raise ProjectNotFound(f"项目 {project_id} 不存在", {"project_id": project_id})
    return project


async def _assert_name_free(db: AsyncSession, project_id: int, name: str,
                            exclude_id: int | None = None) -> None:
    stmt = select(TestSuite.id).where(
        TestSuite.project_id == project_id, TestSuite.name == name,
        TestSuite.is_deleted.is_(False))
    if exclude_id:
        stmt = stmt.where(TestSuite.id != exclude_id)
    if (await db.execute(stmt.limit(1))).scalar_one_or_none():
        raise SuiteNameDuplicated(f"项目内已存在同名用例集「{name}」",
                                  {"name": name, "project_id": project_id})


async def list_suites(db: AsyncSession, project_id: int) -> list[dict]:
    rows = list((await db.execute(
        select(TestSuite).where(TestSuite.project_id == project_id,
                                TestSuite.is_deleted.is_(False))
        .order_by(TestSuite.id))).scalars().all())
    counts = dict((await db.execute(
        select(TestSuiteCase.suite_id, func.count(TestSuiteCase.id))
        .where(TestSuiteCase.suite_id.in_([r.id for r in rows] or [0]))
        .group_by(TestSuiteCase.suite_id))).all())
    return [{"suite": row, "case_count": int(counts.get(row.id, 0))} for row in rows]


async def create(db: AsyncSession, *, project_id: int, name: str,
                 description: str | None = None, schedule_cron: str | None = None,
                 schedule_enabled: bool = False) -> TestSuite:
    await _project_or_404(db, project_id)
    name = (name or "").strip()
    if not name:
        raise ValidationFailed("用例集名称不能为空")
    await _assert_name_free(db, project_id, name)
    cron = validate_cron(schedule_cron)

    suite = TestSuite(project_id=project_id, name=name, description=description,
                      schedule_cron=cron, schedule_enabled=bool(schedule_enabled and cron),
                      deleted_seq=0)
    db.add(suite)
    await db.commit()
    await db.refresh(suite)
    return suite


async def update(db: AsyncSession, suite_id: int, *, name: str | None = None,
                 description: str | None = None, schedule_cron: str | None = None,
                 schedule_enabled: bool | None = None) -> TestSuite:
    suite = await get_or_404(db, suite_id)
    if name is not None and name.strip() != suite.name:
        new_name = name.strip()
        if not new_name:
            raise ValidationFailed("用例集名称不能为空")
        await _assert_name_free(db, suite.project_id, new_name, exclude_id=suite.id)
        suite.name = new_name
    if description is not None:
        suite.description = description
    if schedule_cron is not None:
        suite.schedule_cron = validate_cron(schedule_cron)
    if schedule_enabled is not None:
        suite.schedule_enabled = bool(schedule_enabled)
    # 没有 cron 就不该处于启用态
    if not suite.schedule_cron:
        suite.schedule_enabled = False
    await db.commit()
    await db.refresh(suite)
    return suite


async def delete(db: AsyncSession, suite_id: int) -> None:
    suite = await get_or_404(db, suite_id)
    suite.is_deleted = True
    suite.deleted_at = datetime.now()
    suite.deleted_seq = suite.id          # 与 element 同一套软删唯一键方案
    await db.execute(sa_delete(TestSuiteCase).where(TestSuiteCase.suite_id == suite.id))
    await db.commit()


# ─────────────────────────── 成员 ───────────────────────────
async def list_cases(db: AsyncSession, suite_id: int) -> list[dict]:
    rows = (await db.execute(
        select(TestSuiteCase, TestCase)
        .join(TestCase, TestCase.id == TestSuiteCase.case_id)
        .where(TestSuiteCase.suite_id == suite_id,
               TestCase.is_deleted.is_(False))
        .order_by(TestSuiteCase.sort, TestSuiteCase.id))).all()
    return [{"member": member, "case": case} for member, case in rows]


async def enabled_case_ids(db: AsyncSession, suite_id: int) -> list[int]:
    rows = (await db.execute(
        select(TestSuiteCase.case_id)
        .where(TestSuiteCase.suite_id == suite_id, TestSuiteCase.enabled.is_(True))
        .order_by(TestSuiteCase.sort, TestSuiteCase.id))).scalars().all()
    return [int(x) for x in rows]


async def add_cases(db: AsyncSession, suite_id: int, case_ids: list[int]) -> dict:
    suite = await get_or_404(db, suite_id)
    if not case_ids:
        raise ValidationFailed("case_ids 不能为空")

    existing = set(await enabled_case_ids(db, suite_id))
    existing |= set((await db.execute(
        select(TestSuiteCase.case_id).where(TestSuiteCase.suite_id == suite_id)
    )).scalars().all())

    added, skipped, invalid = [], [], []
    next_sort = (await db.execute(
        select(func.coalesce(func.max(TestSuiteCase.sort), 0))
        .where(TestSuiteCase.suite_id == suite_id))).scalar_one()

    for case_id in case_ids:
        if case_id in existing:
            skipped.append(case_id)
            continue
        case = (await db.execute(
            select(TestCase).where(TestCase.id == case_id,
                                  TestCase.is_deleted.is_(False)))).scalar_one_or_none()
        if case is None or case.project_id != suite.project_id:
            invalid.append(case_id)
            continue
        next_sort += 10
        db.add(TestSuiteCase(suite_id=suite_id, case_id=case_id, sort=next_sort))
        existing.add(case_id)             # 同一次请求里重复传入也要去重
        added.append(case_id)

    await db.commit()
    return {"added": added, "skipped": skipped, "invalid": invalid}


async def remove_case(db: AsyncSession, suite_id: int, case_id: int) -> None:
    await get_or_404(db, suite_id)
    result = await db.execute(sa_delete(TestSuiteCase).where(
        TestSuiteCase.suite_id == suite_id, TestSuiteCase.case_id == case_id))
    if not (result.rowcount or 0):
        raise SuiteMemberNotFound(
            f"用例 {case_id} 不在该用例集中", {"case_id": case_id, "suite_id": suite_id})
    await db.commit()


async def set_member_enabled(db: AsyncSession, suite_id: int, case_id: int,
                             enabled: bool) -> TestSuiteCase:
    """GAP-38：临时跳一条用例，不必先移除再重新加（会丢排序）。"""
    await get_or_404(db, suite_id)
    member = (await db.execute(
        select(TestSuiteCase).where(TestSuiteCase.suite_id == suite_id,
                                    TestSuiteCase.case_id == case_id)
    )).scalar_one_or_none()
    if member is None:
        raise SuiteMemberNotFound(
            f"用例 {case_id} 不在该用例集中", {"case_id": case_id, "suite_id": suite_id})
    member.enabled = bool(enabled)
    await db.commit()
    await db.refresh(member)
    return member


async def reorder_cases(db: AsyncSession, suite_id: int, ordered_case_ids: list[int]) -> None:
    await get_or_404(db, suite_id)
    current = [int(x) for x in (await db.execute(
        select(TestSuiteCase.case_id).where(TestSuiteCase.suite_id == suite_id)
    )).scalars().all()]
    tree_service.assert_order_complete(current, ordered_case_ids)
    for index, case_id in enumerate(ordered_case_ids, start=1):
        member = (await db.execute(
            select(TestSuiteCase).where(TestSuiteCase.suite_id == suite_id,
                                        TestSuiteCase.case_id == case_id))).scalar_one()
        member.sort = index * 10
    await db.commit()


# ─────────────────────────── 运行 ───────────────────────────
async def run(db: AsyncSession, suite_id: int, *, trigger_type: str = "MANUAL",
              target_id: int | None = None):
    """按用例集提交一次执行（单次手动 / 定时都走这里）。"""
    from app.domain.enums import TriggerType
    from app.services import execution_service

    suite = await get_or_404(db, suite_id)
    case_ids = await enabled_case_ids(db, suite.id)
    if not case_ids:
        raise SuiteEmpty(f"用例集「{suite.name}」没有可执行的用例",
                         {"suite_id": suite.id})

    execution = await execution_service.submit(
        db, project_id=suite.project_id, case_ids=case_ids, target_id=target_id,
        suite_id=suite.id, suite_name=suite.name,
        trigger_type=TriggerType(trigger_type),
    )
    suite.last_run_at = datetime.now()
    await db.commit()
    return execution
