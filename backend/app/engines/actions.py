"""动作分发（M1 §2.7）。

一条冻结约定撑起整个机制：
    适配器方法名 == action_key，关键字参数名 == params_schema 属性名
→ ``getattr(adapter, action_key)(chain, ctx, **params)`` 直接转发，
  **没有动作映射表，也没有 if-else 长链**。

平台内建动作（9 个）不经过适配器 —— 防止断言逻辑漂移到引擎层。
"""
from __future__ import annotations

import ast
import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.core.errors import LocatorNotFoundError, UnsupportedActionError, ValidationFailed
from app.domain.action_keys import ACTION_BY_KEY, BUILTIN_ACTION_KEYS, ActionDef
from app.engines.base import ActionContext, EngineAdapter, LocatorChain

logger = logging.getLogger(__name__)

_VAR_RE = re.compile(r"\$\{([a-zA-Z_][\w.]*)\}|\{\{\s*([a-zA-Z_][\w.]*)\s*\}\}")


def render(value: Any, variables: dict[str, Any]) -> Any:
    """变量替换：支持 ``${var}`` 与 ``{{ var }}``，路径可用 ``a.b.c``。

    变量缺失时**保留原样**，不静默变空串 —— 否则定位符会变成一片空白，极难排查。
    """
    if isinstance(value, str):
        def _sub(m: re.Match) -> str:
            key = m.group(1) or m.group(2)
            cur: Any = variables
            for part in key.split("."):
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                else:
                    return m.group(0)
            return str(cur)

        return _VAR_RE.sub(_sub, value)
    if isinstance(value, dict):
        return {k: render(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [render(v, variables) for v in value]
    return value


@dataclass(frozen=True, slots=True)
class ActionSpec:
    action_key: str
    kind: str                       # "element" | "plain"
    needs_engine: bool              # False = 平台内建
    handler: Callable[..., Awaitable[Any]] | None = None

    @property
    def is_builtin(self) -> bool:
        return not self.needs_engine


# ─────────────────────── 平台内建实现 ───────────────────────
async def _builtin_assert_equals(adapter, chain, ctx, params):
    actual, expected = params.get("actual"), params.get("expected")
    if str(actual) != str(expected):
        raise AssertionError(f"断言失败：{actual!r} != {expected!r}")


async def _builtin_assert_contains(adapter, chain, ctx, params):
    actual, expected = str(params.get("actual", "")), str(params.get("expected", ""))
    if expected not in actual:
        raise AssertionError(f"断言失败：{actual!r} 不含 {expected!r}")


async def _builtin_assert_matches(adapter, chain, ctx, params):
    actual, pattern = str(params.get("actual", "")), str(params.get("pattern", ""))
    if not re.search(pattern, actual):
        raise AssertionError(f"断言失败：{actual!r} 不匹配 /{pattern}/")


async def _poll_until(ctx: ActionContext, predicate) -> bool:
    """在 ``ctx.timeout_ms`` 窗口内轮询 predicate，直到为真或超时。

    Q-05 已确认：**不设固定重试次数**，只受超时窗口约束。页面慢 200ms 不再误报失败，
    而超时窗口也不会被"重试 3 次 × 每次 15s"放大成 45s。
    """
    timeout = max(0, ctx.timeout_ms)
    interval = max(1, settings.assert_poll_interval_ms) / 1000
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout / 1000
    while True:
        if await predicate():
            return True
        remaining = deadline - loop.time()
        if remaining <= 0:
            return False
        await asyncio.sleep(min(interval, remaining))


async def _builtin_assert_visible(adapter, chain, ctx, params):
    if adapter is None or chain is None:
        raise ValidationFailed("assert_visible 需要引擎与元素")
    if await _poll_until(ctx, lambda: adapter.check_exists(chain, ctx)):
        return
    raise AssertionError(
        f"断言失败：元素 {chain.element_id} 在 {ctx.timeout_ms}ms 内一直不可见")


async def _builtin_assert_not_exists(adapter, chain, ctx, params):
    if adapter is None or chain is None:
        return

    async def gone() -> bool:
        try:
            return not await adapter.check_exists(chain, ctx)
        except LocatorNotFoundError:
            return True

    if await _poll_until(ctx, gone):
        return
    raise AssertionError(
        f"断言失败：元素 {chain.element_id} 在 {ctx.timeout_ms}ms 内仍然存在")


async def _builtin_set_variable(adapter, chain, ctx, params):
    return ctx.set_var(params.get("name"), params.get("value"))


_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.Constant,
    ast.Name, ast.Load, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow,
    ast.USub, ast.UAdd, ast.Not, ast.And, ast.Or, ast.Eq, ast.NotEq, ast.Lt,
    ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.List, ast.Tuple, ast.Dict,
    ast.Subscript, ast.Slice, ast.IfExp, ast.Call,
)
_ALLOWED_CALLS = {"len", "str", "int", "float", "bool", "abs", "min", "max", "round"}


async def _builtin_eval_expression(adapter, chain, ctx, params):
    expr = str(params.get("expression", ""))
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ValidationFailed(f"表达式语法错误：{exc.msg}") from exc
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValidationFailed(f"表达式含不允许的语法：{type(node).__name__}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_CALLS:
                raise ValidationFailed("表达式只允许白名单函数调用")
    result = eval(compile(tree, "<expr>", "eval"), {"__builtins__": {}}, dict(ctx.variables))  # noqa: S307
    return ctx.set_var(params.get("output_var"), result)


async def _builtin_db_query(adapter, chain, ctx, params):
    from sqlalchemy import text

    from app.core.db import SessionLocal

    sql = str(params.get("sql", "")).strip()
    if not sql.lower().startswith(("select", "show", "desc", "explain")):
        raise ValidationFailed("db_query 仅允许只读语句")
    async with SessionLocal() as session:
        result = await session.execute(text(sql), {"p": params.get("params") or []})
        rows = [dict(r._mapping) for r in result.fetchmany(200)]
    return ctx.set_var(params.get("output_var"), rows)


async def _builtin_run_python(adapter, chain, ctx, params):
    if not settings.allow_run_python:
        raise UnsupportedActionError(
            "run_python 默认禁用（D11）。需要显式配置 UIP_ALLOW_RUN_PYTHON=true",
            {"allow_run_python": False},
        )
    code = str(params.get("code", ""))
    safe_builtins = {name: __builtins__[name] if isinstance(__builtins__, dict)
                     else getattr(__builtins__, name)
                     for name in ("len", "str", "int", "float", "range", "min", "max",
                                  "sum", "sorted", "print")}
    namespace: dict[str, Any] = {"__builtins__": safe_builtins,
                                 "variables": dict(ctx.variables)}

    def _run() -> Any:
        exec(compile(code, "<run_python>", "exec"), namespace)  # noqa: S102
        return namespace.get("result")

    result = await asyncio.wait_for(asyncio.to_thread(_run), timeout=settings.run_python_timeout_s)
    return ctx.set_var(params.get("output_var"), result)


BUILTIN_HANDLERS: dict[str, Callable[..., Awaitable[Any]]] = {
    "assert_equals": _builtin_assert_equals,
    "assert_contains": _builtin_assert_contains,
    "assert_matches": _builtin_assert_matches,
    "assert_visible": _builtin_assert_visible,
    "assert_not_exists": _builtin_assert_not_exists,
    "set_variable": _builtin_set_variable,
    "eval_expression": _builtin_eval_expression,
    "db_query": _builtin_db_query,
    "run_python": _builtin_run_python,
}

BUILTIN_SPECS: dict[str, ActionSpec] = {
    key: ActionSpec(key, "element" if key.startswith("assert_") else "plain", False,
                    BUILTIN_HANDLERS[key])
    for key in BUILTIN_HANDLERS
}

assert set(BUILTIN_SPECS) == set(BUILTIN_ACTION_KEYS), "内建动作表与字典不一致"


def get_action(action_key: str) -> ActionDef:
    spec = ACTION_BY_KEY.get(action_key)
    if not spec:
        raise ValidationFailed(f"未知动作 {action_key}", {"action_key": action_key})
    return spec


async def dispatch(action_key: str, adapter: EngineAdapter | None,
                   chain: LocatorChain | None, params: dict[str, Any],
                   ctx: ActionContext) -> Any:
    """统一入口。返回动作结果（可能带 output_var 语义）。"""
    spec = get_action(action_key)
    params = render(params or {}, ctx.variables)

    # 1) 平台内建
    builtin = BUILTIN_SPECS.get(action_key)
    if builtin is not None:
        return await builtin.handler(adapter, chain, ctx, params)

    # 2) 引擎动作
    if adapter is None:
        raise UnsupportedActionError(f"动作 {action_key} 需要引擎，但当前没有可用会话",
                                     {"action_key": action_key})
    if action_key not in adapter.capabilities:
        raise UnsupportedActionError(
            f"引擎 {adapter.key} 不支持动作 {action_key}",
            {"engine_key": adapter.key, "action_key": action_key},
        )
    if spec.requires_element and chain is None:
        raise ValidationFailed(f"动作 {action_key} 需要绑定元素", {"action_key": action_key})

    method = getattr(adapter, action_key, None)
    if method is None:
        raise UnsupportedActionError(f"适配器 {adapter.key} 未实现 {action_key}")

    ctx.emit("action.invoke", action_key=action_key,
             element_id=getattr(chain, "element_id", None), params=params)
    return await method(chain, ctx, **params)
