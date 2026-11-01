"""响应序列化（ORM → dict）。集中一处，避免各端点各写一套。"""
from __future__ import annotations

from typing import Any

from app.models import (
    Element, ElementLocator, Execution, ExecutionStepResult, ExecutionTarget, Project,
    TestCase, TestStep,
)


def iso(value) -> str | None:
    return value.isoformat(timespec="seconds") if value else None


def project_to_dict(p: Project) -> dict[str, Any]:
    return {
        "id": p.id, "name": p.name, "code": p.code,
        "platform": str(p.platform), "engine_key": p.engine_key,
        "target_id": p.target_id, "description": p.description,
        "default_timeout_ms": p.default_timeout_ms,
        "created_at": iso(p.created_at), "updated_at": iso(p.updated_at),
    }


def target_to_dict(t: ExecutionTarget) -> dict[str, Any]:
    """M3.6 GAP-42：字段与既有 GET /execution-targets 列表项完全一致（前端零适配）。"""
    return {
        "id": t.id, "project_id": t.project_id, "name": t.name,
        "platform": str(t.platform), "engine_key": t.engine_key,
        "base_url": t.base_url, "options": t.options, "enabled": bool(t.enabled),
    }


def element_to_dict(e: Element, *, locator_count: dict[str, int] | None = None) -> dict[str, Any]:
    return {
        "id": e.id, "project_id": e.project_id, "parent_id": e.parent_id, "path": e.path,
        "depth": max(e.path.count("/") - 1, 0),
        "element_name": e.element_name, "node_type": str(e.node_type),
        "description": e.description, "memo": e.memo,
        "is_shared": int(bool(e.is_shared)),          # D16：M2 恒为 1
        "sort": e.sort,
        "locator_count": locator_count or {"WEB": 0, "ANDROID": 0, "IOS": 0},
        "created_at": iso(e.created_at), "updated_at": iso(e.updated_at),
    }


def tree_node_to_dict(node: dict) -> dict[str, Any]:
    payload = element_to_dict(node["node"], locator_count=node.get("locator_count"))
    payload["children"] = [tree_node_to_dict(child) for child in node.get("children", [])]
    return payload


def locator_to_dict(loc: ElementLocator) -> dict[str, Any]:
    return {
        "id": loc.id, "element_id": loc.element_id,
        "platform": str(loc.platform), "engine_key": loc.engine_key,
        "locator_type": loc.locator_type, "locator_value": loc.locator_value,
        "priority": loc.priority, "is_primary": bool(loc.is_primary),
        "enabled": bool(loc.enabled), "status": str(loc.status),
        "verified_at": iso(loc.verified_at), "probe_detail": loc.probe_detail,
        "remark": loc.remark,
    }


def locator_group_to_dict(group: dict) -> dict[str, Any]:
    items = [locator_to_dict(i) for i in group["items"]]
    return {
        "platform": group["platform"], "engine_key": group["engine_key"],
        "primary_id": group.get("primary_id"), "items": items,
    }


def case_to_dict(c: TestCase) -> dict[str, Any]:
    return {"id": c.id, "project_id": c.project_id, "title": c.title,
            "description": c.description, "state": bool(c.state),
            "created_at": iso(c.created_at)}


def suite_to_dict(suite, case_count: int | None = None) -> dict[str, Any]:
    payload = {
        "id": suite.id, "project_id": suite.project_id, "name": suite.name,
        "description": suite.description,
        "schedule_cron": suite.schedule_cron,
        "schedule_enabled": bool(suite.schedule_enabled),
        "last_run_at": iso(suite.last_run_at),
        "created_at": iso(suite.created_at), "updated_at": iso(suite.updated_at),
    }
    if case_count is not None:
        payload["case_count"] = case_count
    return payload


def suite_member_to_dict(member, case) -> dict[str, Any]:
    return {
        "case_id": case.id, "title": case.title,
        "description": case.description,
        "sort": member.sort, "enabled": bool(member.enabled),
    }


def step_to_dict(s: TestStep) -> dict[str, Any]:
    return {
        "id": s.id, "case_id": s.case_id, "seq": s.seq, "action_key": s.action_key,
        "element_id": s.element_id, "params": s.params, "output_var": s.output_var,
        "timeout_ms": s.timeout_ms, "on_failure": str(s.on_failure),
        "retry_times": s.retry_times, "enabled": bool(s.enabled), "remark": s.remark,
    }


def step_result_to_dict(r: ExecutionStepResult) -> dict[str, Any]:
    return {
        # M3.2：产物按 step_result_id 挂靠，前端必须能对上号
        "id": r.id,
        "seq": r.seq, "step_id": r.step_id, "action_key": r.action_key,
        "element_id": r.element_id, "status": str(r.status),
        "attempt": r.attempt,
        "duration_ms": r.duration_ms,
        "message": r.message, "used_locator_id": r.used_locator_id,
        "fallback_index": r.fallback_index,
        "active_platform": r.active_platform, "active_engine": r.active_engine,
    }


def execution_to_dict(e: Execution, results: list[ExecutionStepResult] | None = None,
                      case_titles: dict[int, str] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": e.id, "project_id": e.project_id, "target_id": e.target_id,
        "suite_id": e.suite_id, "suite_name": e.suite_name,
        "trigger_type": str(e.trigger_type), "platform": str(e.platform),
        "engine_key": e.engine_key, "status": str(e.status),
        "total": e.total, "passed": e.passed, "failed": e.failed,
        "errored": e.errored, "skipped": e.skipped,
        "duration_ms": e.duration_ms,
        "message": e.message,
        "started_at": iso(e.started_at), "finished_at": iso(e.finished_at),
        "created_at": iso(e.created_at),
    }
    if results is not None:
        by_case: dict[int, list] = {}
        for row in results:
            by_case.setdefault(row.case_id, []).append(step_result_to_dict(row))
        titles = case_titles or {}
        payload["cases"] = [
            {"case_id": case_id, "title": titles.get(case_id, ""), "steps": steps}
            for case_id, steps in by_case.items()
        ]
    return payload
