"""用例集定时调度（M3.3）。

用 APScheduler 的 AsyncIOScheduler：单进程、内存 job store。
* 与队列一致，**单进程语义**（D23/FR40）：进程重启后按数据库重建 job
* 不依赖 Redis / 独立调度服务
* ``coalesce=True`` + ``misfire_grace_time=60``：停机错过的任务只补一次，不堆积
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.core.config import settings
from app.core.db import SessionLocal
from app.models import TestSuite

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone=settings.timezone)


async def _trigger(suite_id: int) -> None:
    from app.services import suite_service

    async with SessionLocal() as db:
        try:
            execution = await suite_service.run(db, suite_id, trigger_type="SCHEDULE")
            logger.info("scheduled suite %s -> execution %s", suite_id, execution.id,
                        extra={"event": "suite.scheduled", "suite_id": suite_id,
                               "execution_id": execution.id})
        except Exception:
            logger.exception("scheduled suite %s failed", suite_id)


def _job_id(suite_id: int) -> str:
    return f"suite:{suite_id}"


def sync_suite(suite: TestSuite) -> None:
    """新增/修改/删除用例集后同步 job（幂等）。"""
    job_id = _job_id(suite.id)
    if job_id in {job.id for job in scheduler.get_jobs()}:
        scheduler.remove_job(job_id)

    if suite.is_deleted or not suite.schedule_enabled or not suite.schedule_cron:
        return
    try:
        trigger = CronTrigger.from_crontab(suite.schedule_cron, timezone=settings.timezone)
    except ValueError:
        logger.warning("invalid cron for suite %s: %s", suite.id, suite.schedule_cron)
        return
    scheduler.add_job(
        _trigger, trigger, args=[suite.id], id=job_id,
        replace_existing=True, coalesce=True, max_instances=1,
        misfire_grace_time=60,
    )


async def start() -> None:
    if not scheduler.running:
        scheduler.start()
    await reload_all()
    logger.info("scheduler started", extra={
        "event": "scheduler.start", "jobs": len(scheduler.get_jobs()),
        "timezone": settings.timezone,
    })


async def stop() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)


async def reload_all() -> None:
    """启动时从数据库重建全部定时任务。"""
    for job in list(scheduler.get_jobs()):
        scheduler.remove_job(job.id)

    async with SessionLocal() as db:
        suites = list((await db.execute(
            select(TestSuite).where(TestSuite.is_deleted.is_(False),
                                    TestSuite.schedule_enabled.is_(True)))).scalars().all())
    for suite in suites:
        sync_suite(suite)


def jobs() -> list[dict]:
    return [{"id": job.id, "next_run": str(getattr(job, "next_run_time", None))}
            for job in scheduler.get_jobs()]
