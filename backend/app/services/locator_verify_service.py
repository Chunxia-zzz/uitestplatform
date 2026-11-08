"""★ 定位符验证器（D14 的支点 / M2 §2.8）。

不做拾取器（D14），就必须让"这条定位符到底能不能命中"变成**可一键确认**的事实，
否则元素库会退化成一堆没人验证过的字符串。

设计要点：
* **逐条独立探测**，不是跑整条回退链 —— 回退链只能告诉你"第 N 条命中"，其余好坏未知
* **只读**：只 navigate + probe，绝不执行写动作
* **必须清理**：``finally`` 里 stop，否则会留僵尸 Chromium 进程
* **项目级串行**：同时起多个浏览器会打爆内存（M3 多 worker 时换 Redis 分布式锁）
"""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import (
    BatchLimitExceeded,
    LocatorVerifyTargetRequired,
    LocatorVerifyTimeout,
    ProjectNotFound,
    ValidationFailed,
)
from app.domain.enums import VerifySummary, VerifyVerdict
from app.engines.base import ActionContext, Locator, LocatorChain, SessionConfig
from app.engines.registry import registry
from app.engines.session import SessionManager
from app.models import ExecutionTarget, Project
from app.repositories.locator_repo import locator_repo
from app.services.element_service import get_or_404
from app.services.locator_service import mark_verified

logger = logging.getLogger(__name__)

_project_locks: dict[int, asyncio.Lock] = {}


@asynccontextmanager
async def _project_lock(project_id: int):
    lock = _project_locks.setdefault(project_id, asyncio.Lock())
    async with lock:
        yield


async def _resolve_target(db: AsyncSession, project: Project, target_id: int | None):
    tid = target_id or project.target_id
    if not tid:
        return None
    return (await db.execute(select(ExecutionTarget).where(ExecutionTarget.id == tid))
            ).scalar_one_or_none()


def _judge(matched: int, error: str | None) -> str:
    if error:
        return VerifyVerdict.ERROR
    if matched == 1:
        return VerifyVerdict.VALID
    if matched > 1:
        return VerifyVerdict.MULTIPLE
    return VerifyVerdict.NONE


async def verify(db: AsyncSession, element_id: int, *, platform: str, engine_key: str,
                 target_id: int | None = None, url: str | None = None,
                 include_saved: bool = True,
                 drafts: list[dict] | None = None) -> dict:
    element = await get_or_404(db, element_id)
    project = (await db.execute(select(Project).where(Project.id == element.project_id))
               ).scalar_one_or_none()
    if project is None:
        raise ProjectNotFound(f"项目 {element.project_id} 不存在")

    target = await _resolve_target(db, project, target_id)
    if target is None and not url:
        raise LocatorVerifyTargetRequired(
            "必须提供 target_id（或项目默认执行目标），或直接给 url",
            {"element_id": element_id},
        )

    candidates: list[dict] = []
    if include_saved:
        for row in await locator_repo.group_rows(db, element_id, platform, engine_key):
            candidates.append({
                "locator_id": row.id, "locator_type": row.locator_type,
                "locator_value": row.locator_value,
                "locator": Locator(type=row.locator_type, value=row.locator_value,
                                   locator_id=row.id),
            })
    for draft in drafts or []:
        candidates.append({
            "locator_id": None,
            "locator_type": draft["locator_type"],
            "locator_value": draft["locator_value"],
            "locator": Locator(type=draft["locator_type"], value=draft["locator_value"]),
        })

    if not candidates:
        raise ValidationFailed("没有可验证的定位符（既无已保存的，也没有草稿）")
    if len(candidates) > settings.verify_max_locators:
        raise BatchLimitExceeded(
            f"单次最多验证 {settings.verify_max_locators} 条",
            {"limit": settings.verify_max_locators, "actual": len(candidates)},
        )

    base_url = target.base_url if target else None
    navigate_to = url or base_url
    config = SessionConfig(
        platform=platform, engine_key=engine_key, base_url=base_url,
        options=dict(target.options or {}) if target else {},
        headless=settings.headless, timeout_ms=project.default_timeout_ms,
    )

    started = time.perf_counter()
    async with _project_lock(project.id):
        manager = SessionManager(registry)
        results: list[dict] = []
        stage = "start"
        try:
            async def _run() -> None:
                nonlocal stage
                adapter = await manager.open(config)
                stage = "navigate"
                if navigate_to:
                    await adapter.navigate(
                        None, ActionContext(timeout_ms=project.default_timeout_ms),
                        url=navigate_to)
                stage = "probe"
                for cand in candidates:
                    probe_ctx = ActionContext(timeout_ms=int(
                        settings.verify_probe_timeout_s * 1000))
                    chain = LocatorChain.of(element_id, [cand["locator"]])
                    probe = await asyncio.wait_for(
                        adapter.probe_locator(chain, probe_ctx),
                        timeout=settings.verify_probe_timeout_s)
                    verdict = _judge(probe.count, probe.error)
                    results.append({
                        "locator_id": cand["locator_id"],
                        "locator_type": cand["locator_type"],
                        "locator_value": cand["locator_value"],
                        "verdict": str(verdict),
                        "matched": probe.count,
                        "duration_ms": probe.elapsed_ms,
                        "sample": probe.sample,
                        "error": probe.error,
                    })

            await asyncio.wait_for(_run(), timeout=settings.verify_total_timeout_s)
        except TimeoutError as exc:
            raise LocatorVerifyTimeout(
                f"验证超时（>{settings.verify_total_timeout_s}s），当前阶段：{stage}",
                {"stage": stage, "timeout_s": settings.verify_total_timeout_s},
            ) from exc
        except NotImplementedError as exc:
            raise ValidationFailed(
                f"引擎 {engine_key} 尚未实现，无法验证", {"reason": str(exc)}
            ) from exc
        finally:
            await manager.close_all()

    # 落库：只有确定无效才落 INVALID；matched>1 只写 probe_detail 供 UI 警告
    now = datetime.now()
    for item in results:
        if item["locator_id"] is None:
            continue
        locator = await locator_repo.get(db, item["locator_id"])
        if locator is None:
            continue
        mark_verified(locator, matched=item["matched"], verdict=item["verdict"],
                      sample=item["sample"], error=item["error"])
    await db.commit()

    summary = {
        "valid": sum(1 for r in results if r["verdict"] == VerifyVerdict.VALID),
        "multiple": sum(1 for r in results if r["verdict"] == VerifyVerdict.MULTIPLE),
        "none": sum(1 for r in results if r["verdict"] == VerifyVerdict.NONE),
        "error": sum(1 for r in results if r["verdict"] == VerifyVerdict.ERROR),
    }
    if summary["valid"] == len(results):
        verdict = VerifySummary.ALL_VALID
    elif summary["none"] + summary["error"] == len(results):
        verdict = VerifySummary.ALL_INVALID
    else:
        verdict = VerifySummary.HAS_PROBLEM

    return {
        "checked_at": now.isoformat(timespec="seconds"),
        "target_id": target.id if target else None,
        "url": navigate_to,
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "results": results,
        "summary": summary,
        "verdict": str(verdict),
    }
