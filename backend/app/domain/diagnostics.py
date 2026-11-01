"""诊断解析（M3.6 GAP-08，D34）：target options > 全局 env。

纯函数、零业务依赖（与 ``domain.scan`` 同一先例），不 import settings ——
单测无需 patch 任何全局状态。非法值回退默认并产出 warning（字符串元组，
由执行器写日志，不进事件流、不影响执行结果）。
"""
from __future__ import annotations

from dataclasses import dataclass

#: 合法 trace 模式（D35）
TRACE_MODES: frozenset[str] = frozenset({"off", "on-failure", "always"})
#: 默认 trace 模式（D35：on-failure 是 Playwright 官方推荐姿势）
DEFAULT_TRACE = "on-failure"


@dataclass(frozen=True)
class DiagnosticsPlan:
    """解析后的诊断计划。"""
    trace: str = DEFAULT_TRACE        # off / on-failure / always
    video: bool = False
    har: bool = False
    warnings: tuple[str, ...] = ()


def resolve_diagnostics(global_trace: str, global_video: bool, global_har: bool,
                        options: dict | None) -> DiagnosticsPlan:
    """解析优先级：``options`` 里的 trace/video/har > 全局 env。

    规则（设计 §2.3）：
    1. trace：options 值合法 → 用之；否则用全局（合法时）；再否则回退默认 +
       warning。options 值非法 → warning 并回退到全局（全局合法时）或默认。
    2. video / har：options 值为 **bool** 才覆盖全局；非 bool（如 "yes"）→
       忽略 + warning（不做真值转换，避免字符串 "false" 意外为真）。
    """
    warnings: list[str] = []
    opts = options or {}

    # ── trace ────────────────────────────────────────────────
    opt_trace = opts.get("trace")
    if isinstance(opt_trace, str) and opt_trace in TRACE_MODES:
        trace = opt_trace
    else:
        if "trace" in opts:
            warnings.append(
                f"options.trace 非法值 {opt_trace!r}（合法：{sorted(TRACE_MODES)}），回退全局配置")
        if isinstance(global_trace, str) and global_trace in TRACE_MODES:
            trace = global_trace
        else:
            if global_trace not in (None, ""):
                warnings.append(
                    f"全局 trace 非法值 {global_trace!r}，回退默认 {DEFAULT_TRACE!r}")
            trace = DEFAULT_TRACE

    # ── video / har（只认 bool，非 bool 一律忽略 + warning）────
    def _flag(key: str, global_value: bool) -> tuple[bool, list[str]]:
        opt_value = opts.get(key)
        if isinstance(opt_value, bool):
            return opt_value, []
        if key in opts:
            return bool(global_value), [f"options.{key} 非法值 {opt_value!r}（需 bool），已忽略"]
        return bool(global_value), []

    video, w1 = _flag("video", global_video)
    har, w2 = _flag("har", global_har)
    warnings.extend(w1)
    warnings.extend(w2)

    return DiagnosticsPlan(trace=trace, video=video, har=har,
                           warnings=tuple(warnings))
