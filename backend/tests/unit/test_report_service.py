"""重试策略与报告内容（M3.1 V4 / V7）。"""
from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.models import Artifact, Execution, ExecutionStepResult, TestCase
from app.services import report_service
from app.services.execution_service import max_attempts


def step(on_failure: str, retry_times: int):
    return SimpleNamespace(on_failure=on_failure, retry_times=retry_times)


@pytest.mark.parametrize("policy,retries,expected", [
    ("ABORT", 0, 1), ("ABORT", 3, 1),
    ("CONTINUE", 2, 1),
    ("RETRY", 0, 1), ("RETRY", 2, 3), ("RETRY", 1, 2),
])
def test_max_attempts(policy, retries, expected):
    assert max_attempts(step(policy, retries)) == expected


@pytest.mark.asyncio
async def test_report_contains_retry_and_fallback(db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "report_dir", str(tmp_path))

    case = TestCase(project_id=1, title="登录成功")
    db.add(case)
    await db.commit()
    await db.refresh(case)

    execution = Execution(
        project_id=1, case_ids=[case.id], engine_key="playwright", platform="WEB",
        status="FAILED", total=1, failed=1, passed=0, errored=0, skipped=0,
        duration_ms=1234, started_at=datetime.now(), finished_at=datetime.now(),
        message="有失败步骤",
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)

    rows = [
        ExecutionStepResult(execution_id=execution.id, case_id=case.id, seq=4,
                            action_key="click", status="ERROR", attempt=1,
                            duration_ms=2500, message="TimeoutError: 第一条定位符超时",
                            used_locator_id=3, fallback_index=None),
        ExecutionStepResult(execution_id=execution.id, case_id=case.id, seq=4,
                            action_key="click", status="PASSED", attempt=2,
                            duration_ms=300, message=None,
                            used_locator_id=4, fallback_index=1),
    ]
    db.add_all(rows)
    await db.commit()
    for row in rows:
        await db.refresh(row)
    db.add(Artifact(execution_id=execution.id, step_result_id=rows[1].id,
                    kind="SCREENSHOT", storage="LOCAL", path="/tmp/a.png", size_bytes=10))
    await db.commit()

    paths = await report_service.generate(db, execution.id)
    html = open(paths["html"], encoding="utf-8").read()
    payload = json.load(open(paths["json"], encoding="utf-8"))

    assert "执行报告" in html and "登录成功" in html
    assert "TimeoutError" in html
    assert 'class="fb"' in html, "fallback_index>0 的行应高亮"
    assert payload["summary"]["steps"] == 2
    assert payload["cases"][0]["steps"][1]["attempt"] == 2
    assert payload["cases"][0]["steps"][1]["fallback_index"] == 1
    assert payload["cases"][0]["steps"][1]["artifacts"][0]["path"] == "/tmp/a.png"
    # GAP-34：同时给出浏览器可直接访问的 URL（而不是服务器本地路径）
    assert payload["cases"][0]["steps"][1]["artifacts"][0]["url"].startswith(
        f"/api/v1/executions/{execution.id}/artifacts/")
    assert "/api/v1/executions/" in html, "报告里的截图链接应指向 API 路径"

    # 幂等：重复生成不产生重复 report 行
    await report_service.generate(db, execution.id)
    from sqlalchemy import func, select
    from app.models import Report
    count = (await db.execute(select(func.count(Report.id))
                              .where(Report.execution_id == execution.id))).scalar_one()
    assert count == 2


@pytest.mark.asyncio
async def test_regenerate_updates_existing_row(db, tmp_path, monkeypatch):
    """GAP-35：第二次生成必须更新原行（不是插入第二行），且能反映新统计。"""
    monkeypatch.setattr(settings, "report_dir", str(tmp_path))
    execution = Execution(
        project_id=1, case_ids=[], engine_key="playwright", platform="WEB",
        status="PASSED", total=1, passed=1, failed=0, errored=0, skipped=0,
        duration_ms=10, started_at=datetime.now(), finished_at=datetime.now(),
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)

    await report_service.generate(db, execution.id)
    execution.passed = 0
    execution.failed = 1
    execution.status = "FAILED"
    await db.commit()

    await report_service.generate(db, execution.id)
    from sqlalchemy import select
    from app.models import Report
    rows = list((await db.execute(
        select(Report).where(Report.execution_id == execution.id))).scalars().all())
    assert len(rows) == 2                                   # HTML + JSON，各一行
    html_row = next(r for r in rows if r.format == "HTML")
    assert html_row.summary["pass_rate"] == 0.0             # 已更新

