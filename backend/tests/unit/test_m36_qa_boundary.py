"""M3.6 QA 边界补测（验收第 2 步）：工程师单测之外的薄弱点。

覆盖点：
- target：PATCH 仅传 name 时其余字段不动；显式 name=null 不改名字；
  跨项目同名不冲突（per-project 唯一）。
- notify：send_markdown 的三个抛错分支（HTTP 5xx / errcode!=0 / 非 JSON）；
  D39 日志含 event=notify.failed 且不泄漏 webhook URL。
- diagnostics：video="true"（字符串）被忽略而非误开；options.trace=None
  （键存在值为 None）回退全局 + warning。
"""
from __future__ import annotations

import logging

import httpx
import pytest

from app.core.config import settings
from app.domain.diagnostics import resolve_diagnostics
from app.models import Project
from app.services import notify_service, target_service


async def _project(db, code: str = "p1") -> Project:
    row = Project(name="P", code=code, platform="WEB", engine_key="playwright",
                  default_timeout_ms=5000)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


# ─────────────────────────── target 边界 ───────────────────────────
@pytest.mark.asyncio
async def test_update_name_only_keeps_base_url_options_enabled(db):
    """PATCH exclude_unset 语义：只传 name 时 base_url / options / enabled 原样保留。"""
    project = await _project(db)
    target = await target_service.create(
        db, project.id, name="旧名", platform="WEB", engine_key="playwright",
        base_url="http://keep", options={"browser": "chromium"}, enabled=False)
    updated = await target_service.update(db, target.id, name="新名")
    assert updated.name == "新名"
    assert updated.base_url == "http://keep"
    assert updated.options == {"browser": "chromium"}
    assert updated.enabled is False


@pytest.mark.asyncio
async def test_update_name_none_does_not_rename(db):
    """显式传 name=None（JSON null）不应把名字清空。"""
    project = await _project(db)
    target = await target_service.create(db, project.id, name="原名",
                                         platform="WEB", engine_key="playwright")
    updated = await target_service.update(db, target.id, name=None)
    assert updated.name == "原名"


@pytest.mark.asyncio
async def test_same_name_in_different_project_ok(db):
    """唯一性是项目内的：不同项目同名互不冲突（D30）。"""
    p1 = await _project(db, code="pa")
    p2 = await _project(db, code="pb")
    await target_service.create(db, p1.id, name="同名", platform="WEB",
                                engine_key="playwright")
    other = await target_service.create(db, p2.id, name="同名", platform="WEB",
                                        engine_key="playwright")
    assert other.id and other.name == "同名"


# ─────────────────────────── notify 边界 ───────────────────────────
@pytest.fixture
def _mock_transport():
    """把 notify_service 内的 httpx.AsyncClient 换成指向 MockTransport 的子类。"""
    def install(handler):
        transport = httpx.MockTransport(handler)
        real_client = httpx.AsyncClient

        class _Client(real_client):
            def __init__(self, *a, **kw):
                kw["transport"] = transport
                super().__init__(*a, **kw)
        return _Client
    return install


@pytest.mark.asyncio
async def test_send_markdown_raises_on_http_500(monkeypatch, _mock_transport):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")
    monkeypatch.setattr(notify_service.httpx, "AsyncClient", _mock_transport(handler))
    with pytest.raises(notify_service.NotifySendError, match="HTTP 500"):
        await notify_service.send_markdown("https://qyapi.weixin.qq.com/x", "hi")


@pytest.mark.asyncio
async def test_send_markdown_raises_on_errcode_nonzero(monkeypatch, _mock_transport):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"errcode": 94000, "errmsg": "invalid webhook"})
    monkeypatch.setattr(notify_service.httpx, "AsyncClient", _mock_transport(handler))
    with pytest.raises(notify_service.NotifySendError, match="errcode=94000"):
        await notify_service.send_markdown("https://qyapi.weixin.qq.com/x", "hi")


@pytest.mark.asyncio
async def test_send_markdown_raises_on_non_json(monkeypatch, _mock_transport):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")
    monkeypatch.setattr(notify_service.httpx, "AsyncClient", _mock_transport(handler))
    with pytest.raises(notify_service.NotifySendError, match="JSON"):
        await notify_service.send_markdown("https://qyapi.weixin.qq.com/x", "hi")


@pytest.mark.asyncio
async def test_send_failure_logs_event_without_webhook_url(caplog, monkeypatch):
    """D39：日志含 event=notify.failed，且不打印 webhook 完整 URL（含 key）。"""
    webhook = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=SECRETKEY123"
    async def boom(*a, **kw):
        raise httpx.ConnectError("refused")
    monkeypatch.setattr(notify_service, "send_markdown", boom)
    monkeypatch.setattr(settings, "notify_wecom_webhook", webhook)
    monkeypatch.setattr(settings, "notify_on", "failure")
    with caplog.at_level(logging.WARNING, logger="app.services.notify_service"):
        await notify_service.notify_execution_result({
            "execution_id": 1, "status": "FAILED", "suite_name": "s",
            "counts": {"passed": 0, "failed": 1, "errored": 0, "skipped": 0},
            "duration_ms": 100,
        })
        for task in list(notify_service._pending_tasks):
            await task
    records = [r for r in caplog.records if r.__dict__.get("event") == "notify.failed"]
    assert records, "应记录 event=notify.failed 结构化日志"
    assert webhook not in caplog.text and "SECRETKEY123" not in caplog.text


# ─────────────────────────── diagnostics 边界 ───────────────────────────
def test_video_string_true_ignored_not_truthy():
    """video="true"（字符串）必须被忽略而非真值转换误开（设计 §2.3 规则 2）。"""
    plan = resolve_diagnostics("off", False, False, {"video": "true"})
    assert plan.video is False
    assert len(plan.warnings) == 1 and "options.video" in plan.warnings[0]
    # 全局也是 False 时同样不开
    plan2 = resolve_diagnostics("off", False, False, {"video": "1", "har": "on"})
    assert plan2.video is False and plan2.har is False
    assert len(plan2.warnings) == 2


def test_trace_key_present_with_none_falls_back_to_global():
    """options 里 trace 键存在但值为 None：回退到合法全局并给 warning。"""
    plan = resolve_diagnostics("always", False, False, {"trace": None})
    assert plan.trace == "always"
    assert len(plan.warnings) == 1 and "options.trace" in plan.warnings[0]
