"""企业微信通知服务（M3.6 GAP-20，D32 / D33 / D39）。

边界（D33）：只做企微群机器人 markdown 单渠道、全局单 webhook；
不做渠道管理 UI、per-project webhook、钉钉/Slack、@成员、重试队列。

失败隔离（D39）：推送走 ``asyncio.create_task`` + ``asyncio.wait_for`` +
**全异常吞掉**，只记结构化日志（``event=notify.failed``），绝不影响执行结果；
日志不打印 webhook 完整 URL（含 secret key）。
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


class NotifySendError(Exception):
    """webhook 发送失败（HTTP 非 2xx 或响应 errcode != 0）。"""


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


#: fire-and-forget 任务的强引用集合（防止任务被 GC 静默丢弃）
_pending_tasks: set[asyncio.Task] = set()


async def _send_safe(webhook: str, content: str, timeout_s: float) -> None:
    """D39：wait_for 包超时 + 全异常吞掉，只记 event=notify.failed（不含 webhook URL）。"""
    try:
        await asyncio.wait_for(send_markdown(webhook, content, timeout_s=timeout_s),
                               timeout=timeout_s + 1.0)
    except Exception:
        logger.warning("企微通知推送失败（不影响执行结果）",
                       extra={"event": "notify.failed"}, exc_info=True)


async def notify_execution_result(payload: dict[str, Any]) -> None:
    """执行终态推送入口。

    读 settings 判门控（webhook 空串 = 全局禁用；notify_on 门控），
    通过后 ``asyncio.create_task(_send_safe(...))`` fire-and-forget ——
    调用方 await 本函数只会等待"是否建任务"的同步逻辑，绝不等待推送本身，
    更不会收到推送异常（D39）。
    """
    webhook = settings.notify_wecom_webhook
    if not webhook:
        return
    status = str(payload.get("status") or "")
    if not should_notify(settings.notify_on, status):
        return

    content = build_markdown({**payload, "base_url": settings.public_base_url})
    task = asyncio.create_task(
        _send_safe(webhook, content, timeout_s=settings.notify_timeout_s))
    _pending_tasks.add(task)
    task.add_done_callback(_pending_tasks.discard)


def mask_webhook(webhook: str) -> str:
    """webhook 掩码（测试端点响应防凭据泄漏）：key 只留首尾各 1 字符，不可还原。"""
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
