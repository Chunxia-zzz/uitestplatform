"""页面扫描服务（M3.5 / D28）。

两个职责：
1. ``scan()`` —— 打开 URL，抓取可见元素，返回候选清单（**不落库**）；
2. ``import_candidates()`` —— 把用户确认的候选批量写入元素库（复用既有服务）。

扫描是平台诊断能力（FR62），通过适配器的 ``scan_dom()`` 完成，不进 action_catalog。
"""
from __future__ import annotations

import asyncio
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import (
    ProjectNotFound,
    ScanEmptyCandidates,
    ScanImportEmpty,
    ScanTargetRequired,
    ValidationFailed,
)
from app.domain.scan import build_candidates
from app.engines.base import ActionContext, SessionConfig
from app.engines.registry import registry
from app.engines.session import SessionManager
from app.models import ExecutionTarget, Project
from app.schemas.scan import ScanImportRequest, ScanRequest
from app.services import element_service, locator_service

_SCAN_LOCK: dict[int, asyncio.Lock] = {}


def _project_lock(project_id: int) -> asyncio.Lock:
    """同一项目串行扫描：避免并发打开多个浏览器。"""
    lock = _SCAN_LOCK.get(project_id)
    if lock is None:
        lock = asyncio.Lock()
        _SCAN_LOCK[project_id] = lock
    return lock


async def _resolve_target(db: AsyncSession, project: Project, url: str | None):
    """返回 (target, 要打开的 URL)。"""
    target = None
    if project.target_id:
        target = (await db.execute(
            select(ExecutionTarget).where(ExecutionTarget.id == project.target_id)
        )).scalar_one_or_none()

    if url:
        return target, url
    if target and target.base_url:
        return target, target.base_url
    raise ScanTargetRequired(
        "既未提供 url，项目也没有可用的执行目标", {"project_id": project.id})


async def scan(db: AsyncSession, project_id: int, req: ScanRequest) -> dict:
    project = (await db.execute(
        select(Project).where(Project.id == project_id, Project.is_deleted.is_(False))
    )).scalar_one_or_none()
    if project is None:
        raise ProjectNotFound(f"项目 {project_id} 不存在", {"project_id": project_id})

    target, navigate_to = await _resolve_target(db, project, req.url)
    base_url = target.base_url if target else None

    config = SessionConfig(
        platform=str(project.platform), engine_key=project.engine_key,
        base_url=base_url,
        options=dict(target.options or {}) if target else {},
        headless=settings.headless, timeout_ms=project.default_timeout_ms,
    )

    started = time.perf_counter()
    async with _project_lock(project.id):
        manager = SessionManager(registry)
        stage = "start"
        try:
            async def _run() -> list[dict]:
                nonlocal stage
                adapter = await manager.open(config)
                stage = "navigate"
                # 扫描默认等 networkidle（SPA 需要），不等 domcontentloaded
                await adapter.navigate(
                    None, ActionContext(timeout_ms=project.default_timeout_ms),
                    url=navigate_to, wait_until="networkidle")
                stage = "scan"
                raw = await adapter.scan_dom(
                    ActionContext(timeout_ms=project.default_timeout_ms),
                    max_elements=req.max_elements)
                return raw or []

            raw = await asyncio.wait_for(_run(), timeout=settings.verify_total_timeout_s)
        except TimeoutError as exc:
            raise ScanEmptyCandidates(
                f"扫描超时（>{settings.verify_total_timeout_s}s），当前阶段：{stage}",
                {"stage": stage}) from exc
        except NotImplementedError as exc:
            raise ValidationFailed(
                f"引擎 {project.engine_key} 不支持页面扫描（Appium/u2 仍是桩，见 M4）",
                {"reason": str(exc)}) from exc
        finally:
            await manager.close_all()

    candidates, stats = build_candidates(raw, max_elements=req.max_elements)
    if not candidates:
        raise ScanEmptyCandidates(
            f"页面 {navigate_to} 没有可导入的可见元素", {"url": navigate_to})

    warnings: list[str] = []
    if stats["skipped"]:
        warnings.append(f"跳过 {stats['skipped']} 个不可见/纯容器/重复元素")

    return {
        "url": navigate_to,
        "candidates": [c.to_dict() for c in candidates],
        "stats": stats,
        "warnings": warnings,
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }


async def import_candidates(db: AsyncSession, project_id: int,
                            req: ScanImportRequest) -> dict:
    project = (await db.execute(
        select(Project).where(Project.id == project_id, Project.is_deleted.is_(False))
    )).scalar_one_or_none()
    if project is None:
        raise ProjectNotFound(f"项目 {project_id} 不存在", {"project_id": project_id})
    if not req.candidates:
        raise ScanImportEmpty("导入的候选清单不能为空", {})

    created: list[dict] = []
    failed: list[dict] = []

    for candidate in req.candidates:
        try:
            element = await element_service.create(
                db, project_id=project_id, parent_id=0,
                element_name=candidate.name, node_type="ELEMENT")
            locator_ids: list[int] = []
            if candidate.locators:
                result = await locator_service.create_bulk(
                    db, element.id,
                    [{"platform": str(project.platform),
                      "engine_key": project.engine_key,
                      "locator_type": loc.locator_type,
                      "locator_value": loc.locator_value}
                     for loc in candidate.locators])
                locator_ids = result["created"]
                if result["failed"]:
                    failed.append({
                        "name": candidate.name, "element_id": element.id,
                        "code": "LOCATOR_PARTIAL",
                        "message": f"{len(result['failed'])} 条定位符写入失败",
                        "detail": result["failed"],
                    })
            created.append({
                "name": candidate.name, "element_id": element.id,
                "locator_ids": locator_ids,
            })
        except Exception as exc:                     # noqa: BLE001 —— 逐条报告
            failed.append({
                "name": candidate.name,
                "code": getattr(exc, "code", "ERROR"),
                "message": getattr(exc, "message", str(exc)),
            })

    return {"created": created, "failed": failed}
