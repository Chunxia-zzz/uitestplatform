"""报告生成（M3.1 / D20 / FR35）：HTML（人看）+ JSON（机器读）。

不引入模板引擎：结构固定、体量小；等 M3.2 的报告页要做复杂布局时再评估。
重复生成是幂等的：文件覆盖、DB 按 (execution_id, format) 先删后插。
"""
from __future__ import annotations

import asyncio
import html
import json
import os
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import ExecutionNotFound
from app.models import Artifact, Execution, ExecutionStepResult, Report, TestCase

_STATUS_CLASS = {
    "PASSED": "ok", "FAILED": "warn", "ERROR": "bad", "SKIPPED": "muted",
    "RUNNING": "run", "PENDING": "muted", "CANCELLED": "muted",
}


def _style() -> str:
    return """
    body{font-family:system-ui,-apple-system,"Segoe UI","PingFang SC",sans-serif;
         margin:0;padding:28px;background:#f6f7f9;color:#1b1f24}
    h1{font-size:20px;margin:0 0 4px}
    .sub{color:#6b7280;font-size:13px;margin-bottom:18px}
    .cards{display:flex;gap:12px;margin-bottom:18px;flex-wrap:wrap}
    .card{background:#fff;border:1px solid #e3e6ea;border-radius:10px;
          padding:12px 16px;min-width:110px}
    .card b{display:block;font-size:22px;margin-top:2px}
    .ok{color:#16a34a}.bad{color:#dc2626}.warn{color:#d97706}.muted{color:#6b7280}
    table{width:100%;border-collapse:collapse;background:#fff;
          border:1px solid #e3e6ea;border-radius:10px}
    th,td{padding:8px 10px;border-bottom:1px solid #eef0f3;text-align:left;font-size:13px}
    th{color:#6b7280;font-weight:600;font-size:12px}
    tr:last-child td{border-bottom:0}
    .mono{font-family:ui-monospace,Consolas,monospace}
    .fb{background:#fdf3e3}
    """


async def _load(db: AsyncSession, execution_id: int):
    execution = (await db.execute(
        select(Execution).where(Execution.id == execution_id))).scalar_one_or_none()
    if execution is None:
        raise ExecutionNotFound(f"执行 {execution_id} 不存在", {"execution_id": execution_id})

    results = list((await db.execute(
        select(ExecutionStepResult)
        .where(ExecutionStepResult.execution_id == execution_id)
        .order_by(ExecutionStepResult.case_id, ExecutionStepResult.seq,
                  ExecutionStepResult.attempt))).scalars().all())

    artifacts = list((await db.execute(
        select(Artifact).where(Artifact.execution_id == execution_id))).scalars().all())
    artifacts_by_step: dict[int, list[Artifact]] = {}
    for item in artifacts:
        if item.step_result_id:
            artifacts_by_step.setdefault(item.step_result_id, []).append(item)

    case_ids = list(execution.case_ids or [])
    titles = {}
    if case_ids:
        titles = {c.id: c.title for c in (await db.execute(
            select(TestCase).where(TestCase.id.in_(case_ids)))).scalars().all()}
    return execution, results, artifacts_by_step, titles


def build_payload(execution: Execution, results: list[ExecutionStepResult],
                  artifacts_by_step: dict[int, list[Artifact]],
                  titles: dict[int, str]) -> dict:
    total_steps = len(results)
    done = sum(1 for r in results if r.status in ("PASSED", "FAILED", "ERROR"))
    cases: dict[int, dict] = {}
    for row in results:
        bucket = cases.setdefault(row.case_id, {
            "case_id": row.case_id,
            "title": titles.get(row.case_id, ""),
            "steps": [],
        })
        bucket["steps"].append({
            "seq": row.seq, "action_key": row.action_key, "element_id": row.element_id,
            "status": str(row.status), "attempt": row.attempt,
            "duration_ms": row.duration_ms, "message": row.message,
            "used_locator_id": row.used_locator_id, "fallback_index": row.fallback_index,
            "artifacts": [
                {"id": a.id, "kind": a.kind, "path": a.path, "size_bytes": a.size_bytes,
                 # GAP-34：给浏览器可直接访问的 URL，而不是服务器本地路径
                 "url": f"/api/v1/executions/{execution.id}/artifacts/{a.id}"}
                for a in artifacts_by_step.get(row.id, [])
            ],
        })
    return {
        "execution": {
            "id": execution.id, "project_id": execution.project_id,
            "suite_id": execution.suite_id, "suite_name": execution.suite_name,
            "platform": str(execution.platform), "engine_key": execution.engine_key,
            "status": str(execution.status), "trigger_type": str(execution.trigger_type),
            "total": execution.total, "passed": execution.passed,
            "failed": execution.failed, "errored": execution.errored,
            "skipped": execution.skipped, "duration_ms": execution.duration_ms,
            "started_at": execution.started_at.isoformat(timespec="seconds")
            if execution.started_at else None,
            "finished_at": execution.finished_at.isoformat(timespec="seconds")
            if execution.finished_at else None,
            "message": execution.message,
        },
        "summary": {
            "cases": execution.total,
            "pass_rate": round(execution.passed / execution.total, 4) if execution.total else 0.0,
            "steps": total_steps,
            "steps_done": done,
        },
        "cases": list(cases.values()),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def render_html(payload: dict) -> str:
    ex = payload["execution"]
    summary = payload["summary"]
    css_cls = _STATUS_CLASS.get(ex["status"], "muted")
    rows: list[str] = []
    for case in payload["cases"]:
        rows.append(
            f'<tr><td colspan="9" style="background:#fafbfc">'
            f'<b>用例 #{case["case_id"]}</b> {html.escape(case["title"] or "")}</td></tr>')
        for step in case["steps"]:
            cls = _STATUS_CLASS.get(step["status"], "muted")
            fb = ' class="fb"' if (step["fallback_index"] or 0) > 0 else ""
            shots = " ".join(
                f'<a href="{html.escape(a.get("url") or a["path"])}" '
                f'target="_blank" rel="noreferrer">截图#{a["id"]}</a>'
                for a in step["artifacts"])
            rows.append(
                f'<tr{fb}><td>{step["seq"]}</td>'
                f'<td class="mono">{html.escape(step["action_key"])}</td>'
                f'<td>{step["element_id"] or "—"}</td>'
                f'<td class="{cls}">{step["status"]}</td>'
                f'<td>{step["attempt"]}</td>'
                f'<td>{step["duration_ms"] or 0} ms</td>'
                f'<td class="mono">{step["used_locator_id"] or "—"}</td>'
                f'<td class="mono">{(step["fallback_index"]
                                     if step["fallback_index"] is not None else "—")}</td>'
                f'<td>{html.escape(step["message"] or "")} {shots}</td></tr>')

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>执行报告 #{ex["id"]}</title><style>{_style()}</style></head>
<body>
  <h1>执行报告 #{ex["id"]}</h1>
  <div class="sub">
    {html.escape(ex["suite_name"] or "临时用例（未归入用例集）")} ·
    {html.escape(ex["platform"])} / {html.escape(ex["engine_key"])} ·
    状态 <span class="{css_cls}">{ex["status"]}</span> ·
    {ex["started_at"] or "—"} → {ex["finished_at"] or "—"} ·
    {ex["duration_ms"] or 0} ms
    {(" · " + html.escape(ex["message"])) if ex["message"] else ""}
  </div>
  <div class="cards">
    <div class="card">用例总数<b>{summary["cases"]}</b></div>
    <div class="card">通过<b class="ok">{ex["passed"]}</b></div>
    <div class="card">失败<b class="warn">{ex["failed"]}</b></div>
    <div class="card">异常<b class="bad">{ex["errored"]}</b></div>
    <div class="card">跳过<b class="muted">{ex["skipped"]}</b></div>
    <div class="card">步骤完成<b>{summary["steps_done"]}/{summary["steps"]}</b></div>
  </div>
  <table>
    <thead><tr><th>seq</th><th>动作</th><th>元素</th><th>状态</th><th>尝试</th>
    <th>耗时</th><th>used_locator_id</th><th>fallback_index</th><th>消息 / 产物</th></tr></thead>
    <tbody>{''.join(rows) or '<tr><td colspan="9">无步骤结果</td></tr>'}</tbody>
  </table>
</body></html>"""


async def _upsert(db: AsyncSession, execution_id: int, fmt: str,
                  path: str, summary: dict) -> None:
    """按 (execution_id, format) 更新或插入。

    GAP-35：表上已有 ``uk_report_execution_format``，所以"先查后插"在并发下仍可能
    两个事务同时查不到、同时插入 —— 一个会撞唯一键。用 savepoint 包住插入，
    撞键时回滚到 savepoint 再走更新分支，不会污染整个事务。
    """
    record = (await db.execute(
        select(Report).where(Report.execution_id == execution_id,
                             Report.format == fmt))).scalar_one_or_none()
    if record is None:
        try:
            async with db.begin_nested():
                db.add(Report(execution_id=execution_id, format=fmt,
                              path=path, summary=summary))
                await db.flush()
            return
        except IntegrityError:
            # 并发插入赢了 → 回滚到 savepoint，改为更新那一行
            record = (await db.execute(
                select(Report).where(Report.execution_id == execution_id,
                                     Report.format == fmt))).scalar_one()
    record.path = path
    record.summary = summary


def _write_reports(html_text: str, payload: dict, execution_id: int) -> tuple[str, str]:
    """同步写报告文件（报告可达上百 KB，不应阻塞事件循环；调用方用 to_thread 包一层）。"""
    os.makedirs(settings.report_dir, exist_ok=True)
    html_path = os.path.abspath(os.path.join(settings.report_dir,
                                             f"execution-{execution_id}.html"))
    json_path = os.path.abspath(os.path.join(settings.report_dir,
                                             f"execution-{execution_id}.json"))
    with open(html_path, "w", encoding="utf-8") as fp:
        fp.write(html_text)
    with open(json_path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)
    return html_path, json_path


async def generate(db: AsyncSession, execution_id: int) -> dict:
    """生成（或覆盖）报告，返回 {'html': path, 'json': path}。"""
    execution, results, artifacts_by_step, titles = await _load(db, execution_id)
    payload = build_payload(execution, results, artifacts_by_step, titles)

    html_path, json_path = await asyncio.to_thread(
        _write_reports, render_html(payload), payload, execution_id)

    await _upsert(db, execution_id, "HTML", html_path, payload["summary"])
    await _upsert(db, execution_id, "JSON", json_path, payload["summary"])
    await db.commit()
    return {"html": html_path, "json": json_path, "summary": payload["summary"]}


async def find(db: AsyncSession, execution_id: int, fmt: str) -> Report | None:
    return (await db.execute(
        select(Report).where(Report.execution_id == execution_id,
                             Report.format == fmt.upper())
        .order_by(Report.id.desc()).limit(1))).scalar_one_or_none()
