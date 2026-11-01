"""执行服务（M3.1：提交与执行分离 / 重试 / 取消 / 产物 / 报告 / 事件）。

关键约束：
* ``submit()`` 只建 PENDING 记录并入队，**立即返回**（FR28）
* ``execute()`` 在 worker 内用**独立 session** 跑，请求 session 早已关闭
* 每次尝试写一行 ``execution_step_result``（``attempt`` 递增，FR32）
"""
from __future__ import annotations

import asyncio
import fnmatch
import logging
import os
import time
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.errors import (
    CaseNotFound, ExecutionCannotCancel, ExecutionNotFound, QueueFull, ValidationFailed,
)
from app.domain.action_keys import ACTION_BY_KEY
from app.domain.diagnostics import resolve_diagnostics
from app.domain.enums import ExecutionStatus, StepStatus, TriggerType
from app.engines.actions import dispatch
from app.engines.base import ActionContext, SessionConfig
from app.engines.registry import registry
from app.engines.session import SessionManager
from app.models import Artifact, Execution, ExecutionStepResult, TestCase, TestStep
from app.services.element_service import resolve_chain_for
from app.services.event_bus import ExecutionEvents
from app.services.project_service import get_or_404 as get_project
from app.services.project_service import targets as list_targets
from app.services import notify_service
from app.services.report_service import generate as generate_report

logger = logging.getLogger(__name__)

TERMINAL = {"PASSED", "FAILED", "ERROR", "CANCELLED"}

#: 运行中的取消标记（D22：只在步骤之间检查，不强杀浏览器）
_cancel_flags: set[int] = set()


def max_attempts(step: TestStep) -> int:
    """RETRY 才多重试；其余策略只跑一次。"""
    if str(step.on_failure) == "RETRY" and step.retry_times > 0:
        return step.retry_times + 1
    return 1


def _is_cancelled(execution_id: int) -> bool:
    return execution_id in _cancel_flags


# ─────────────────────────── 提交 ───────────────────────────
async def submit(db: AsyncSession, *, project_id: int, case_ids: list[int],
                 target_id: int | None, suite_id: int | None = None,
                 suite_name: str | None = None,
                 trigger_type: TriggerType = TriggerType.MANUAL) -> Execution:
    project = await get_project(db, project_id)
    if not case_ids:
        raise ValidationFailed("case_ids 不能为空")

    cases = []
    for case_id in case_ids:
        case = (await db.execute(select(TestCase).where(
            TestCase.id == case_id, TestCase.is_deleted.is_(False)))).scalar_one_or_none()
        if case is None or case.project_id != project_id:
            raise CaseNotFound(f"用例 {case_id} 不存在或不属于项目 {project_id}",
                               {"case_id": case_id})
        cases.append(case)

    if target_id or project.target_id:
        wanted = target_id or project.target_id
        found = [t for t in await list_targets(db, project_id) if t.id == wanted]
        if not found:
            raise ValidationFailed(f"执行目标 {wanted} 不存在", {"target_id": wanted})

    execution = Execution(
        project_id=project_id, target_id=target_id or project.target_id,
        suite_id=suite_id, suite_name=suite_name,
        trigger_type=trigger_type, case_ids=case_ids,
        engine_key=project.engine_key, platform=str(project.platform),
        status=ExecutionStatus.PENDING, total=len(cases),
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)

    from app.services.execution_queue import execution_queue
    try:
        await execution_queue.submit(execution.id)
    except QueueFull:
        # 宁可留一条"已取消"的记录，也不留一条永远 PENDING 的幽灵
        execution.status = ExecutionStatus.CANCELLED
        execution.message = "执行队列已满，任务未执行"
        execution.finished_at = datetime.now()
        await db.commit()
        raise
    return execution


# ─────────────────────────── 执行 ───────────────────────────
async def _claim(db: AsyncSession, execution_id: int) -> bool:
    """条件更新抢执行权（INV-2），防重复消费。"""
    result = await db.execute(
        update(Execution)
        .where(Execution.id == execution_id, Execution.status == ExecutionStatus.PENDING)
        .values(status=ExecutionStatus.RUNNING, started_at=datetime.now()))
    await db.commit()
    return (result.rowcount or 0) == 1


async def execute(execution_id: int) -> None:
    async with SessionLocal() as db:
        if not await _claim(db, execution_id):
            logger.info("execution %s not claimed (already running/finished)", execution_id)
            return

        execution = (await db.execute(
            select(Execution).where(Execution.id == execution_id))).scalar_one()
        project = await get_project(db, execution.project_id)
        target = None
        if execution.target_id:
            target = next((t for t in await list_targets(db, execution.project_id)
                           if t.id == execution.target_id), None)

        events = ExecutionEvents(execution_id)
        events.emit("execution.started", execution_id=execution_id,
                    total=execution.total, platform=str(execution.platform),
                    engine_key=execution.engine_key)

        # ── M3.6 GAP-08（D34/D37）：解析诊断计划并准备产物目录 ──
        target_options = dict(target.options or {}) if target else {}
        plan = resolve_diagnostics(settings.trace, settings.video, settings.har,
                                   target_options)
        for warning in plan.warnings:
            logger.warning("execution %s diagnostics: %s", execution_id, warning)
        diagnostics_dir = os.path.join(settings.artifacts_dir, f"exec-{execution_id}")
        for sub in ("trace", "video", "har"):
            os.makedirs(os.path.join(diagnostics_dir, sub), exist_ok=True)

        config = SessionConfig(
            platform=str(execution.platform), engine_key=execution.engine_key,
            base_url=target.base_url if target else None,
            # 规范化后的诊断键写回 options（D36 修正设计）：适配器只信规范值
            options={**target_options, "trace": plan.trace,
                     "video": plan.video, "har": plan.har},
            headless=settings.headless, timeout_ms=project.default_timeout_ms,
            diagnostics_dir=diagnostics_dir,
        )

        manager = SessionManager(registry)
        started = time.perf_counter()
        counts = {"passed": 0, "failed": 0, "errored": 0, "skipped": 0}
        cancelled = False

        try:
            adapter = await manager.open(config)
            cases = list((await db.execute(
                select(TestCase).where(TestCase.id.in_(execution.case_ids or [0]))
                .order_by(TestCase.id))).scalars().all())

            for case in cases:
                if _is_cancelled(execution_id):
                    cancelled = True
                    break
                events.emit("case.started", case_id=case.id, title=case.title)
                case_status = await _run_case(
                    db, execution, project, adapter, case, events, execution_id)
                if case_status == "CANCELLED":
                    cancelled = True
                    counts["skipped"] += 1
                    break
                counts[{"PASSED": "passed", "FAILED": "failed",
                        "ERROR": "errored"}.get(case_status, "errored")] += 1
                events.emit("case.finished", case_id=case.id, status=case_status)
        except Exception as exc:                       # 引擎起不来等致命错误
            logger.exception("execution %s failed to start", execution_id)
            execution.status = ExecutionStatus.ERROR
            execution.message = f"{type(exc).__name__}: {exc}"[:500]
        finally:
            # ── D37 两段式第一段：trace.stop 必须在 context close 之前 ──
            # ERROR 但浏览器没起来时 manager.current 可能为 None → 跳过 finalize
            # （沿用 close_all 的防御式写法）。
            failed_like = bool(counts["failed"] or counts["errored"]) or (
                str(execution.status) == str(ExecutionStatus.ERROR))
            save_trace = plan.trace == "always" or (
                plan.trace == "on-failure" and not cancelled and failed_like)
            adapter = manager.current
            if adapter is not None:
                try:
                    await adapter.finalize_diagnostics(save_trace=save_trace)
                except Exception:                      # 诊断收尾绝不影响执行结果（R5）
                    logger.warning("execution %s finalize_diagnostics failed",
                                   execution_id, exc_info=True)
            await manager.close_all()

        execution.passed = counts["passed"]
        execution.failed = counts["failed"]
        execution.errored = counts["errored"]
        execution.skipped = counts["skipped"]
        execution.duration_ms = int((time.perf_counter() - started) * 1000)
        execution.finished_at = datetime.now()

        if cancelled or _is_cancelled(execution_id):
            execution.status = ExecutionStatus.CANCELLED
            execution.message = execution.message or "用户取消"
            events.emit("execution.cancelled", execution_id=execution_id)
        elif str(execution.status) != ExecutionStatus.ERROR:
            if counts["errored"]:
                execution.status = ExecutionStatus.ERROR
            elif counts["failed"]:
                execution.status = ExecutionStatus.FAILED
            elif counts["passed"] == execution.total:
                execution.status = ExecutionStatus.PASSED
            else:
                execution.status = ExecutionStatus.FAILED

        # ── D37 两段式第二段：close 之后扫描诊断目录，登记产物 ──
        # 必须在终态 commit **之前**：保证「终态可见 ⇔ 产物已齐」，消除
        # "轮询到 PASSED 但 TRACE/VIDEO/HAR 尚未入表"的竞态（验收审计实测命中）。
        # video / har 文件在 context close 后才落盘且文件名随机 → 扫描目录而非记路径。
        # FR34：只由执行器落库；FR57：kind ∈ {TRACE, VIDEO, HAR}，step_result_id=None。
        try:
            await _register_diagnostics(db, execution_id, diagnostics_dir)
        except Exception:                          # 产物登记失败不影响执行结果
            logger.warning("execution %s register diagnostics failed",
                           execution_id, exc_info=True)

        await db.commit()
        _cancel_flags.discard(execution_id)
        events.emit("execution.finished", execution_id=execution_id,
                    status=str(execution.status), **counts,
                    duration_ms=execution.duration_ms)

        try:
            await generate_report(db, execution_id)
        except Exception:
            logger.warning("report generation failed for %s", execution_id, exc_info=True)

        # ── M3.6 GAP-20：终态 commit 之后推送企微（fire-and-forget，
        #    notify_service 内部 create_task + 全异常吞掉，绝不影响执行结果）──
        await notify_service.notify_execution_result({
            "execution_id": execution_id,
            "status": str(execution.status),
            "suite_name": execution.suite_name,
            "counts": dict(counts),
            "duration_ms": execution.duration_ms,
        })


async def _register_diagnostics(db: AsyncSession, execution_id: int,
                                diagnostics_dir: str) -> int:
    """扫描 ``{artifacts_dir}/exec-{id}`` 目录，登记 trace/video/har 产物。"""
    specs = (("trace", "*.zip", "TRACE"), ("video", "*.webm", "VIDEO"),
             ("har", "*.har", "HAR"))
    added = 0
    for sub, pattern, kind in specs:
        folder = os.path.join(diagnostics_dir, sub)
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            if not fnmatch.fnmatch(name.lower(), pattern):
                continue
            path = os.path.join(folder, name)
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            db.add(Artifact(execution_id=execution_id, step_result_id=None,
                            kind=kind, storage="LOCAL", path=path, size_bytes=size))
            added += 1
    if added:
        await db.commit()
    return added


async def _run_case(db: AsyncSession, execution: Execution, project, adapter,
                    case: TestCase, events: ExecutionEvents, execution_id: int) -> str:
    steps = list((await db.execute(
        select(TestStep).where(TestStep.case_id == case.id, TestStep.enabled.is_(True))
        .order_by(TestStep.seq))).scalars().all())

    case_vars: dict = {}
    aborted = False
    failed = errored = False

    for step in steps:
        if _is_cancelled(execution_id):
            await _record(db, execution.id, case.id, step, StepStatus.SKIPPED, 1, 0,
                          "执行已取消", None, None, project)
            return "CANCELLED"
        if aborted:
            await _record(db, execution.id, case.id, step, StepStatus.SKIPPED, 1, 0,
                          "前序步骤失败，已中止", None, None, project)
            continue

        attempts = max_attempts(step)
        final_status, final_message = StepStatus.ERROR, "未执行"

        for attempt in range(1, attempts + 1):
            collector = _Collector()
            ctx = ActionContext(
                execution_id=execution.id, case_id=case.id, step_seq=step.seq,
                timeout_ms=step.timeout_ms or project.default_timeout_ms,
                variables=case_vars, log=collector,
            )
            step_started = time.perf_counter()
            try:
                spec = ACTION_BY_KEY.get(step.action_key)
                if spec is None:
                    raise ValidationFailed(f"未知动作 {step.action_key}")
                params = dict(step.params or {})
                # F-M3.2-4：test_step.output_var 曾是死字段（只序列化、执行不生效）。
                # 动作 schema 里的 output_var 优先；没有时用列上的值兜底。
                if step.output_var and "output_var" not in params:
                    params["output_var"] = step.output_var
                # screenshot(target=element) 也绑定元素，但它不是"必须绑定"的动作
                # （页面级截图不需要元素），所以不能只靠 spec.requires_element 判断。
                needs_element = spec.requires_element or params.get("target") == "element"
                chain = None
                if needs_element:
                    if not step.element_id:
                        raise ValidationFailed(
                            f"步骤 {step.seq} 的动作 {step.action_key} 需要绑定元素"
                            + ("（target=element）" if params.get("target") == "element" else ""))
                    chain = await resolve_chain_for(
                        db, step.element_id, str(project.platform), project.engine_key)
                if "target_element_id" in params:
                    ref = int(params["target_element_id"])
                    ctx.resolved_chains[ref] = await resolve_chain_for(
                        db, ref, str(project.platform), project.engine_key)
                await dispatch(step.action_key, adapter, chain, params, ctx)
                final_status, final_message = StepStatus.PASSED, None
            except AssertionError as exc:
                final_status, final_message = StepStatus.FAILED, str(exc)
            except Exception as exc:                   # 含 LocatorNotFoundError
                final_status = StepStatus.ERROR
                final_message = f"{type(exc).__name__}: {exc}"

            elapsed = int((time.perf_counter() - step_started) * 1000)
            used_locator_id, fallback_index = collector.last_locator_hit()
            await _record(db, execution.id, case.id, step, final_status, attempt, elapsed,
                          final_message, used_locator_id, fallback_index, project,
                          artifacts=ctx.artifacts)
            events.emit("step.finished", case_id=case.id, seq=step.seq,
                        action_key=step.action_key, status=str(final_status),
                        duration_ms=elapsed, attempt=attempt,
                        fallback_index=fallback_index)

            if final_status == StepStatus.PASSED:
                break
            if attempt < attempts:
                events.emit("step.retried", case_id=case.id, seq=step.seq,
                            attempt=attempt, error=(final_message or "")[:200])
                continue
            break

        if final_status == StepStatus.FAILED:
            failed = True
            if str(step.on_failure) in ("ABORT", "RETRY"):
                aborted = True
        elif final_status == StepStatus.ERROR:
            errored = True
            if str(step.on_failure) in ("ABORT", "RETRY"):
                aborted = True

    if errored:
        return "ERROR"
    if failed:
        return "FAILED"
    return "PASSED"


class _Collector:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def __call__(self, event: str, payload: dict) -> None:
        self.events.append((event, payload))

    def last_locator_hit(self) -> tuple[int | None, int | None]:
        for event, payload in reversed(self.events):
            if event == "locator.hit":
                return payload.get("locator_id"), payload.get("fallback_index")
        return None, None


async def _record(db: AsyncSession, execution_id: int, case_id: int, step: TestStep,
                  status: str, attempt: int, elapsed_ms: int, message: str | None,
                  used_locator_id: int | None, fallback_index: int | None, project,
                  artifacts: list[dict] | None = None) -> None:
    row = ExecutionStepResult(
        execution_id=execution_id, case_id=case_id, step_id=step.id, seq=step.seq,
        action_key=step.action_key, element_id=step.element_id, status=status,
        attempt=attempt, duration_ms=elapsed_ms, message=message,
        used_locator_id=used_locator_id, fallback_index=fallback_index,
        active_platform=str(project.platform), active_engine=project.engine_key,
    )
    db.add(row)
    await db.flush()                                   # 拿 row.id 给产物挂靠
    for item in artifacts or []:
        db.add(Artifact(
            execution_id=execution_id, step_result_id=row.id,
            kind=item.get("kind", "SCREENSHOT"), storage="LOCAL",
            path=item["path"], size_bytes=item.get("size_bytes"),
        ))
    await db.commit()


# ─────────────────────────── 取消与自愈 ───────────────────────────
async def request_cancel(db: AsyncSession, execution_id: int) -> Execution:
    execution = (await db.execute(
        select(Execution).where(Execution.id == execution_id))).scalar_one_or_none()
    if execution is None:
        raise ExecutionNotFound(f"执行 {execution_id} 不存在", {"execution_id": execution_id})
    if str(execution.status) in TERMINAL:
        raise ExecutionCannotCancel(
            f"执行已处于终态 {execution.status}，无法取消",
            {"execution_id": execution_id, "status": str(execution.status)})

    if str(execution.status) == ExecutionStatus.PENDING:
        execution.status = ExecutionStatus.CANCELLED
        execution.message = "提交后立即取消"
        execution.finished_at = datetime.now()
        await db.commit()
        return execution

    _cancel_flags.add(execution_id)                    # RUNNING：步骤间检查点生效
    return execution


async def reconcile_orphans(db: AsyncSession) -> int:
    """启动自愈（FR31）：残留 RUNNING/PENDING 全部置 ERROR。"""
    result = await db.execute(
        update(Execution)
        .where(Execution.status.in_([ExecutionStatus.RUNNING, ExecutionStatus.PENDING]))
        .values(status=ExecutionStatus.ERROR, finished_at=datetime.now(),
                message="进程重启，执行中断"))
    await db.commit()
    return result.rowcount or 0


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)
