"""飞书通知渠道（M3.7 GAP-43 / D41）：卡片构建 / 响应判定 / 渠道分派 / 掩码。"""
from __future__ import annotations

import asyncio

import httpx
import pytest

from app.api.v1.notifications import send_test_notification
from app.core.config import settings
from app.core.errors import NotifyNotConfigured
from app.services import notify_service

FEISHU_WEBHOOK = ("https://open.feishu.cn/open-apis/bot/v2/hook/"
                  "9f2c1d4e-0000-0000-0000-000000000000")


def _payload(**overrides) -> dict:
    base = {
        "execution_id": 123, "status": "FAILED", "suite_name": "冒烟回归",
        "counts": {"passed": 3, "failed": 1, "errored": 0, "skipped": 0},
        "duration_ms": 42300, "base_url": "http://host:5173",
    }
    base.update(overrides)
    return base


@pytest.fixture
def mock_feishu_transport():
    """把 notify_service 内的 httpx.AsyncClient 换成 MockTransport 版本。"""
    def install(handler):
        transport = httpx.MockTransport(handler)
        real_client = httpx.AsyncClient

        class _Client(real_client):
            def __init__(self, *a, **kw):
                kw["transport"] = transport
                super().__init__(*a, **kw)
        return _Client
    return install


# ───────────────────────── build_feishu_card（纯函数）─────────────────────────
def test_build_card_failed_full():
    card = notify_service.build_feishu_card(_payload())
    assert card["header"]["template"] == "red"
    assert card["header"]["title"]["content"] == "UI自动化平台 · 执行失败"
    body = card["elements"][0]["text"]["content"]
    assert "❌ 执行失败" in body and "冒烟回归" in body
    assert "来源：用例集「冒烟回归」" in body
    assert "结果：通过 3 / 失败 1 / 异常 0 / 跳过 0" in body
    assert "耗时：42.3s" in body and "执行：#123" in body
    action = card["elements"][1]
    assert action["tag"] == "action"
    assert action["actions"][0]["url"] == "http://host:5173/executions/123/report"
    assert action["actions"][0]["text"]["content"] == "查看报告"


def test_build_card_without_base_url_has_no_action():
    card = notify_service.build_feishu_card(_payload(base_url=None, suite_name=None))
    assert [e["tag"] for e in card["elements"]] == ["div"]
    assert "手动提交" in card["elements"][0]["text"]["content"]


@pytest.mark.parametrize("status,template", [
    ("PASSED", "green"), ("FAILED", "red"), ("ERROR", "orange"),
    ("CANCELLED", "grey"), ("UNKNOWN", "blue"),
])
def test_build_card_colors(status, template):
    assert notify_service.build_feishu_card(_payload(status=status))["header"]["template"] \
        == template


def test_build_card_keyword_empty_has_no_prefix():
    card = notify_service.build_feishu_card(_payload(), keyword="")
    assert card["header"]["title"]["content"] == "执行失败"


def test_build_test_card_contains_keyword():
    card = notify_service.build_feishu_test_card("UIP 通知测试消息")
    assert card["header"]["title"]["content"] == "UI自动化平台 · 通知测试"
    assert card["elements"][0]["text"]["content"] == "UIP 通知测试消息"


# ───────────────────────── send_feishu 响应判定 ─────────────────────────
@pytest.mark.asyncio
async def test_send_feishu_ok(monkeypatch, mock_feishu_transport):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"code": 0, "msg": "success", "data": {}})

    monkeypatch.setattr(notify_service.httpx, "AsyncClient",
                        mock_feishu_transport(handler))
    card = notify_service.build_feishu_test_card("hi")
    data = await notify_service.send_feishu(FEISHU_WEBHOOK, card)
    assert data["code"] == 0
    assert '"msg_type":"interactive"' in seen["body"].replace(" ", "")


@pytest.mark.asyncio
async def test_send_feishu_keyword_error(monkeypatch, mock_feishu_transport):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 19024, "msg": "Key Words Not Found"})

    monkeypatch.setattr(notify_service.httpx, "AsyncClient",
                        mock_feishu_transport(handler))
    with pytest.raises(notify_service.NotifySendError, match="19024"):
        await notify_service.send_feishu(FEISHU_WEBHOOK,
                                         notify_service.build_feishu_test_card("hi"))


@pytest.mark.asyncio
async def test_send_feishu_http_500(monkeypatch, mock_feishu_transport):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    monkeypatch.setattr(notify_service.httpx, "AsyncClient",
                        mock_feishu_transport(handler))
    with pytest.raises(notify_service.NotifySendError, match="HTTP 500"):
        await notify_service.send_feishu(FEISHU_WEBHOOK,
                                         notify_service.build_feishu_test_card("hi"))


@pytest.mark.asyncio
async def test_send_feishu_non_json(monkeypatch, mock_feishu_transport):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>no</html>")

    monkeypatch.setattr(notify_service.httpx, "AsyncClient",
                        mock_feishu_transport(handler))
    with pytest.raises(notify_service.NotifySendError, match="JSON"):
        await notify_service.send_feishu(FEISHU_WEBHOOK,
                                         notify_service.build_feishu_test_card("hi"))


# ───────────────────────── notify_execution_result 分派 ─────────────────────────
@pytest.mark.asyncio
async def test_dispatch_feishu_uses_card_sender(monkeypatch):
    seen = {}

    async def fake_feishu(webhook, card, timeout_s=5.0):
        seen["webhook"], seen["card"] = webhook, card
        return {"code": 0}

    async def forbidden(*a, **kw):
        raise AssertionError("feishu 渠道不应调用企微 send_markdown")

    monkeypatch.setattr(notify_service, "send_feishu", fake_feishu)
    monkeypatch.setattr(notify_service, "send_markdown", forbidden)
    monkeypatch.setattr(settings, "notify_channel", "feishu")
    monkeypatch.setattr(settings, "notify_feishu_webhook", FEISHU_WEBHOOK)
    monkeypatch.setattr(settings, "notify_on", "failure")
    monkeypatch.setattr(settings, "public_base_url", "http://host:5173")

    await notify_service.notify_execution_result(_payload())
    for task in list(notify_service._pending_tasks):
        await task
    assert seen["webhook"] == FEISHU_WEBHOOK
    assert seen["card"]["header"]["title"]["content"] == "UI自动化平台 · 执行失败"


@pytest.mark.asyncio
async def test_dispatch_wecom_unchanged(monkeypatch):
    seen = {}

    async def fake_markdown(webhook, content, timeout_s=5.0):
        seen["webhook"], seen["content"] = webhook, content
        return {"errcode": 0}

    monkeypatch.setattr(notify_service, "send_markdown", fake_markdown)
    monkeypatch.setattr(settings, "notify_channel", "wecom")
    monkeypatch.setattr(settings, "notify_wecom_webhook", "https://qyapi.weixin.qq.com/x")
    monkeypatch.setattr(settings, "notify_on", "failure")

    await notify_service.notify_execution_result(_payload())
    for task in list(notify_service._pending_tasks):
        await task
    assert seen["webhook"] == "https://qyapi.weixin.qq.com/x"
    assert "执行失败" in seen["content"]


@pytest.mark.asyncio
async def test_feishu_channel_without_webhook_creates_no_task(monkeypatch):
    monkeypatch.setattr(settings, "notify_channel", "feishu")
    monkeypatch.setattr(settings, "notify_feishu_webhook", "")
    monkeypatch.setattr(settings, "notify_on", "failure")
    before = len(notify_service._pending_tasks)
    await notify_service.notify_execution_result(_payload())
    await asyncio.sleep(0.01)
    assert len(notify_service._pending_tasks) == before


# ───────────────────────── 测试端点 / 掩码 ─────────────────────────
@pytest.mark.asyncio
async def test_endpoint_feishu_ok_and_masked(monkeypatch):
    seen = {}

    async def fake_feishu(webhook, card, timeout_s=5.0):
        seen["webhook"], seen["card"] = webhook, card
        return {"code": 0}

    monkeypatch.setattr(settings, "notify_channel", "feishu")
    monkeypatch.setattr(settings, "notify_feishu_webhook", FEISHU_WEBHOOK)
    monkeypatch.setattr(notify_service, "send_feishu", fake_feishu)
    result = await send_test_notification(None)
    assert result["sent"] is True and result["channel"] == "feishu"
    assert result["webhook"].endswith("9f2c***")
    assert "9f2c1d4e-0000-0000-0000-000000000000" not in result["webhook"]
    assert seen["card"]["header"]["title"]["content"] == "UI自动化平台 · 通知测试"


@pytest.mark.asyncio
async def test_endpoint_feishu_not_configured_422(monkeypatch):
    monkeypatch.setattr(settings, "notify_channel", "feishu")
    monkeypatch.setattr(settings, "notify_feishu_webhook", "")
    monkeypatch.setattr(settings, "notify_wecom_webhook", "https://qyapi.weixin.qq.com/x")
    with pytest.raises(NotifyNotConfigured) as exc:
        await send_test_notification(None)
    assert exc.value.detail["channel"] == "feishu"


def test_mask_feishu_hook_token():
    masked = notify_service.mask_webhook(FEISHU_WEBHOOK)
    assert masked == "https://open.feishu.cn/open-apis/bot/v2/hook/9f2c***"
    assert "0000-1111" not in masked
