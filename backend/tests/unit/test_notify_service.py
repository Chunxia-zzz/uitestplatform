"""企微通知服务（M3.6 GAP-20）：门控 / markdown / fire-and-forget / 掩码 / 测试端点三态。"""
from __future__ import annotations

import asyncio

import httpx
import pytest

from app.api.v1.notifications import send_test_notification
from app.core.config import settings
from app.core.errors import NotifyNotConfigured, NotifySendFailed
from app.services import notify_service


def _payload(**overrides) -> dict:
    base = {
        "execution_id": 123, "status": "FAILED", "suite_name": "冒烟回归",
        "counts": {"passed": 3, "failed": 1, "errored": 0, "skipped": 0},
        "duration_ms": 42300, "base_url": "http://host:5173",
    }
    base.update(overrides)
    return base


# ───────────────────────── should_notify 表驱动（D32）─────────────────────────
@pytest.mark.parametrize("notify_on,status,expected", [
    ("none", "PASSED", False), ("none", "FAILED", False),
    ("none", "ERROR", False), ("none", "CANCELLED", False),
    ("failure", "PASSED", False), ("failure", "FAILED", True),
    ("failure", "ERROR", True), ("failure", "CANCELLED", False),
    ("all", "PASSED", True), ("all", "FAILED", True),
    ("all", "ERROR", True), ("all", "CANCELLED", True),
    ("unknown", "FAILED", False),            # 未知门控 → 宁可漏发
    ("", "FAILED", False),
])
def test_should_notify_table(notify_on, status, expected):
    assert notify_service.should_notify(notify_on, status) is expected


# ───────────────────────── build_markdown（纯函数）─────────────────────────
def test_build_markdown_full():
    text = notify_service.build_markdown(_payload())
    assert "**❌ 执行失败** 冒烟回归" in text
    assert "> 来源：用例集「冒烟回归」" in text
    assert "> 结果：通过 3 / 失败 1 / 异常 0 / 跳过 0" in text
    assert "> 耗时：42.3s" in text
    assert "> 执行：#123" in text
    assert "> [查看报告](http://host:5173/executions/123/report)" in text


def test_build_markdown_manual_without_suite():
    text = notify_service.build_markdown(_payload(suite_name=None, base_url=None))
    assert "手动提交" in text
    assert "> 来源：手动提交" in text
    assert "查看报告" not in text            # base_url 为空 → 整行省略


def test_build_markdown_emoji_map():
    assert "✅" in notify_service.build_markdown(_payload(status="PASSED"))
    assert "⚠️" in notify_service.build_markdown(_payload(status="ERROR"))
    assert "⏹️" in notify_service.build_markdown(_payload(status="CANCELLED"))


def test_mask_webhook_irrecoverable():
    webhook = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=7a8b9c0d1e2f"
    masked = notify_service.mask_webhook(webhook)
    assert masked.startswith("https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=")
    assert "7***f" in masked
    assert "7a8b9c0d1e2f" not in masked      # 不可还原


# ───────────────────── notify_execution_result（D39）─────────────────────
@pytest.mark.asyncio
async def test_not_configured_creates_no_task(monkeypatch):
    sent = []
    monkeypatch.setattr(notify_service, "send_markdown",
                        lambda *a, **kw: sent.append(a) or asyncio.sleep(0))
    monkeypatch.setattr(settings, "notify_wecom_webhook", "")
    await notify_service.notify_execution_result(_payload())
    await asyncio.sleep(0.02)
    assert sent == []                        # webhook 空串 = 全局禁用，未建任务


@pytest.mark.asyncio
async def test_gated_off_sends_nothing(monkeypatch):
    sent = []
    monkeypatch.setattr(notify_service, "send_markdown",
                        lambda *a, **kw: sent.append(a) or asyncio.sleep(0))
    monkeypatch.setattr(settings, "notify_wecom_webhook", "https://qyapi.weixin.qq.com/x")
    monkeypatch.setattr(settings, "notify_on", "none")
    await notify_service.notify_execution_result(_payload())
    await asyncio.sleep(0.02)
    assert sent == []


@pytest.mark.asyncio
async def test_fire_and_forget_sends(monkeypatch):
    sent = []
    async def fake_send(webhook, content, timeout_s=5.0):
        sent.append((webhook, content))
        return {"errcode": 0}
    monkeypatch.setattr(notify_service, "send_markdown", fake_send)
    monkeypatch.setattr(settings, "notify_wecom_webhook", "https://qyapi.weixin.qq.com/x")
    monkeypatch.setattr(settings, "notify_on", "failure")
    monkeypatch.setattr(settings, "public_base_url", "http://host:5173")
    # 绝不影响调用方：立即返回（不等推送完成）
    await notify_service.notify_execution_result(_payload())
    for task in list(notify_service._pending_tasks):
        await task
    assert len(sent) == 1
    assert "执行失败" in sent[0][1]


@pytest.mark.asyncio
async def test_send_failure_swallowed(monkeypatch):
    """发送异常被吞掉且不影响调用方（monkeypatch httpx 路径抛超时）。"""
    async def boom(*a, **kw):
        raise httpx.TimeoutException("connect timeout")
    monkeypatch.setattr(notify_service, "send_markdown", boom)
    monkeypatch.setattr(settings, "notify_wecom_webhook", "https://qyapi.weixin.qq.com/x")
    monkeypatch.setattr(settings, "notify_on", "failure")
    # 不抛 = 通过（D39：全异常吞掉，只记 event=notify.failed）
    await notify_service.notify_execution_result(_payload())
    for task in list(notify_service._pending_tasks):
        await task


# ───────────────────── POST /notifications:test 三态 ─────────────────────
@pytest.mark.asyncio
async def test_endpoint_not_configured_422(monkeypatch):
    monkeypatch.setattr(settings, "notify_wecom_webhook", "")
    with pytest.raises(NotifyNotConfigured):
        await send_test_notification(None)


@pytest.mark.asyncio
async def test_endpoint_send_failed_502(monkeypatch):
    async def boom(*a, **kw):
        raise notify_service.NotifySendError("HTTP 500")
    monkeypatch.setattr(settings, "notify_wecom_webhook", "https://qyapi.weixin.qq.com/x")
    monkeypatch.setattr(notify_service, "send_markdown", boom)
    with pytest.raises(NotifySendFailed):
        await send_test_notification(None)


@pytest.mark.asyncio
async def test_endpoint_ok_200_masked(monkeypatch):
    seen = {}
    async def fake_send(webhook, content, timeout_s=5.0):
        seen["webhook"], seen["content"] = webhook, content
        return {"errcode": 0}
    monkeypatch.setattr(settings, "notify_wecom_webhook",
                        "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=abcdef123456")
    monkeypatch.setattr(notify_service, "send_markdown", fake_send)
    result = await send_test_notification(None)
    assert result["sent"] is True
    assert result["webhook"] == "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=a***6"
    assert seen["content"] == "UIP 通知测试消息"     # 缺省探测文案
