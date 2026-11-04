"""通知服务（M3.6 GAP-20 企微 / M3.7 GAP-43 飞书，D32 / D33 / D39 / D41）。

边界（D33 / D41）：全局单渠道（``UIP_NOTIFY_CHANNEL`` = wecom | feishu）、全局单 webhook；
不做渠道管理 UI、per-project webhook、多渠道并行、@成员、重试队列。
飞书走自定义机器人 ``interactive`` 卡片；标题固定带关键词，命中机器人「自定义关键词」。

失败隔离（D39）：推送走 ``asyncio.create_task`` + ``asyncio.wait_for`` +
**全异常吞掉**，只记结构化日志（``event=notify.failed``），绝不影响执行结果；
日志不打印 webhook 完整 URL（含 secret token）。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

#: 状态 → 企微 markdown emoji（D32：CANCELLED 仅 all 模式可能推送）
STATUS_EMOJI: dict[str, str] = {
    "PASSED": "✅", "FAILED": "❌", "ERROR": "⚠️", "CANCELLED": "⏹️",
}
#: 状态 → 标题文案
STATUS_TITLE: dict[str, str] = {
    "PASSED": "执行通过", "FAILED": "执行失败", "ERROR": "执行异常", "CANCELLED": "执行取消",
}
#: 状态 → 飞书卡片 header 模板色（D41）
FEISHU_HEADER_TEMPLATE: dict[str, str] = {
    "PASSED": "green", "FAILED": "red", "ERROR": "orange", "CANCELLED": "grey",
}
FEISHU_HEADER_FALLBACK = "blue"


class NotifySendError(Exception):
    """webhook 发送失败（HTTP 非 2xx 或响应 errcode/code != 0）。"""


def active_channel() -> str:
    """当前通知渠道（小写）。非法值按 wecom 处理（防御式，正常由 Pydantic 拦住）。"""
    channel = str(getattr(settings, "notify_channel", "wecom") or "").strip().lower()
    return channel if channel in ("wecom", "feishu") else "wecom"


def channel_webhook(channel: str) -> str:
    """取渠道对应的 webhook；空串表示该渠道未配置（= 禁用）。"""
    if channel == "feishu":
        return settings.notify_feishu_webhook
    return settings.notify_wecom_webhook


def channel_label(channel: str) -> str:
    return "飞书" if channel == "feishu" else "企业微信"


def should_notify(notify_on: str, status: str) -> bool:
    """D32 门控（纯函数）：notify_on ∈ {none, failure, all}。

    * none → 全部不发；webhook 空串在调用方处理（= 全局禁用）
    * failure → 只有 FAILED / ERROR 推送（CANCELLED 是人为行为，不推）
    * all → 全推
    * 未知 notify_on → 不发（宁可漏发不可误发）
    """
    mode = (notify_on or "").strip().lower()
    if mode == "all":
        return True
    if mode == "failure":
        return status in ("FAILED", "ERROR")
    return False


def build_markdown(payload: dict[str, Any]) -> str:
    """拼企微 markdown 消息体（纯函数，不依赖网络与 settings）。

    payload 期望键：execution_id / status / suite_name / counts / duration_ms /
    base_url（由调用方从 settings.public_base_url 注入；空则省略链接行）。
    """
    status = str(payload.get("status") or "")
    emoji = STATUS_EMOJI.get(status, "ℹ️")
    title = STATUS_TITLE.get(status, "执行结束")
    suite_name = str(payload.get("suite_name") or "")
    counts = payload.get("counts") or {}
    passed = int(counts.get("passed", 0) or 0)
    failed = int(counts.get("failed", 0) or 0)
    errored = int(counts.get("errored", 0) or 0)
    skipped = int(counts.get("skipped", 0) or 0)

    lines = [f"**{emoji} {title}** {suite_name or '手动提交'}"]
    lines.append(f"> 来源：用例集「{suite_name}」" if suite_name else "> 来源：手动提交")
    lines.append(f"> 结果：通过 {passed} / 失败 {failed} / 异常 {errored} / 跳过 {skipped}")

    duration_ms = payload.get("duration_ms")
    if duration_ms is not None:
        lines.append(f"> 耗时：{int(duration_ms) / 1000:.1f}s")

    execution_id = payload.get("execution_id")
    if execution_id:
        lines.append(f"> 执行：#{execution_id}")

    base_url = str(payload.get("base_url") or "")
    if base_url and execution_id:
        lines.append(f"> [查看报告]({base_url}/executions/{execution_id}/report)")

    return "\n".join(lines)


def _feishu_title(payload: dict[str, Any], keyword: str) -> str:
    """卡片标题 = ``关键词 · 状态文案``；关键词非空时必出现在标题（飞书关键词校验）。"""
    status = str(payload.get("status") or "")
    title = STATUS_TITLE.get(status, "执行结束")
    prefix = str(keyword or "").strip()
    return f"{prefix} · {title}" if prefix else title


def build_feishu_card(payload: dict[str, Any],
                      keyword: str = "UI自动化平台") -> dict[str, Any]:
    """拼飞书自定义机器人 interactive 卡片（纯函数，不依赖网络与 settings）。

    payload 键与 :func:`build_markdown` 一致；返回的 ``card`` 直接作为
    ``{"msg_type": "interactive", "card": ...}`` 的 card 字段。
    """
    status = str(payload.get("status") or "")
    emoji = STATUS_EMOJI.get(status, "ℹ️")
    title = STATUS_TITLE.get(status, "执行结束")
    suite_name = str(payload.get("suite_name") or "")
    counts = payload.get("counts") or {}
    passed = int(counts.get("passed", 0) or 0)
    failed = int(counts.get("failed", 0) or 0)
    errored = int(counts.get("errored", 0) or 0)
    skipped = int(counts.get("skipped", 0) or 0)

    lines = [f"**{emoji} {title}** {suite_name or '手动提交'}"]
    lines.append(f"来源：{'用例集「' + suite_name + '」' if suite_name else '手动提交'}")
    lines.append(f"结果：通过 {passed} / 失败 {failed} / 异常 {errored} / 跳过 {skipped}")

    duration_ms = payload.get("duration_ms")
    if duration_ms is not None:
        lines.append(f"耗时：{int(duration_ms) / 1000:.1f}s")

    execution_id = payload.get("execution_id")
    if execution_id:
        lines.append(f"执行：#{execution_id}")

    elements: list[dict[str, Any]] = [
        {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}},
    ]
    base_url = str(payload.get("base_url") or "")
    if base_url and execution_id:
        elements.append({
            "tag": "action",
            "actions": [{
                "tag": "button",
                "text": {"tag": "plain_text", "content": "查看报告"},
                "url": f"{base_url}/executions/{execution_id}/report",
                "type": "primary",
            }],
        })

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": FEISHU_HEADER_TEMPLATE.get(status, FEISHU_HEADER_FALLBACK),
            "title": {"tag": "plain_text", "content": _feishu_title(payload, keyword)},
        },
        "elements": elements,
    }


def build_feishu_test_card(content: str, keyword: str = "UI自动化平台") -> dict[str, Any]:
    """测试端点用的飞书卡片（蓝色标题 + 自定义正文）。"""
    prefix = str(keyword or "").strip()
    title = f"{prefix} · 通知测试" if prefix else "通知测试"
    return {
        "config": {"wide_screen_mode": True},
        "header": {"template": FEISHU_HEADER_FALLBACK,
                   "title": {"tag": "plain_text", "content": title}},
        "elements": [{
            "tag": "div",
            "text": {"tag": "lark_md", "content": str(content or "")},
        }],
    }


async def send_markdown(webhook: str, content: str, timeout_s: float = 5.0) -> dict:
    """POST markdown 消息到企微 webhook。

    HTTP 非 2xx 或响应 ``errcode != 0`` 都抛 ``NotifySendError``；
    网络异常由 httpx 自行抛出，由调用方统一兜底。
    """
    body = {"msgtype": "markdown", "markdown": {"content": content}}
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        resp = await client.post(webhook, json=body)
    if not (200 <= resp.status_code < 300):
        raise NotifySendError(f"企微 webhook HTTP {resp.status_code}")
    try:
        data = resp.json()
    except ValueError as exc:
        raise NotifySendError("企微 webhook 响应不是 JSON") from exc
    if data.get("errcode") not in (0, None):
        raise NotifySendError(f"企微 webhook errcode={data.get('errcode')}")
    return data


async def send_feishu(webhook: str, card: dict[str, Any],
                      timeout_s: float = 5.0) -> dict:
    """POST interactive 卡片到飞书自定义机器人 webhook。

    飞书即使业务失败也返回 HTTP 200，必须判 ``code``（兼容旧字段 ``StatusCode``）：
    非 0 抛 ``NotifySendError``（关键词不匹配为 ``code=19024``）。
    """
    body = {"msg_type": "interactive", "card": card}
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        resp = await client.post(webhook, json=body)
    if not (200 <= resp.status_code < 300):
        raise NotifySendError(f"飞书 webhook HTTP {resp.status_code}")
    try:
        data = resp.json()
    except ValueError as exc:
        raise NotifySendError("飞书 webhook 响应不是 JSON") from exc
    code = data.get("code", data.get("StatusCode"))
    if code not in (0, None):
        raise NotifySendError(f"飞书 webhook code={code}")
    return data


#: fire-and-forget 任务的强引用集合（防止任务被 GC 静默丢弃）
_pending_tasks: set[asyncio.Task] = set()


async def _send_safe(webhook: str, content: str, timeout_s: float) -> None:
    """D39：wait_for 包超时 + 全异常吞掉，只记 event=notify.failed（不含 webhook URL）。"""
    try:
        await asyncio.wait_for(send_markdown(webhook, content, timeout_s=timeout_s),
                               timeout=timeout_s + 1.0)
    except Exception:
        logger.warning("通知推送失败（不影响执行结果）", extra={"event": "notify.failed",
                                                       "channel": "wecom"}, exc_info=True)


async def _send_feishu_safe(webhook: str, card: dict[str, Any], timeout_s: float) -> None:
    """飞书渠道的 D39 包装：超时 + 全异常吞掉，日志不含 webhook。"""
    try:
        await asyncio.wait_for(send_feishu(webhook, card, timeout_s=timeout_s),
                               timeout=timeout_s + 1.0)
    except Exception:
        logger.warning("通知推送失败（不影响执行结果）", extra={"event": "notify.failed",
                                                       "channel": "feishu"}, exc_info=True)


async def notify_execution_result(payload: dict[str, Any]) -> None:
    """执行终态推送入口（按 ``settings.notify_channel`` 分派）。

    读 settings 判门控（当前渠道 webhook 空串 = 全局禁用；notify_on 门控），
    通过后 ``asyncio.create_task(...)`` fire-and-forget ——
    调用方 await 本函数只会等待"是否建任务"的同步逻辑，绝不等待推送本身，
    更不会收到推送异常（D39）。
    """
    channel = active_channel()
    webhook = channel_webhook(channel)
    if not webhook:
        return
    status = str(payload.get("status") or "")
    if not should_notify(settings.notify_on, status):
        return

    enriched = {**payload, "base_url": settings.public_base_url}
    if channel == "feishu":
        card = build_feishu_card(enriched, settings.notify_feishu_keyword)
        coro = _send_feishu_safe(webhook, card, timeout_s=settings.notify_timeout_s)
    else:
        content = build_markdown(enriched)
        coro = _send_safe(webhook, content, timeout_s=settings.notify_timeout_s)

    task = asyncio.create_task(coro)
    _pending_tasks.add(task)
    task.add_done_callback(_pending_tasks.discard)


def mask_webhook(webhook: str) -> str:
    """webhook 掩码（测试端点响应防凭据泄漏），企微 key 与飞书 hook token 都只留可辨识前缀。"""
    marker = "/hook/"
    idx = webhook.find(marker)
    if idx >= 0:
        head = webhook[: idx + len(marker)]
        token = webhook[idx + len(marker):].split("?", 1)[0]
        return f"{head}{token[:4]}***" if len(token) > 4 else f"{head}***"

    marker = "key="
    idx = webhook.find(marker)
    if idx < 0:
        return webhook[:24] + "***" if len(webhook) > 24 else webhook
    head = webhook[: idx + len(marker)]
    rest = webhook[idx + len(marker):]
    key, sep, extra = rest.partition("&")
    if len(key) > 2:
        masked = f"{key[0]}***{key[-1]}"
    else:
        masked = "***"
    return f"{head}{masked}{sep}{extra}"
