"""通知端点（M3.6 GAP-20 / M3.7 GAP-43）：测试推送。

POST /api/v1/notifications:test —— 同步等待（不走 fire-and-forget），
调用方需要立即知道成败：未配置 422 / 发送失败 502 / 成功 200 + webhook 掩码。
按 ``UIP_NOTIFY_CHANNEL`` 选择企微 markdown 或飞书 interactive 卡片。
路由带冒号的先例：POST /suites/{id}:run 已存在。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session
from app.core.errors import NotifyNotConfigured, NotifySendFailed
from app.services import notify_service

router = APIRouter(tags=["notifications"])

#: 缺省探测文案（设计 §2.2）
DEFAULT_TEST_CONTENT = "UIP 通知测试消息"


class NotifyTestRequest(BaseModel):
    content: str | None = Field(default=None, max_length=2048,
                                description="自定义消息内容；缺省发固定探测文案")


@router.post("/notifications:test")
async def send_test_notification(body: NotifyTestRequest | None = None,
                                 db: AsyncSession = Depends(get_session)):
    """测试推送（同步等待）。成功 200 {sent, channel, webhook 掩码}；失败映射见模块 docstring。"""
    channel = notify_service.active_channel()
    webhook = notify_service.channel_webhook(channel)
    if not webhook:
        raise NotifyNotConfigured(detail={"channel": channel})
    text = (body.content if body and body.content else None) or DEFAULT_TEST_CONTENT
    try:
        if channel == "feishu":
            card = notify_service.build_feishu_test_card(
                text, settings.notify_feishu_keyword)
            await notify_service.send_feishu(
                webhook, card, timeout_s=settings.notify_timeout_s)
        else:
            await notify_service.send_markdown(
                webhook, text, timeout_s=settings.notify_timeout_s)
    except Exception as exc:
        raise NotifySendFailed(f"通知发送失败：{type(exc).__name__}",
                               {"channel": channel, "reason": str(exc)[:200]}) from exc
    return {"sent": True, "channel": channel,
            "webhook": notify_service.mask_webhook(webhook)}
