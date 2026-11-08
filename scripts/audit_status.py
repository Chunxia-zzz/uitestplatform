"""能力自检：把"声明支持"与"真的实现了"逐条对比。

    python scripts/audit_status.py

检查四件事：
  1. CAPABILITY_MATRIX 里每个引擎声明的动作，适配器是否真的覆写了（而不是继承基类的 _not_supported）
  2. 覆写的方法签名是否满足冻结约定 FR4（关键字参数名 == params_schema 属性名）
  3. 平台内建动作是否都有 handler
  4. API 路由数量与分层文件清单
"""
from __future__ import annotations

import inspect
import os
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.domain.action_keys import ACTION_BY_KEY, BUILTIN_ACTION_KEYS  # noqa: E402
from app.domain.capabilities import CAPABILITY_MATRIX, ENGINES  # noqa: E402
from app.engines.actions import BUILTIN_SPECS  # noqa: E402
from app.engines.base import EngineAdapter  # noqa: E402


def _load_adapter(adapter_path: str):
    """按注册表的 adapter_path 动态加载，避免脚本硬编码桩类（M4.1 修正）。"""
    module_path, _, attr = adapter_path.partition(":")
    return getattr(importlib.import_module(module_path), attr)


ADAPTERS = {key: _load_adapter(meta.adapter_path) for key, meta in ENGINES.items()}


def implemented_keys(cls) -> set[str]:
    """适配器自己覆写的方法（不是从 EngineAdapter 继承的默认实现）。"""
    own = set()
    for name, value in cls.__dict__.items():
        if name.startswith("_"):
            continue
        base = getattr(EngineAdapter, name, None)
        if callable(value) and value is not base:
            own.add(name)
    return own


def keyword_params(func) -> set[str]:
    sig = inspect.signature(func)
    return {
        name for name, p in sig.parameters.items()
        if p.kind in (p.KEYWORD_ONLY,) and name not in ("chain", "ctx")
    }


def accepts_var_kw(func) -> bool:
    return any(p.kind == p.VAR_KEYWORD for p in inspect.signature(func).parameters.values())


def audit_engine(engine: str) -> tuple[list[str], list[str], list[str]]:
    cls = ADAPTERS[engine]
    declared = CAPABILITY_MATRIX[engine]
    own = implemented_keys(cls)
    done, missing, sig_bad = [], [], []
    for key in sorted(declared):
        if key in own:
            done.append(key)
            spec = ACTION_BY_KEY[key]
            expected = set(spec.props)
            actual = keyword_params(getattr(cls, key))
            if expected != actual and not accepts_var_kw(getattr(cls, key)):
                sig_bad.append(f"{key}: 期望 {sorted(expected)} 实得 {sorted(actual)}")
        else:
            missing.append(key)
    return done, missing, sig_bad


def main() -> int:
    print("=" * 78)
    print("引擎能力自检（声明 vs 实现）")
    print("=" * 78)
    for engine, meta in ENGINES.items():
        done, missing, sig_bad = audit_engine(engine)
        total = len(CAPABILITY_MATRIX[engine])
        print(f"\n[{engine}] 声明 {total} 个动作 · 真实现 {len(done)} · 仅继承默认 {len(missing)}"
              f" · implemented={meta.implemented}")
        if missing:
            print("  未覆写（运行时会抛 NotImplementedError）:")
            print("   ", ", ".join(missing))
        if sig_bad:
            print("  签名不符合 FR4:")
            for item in sig_bad:
                print("   ", item)
        if not missing and not sig_bad:
            print("  ✅ 全部覆写且签名符合约定")

    print("\n" + "=" * 78)
    print("平台内建动作")
    print("=" * 78)
    missing_builtin = sorted(set(BUILTIN_ACTION_KEYS) - set(BUILTIN_SPECS))
    print(f"字典声明 {len(BUILTIN_ACTION_KEYS)} 个 · 有 handler {len(BUILTIN_SPECS)} 个"
          f" · 缺失 {missing_builtin or '无'}")
    for key in sorted(BUILTIN_SPECS):
        print(f"  - {key:<20}{ACTION_BY_KEY[key].name}")

    print("\n" + "=" * 78)
    print("API 路由")
    print("=" * 78)
    from app.main import app

    # 注意：FastAPI 0.146 起 include_router 不再把子路由摊平到 app.routes，
    # 必须读 OpenAPI schema 才能拿到完整清单。
    schema = app.openapi()
    rows = []
    for path, operations in schema.get("paths", {}).items():
        if not (path.startswith("/api") or path == "/healthz"):
            continue
        for method in operations:
            rows.append((path, method.upper()))
    for path, method in sorted(rows, key=lambda x: (x[0], x[1])):
        print(f"  {method:<10}{path}")
    print(f"\n合计 {len(rows)} 个 API 操作（含 /healthz）")

    print("\n" + "=" * 78)
    print("分层文件统计")
    print("=" * 78)
    app_dir = ROOT / "backend" / "app"
    for sub in ("core", "domain", "engines", "models", "repositories", "services", "schemas", "api"):
        count = len(list((app_dir / sub).rglob("*.py")))
        print(f"  app/{sub:<14}{count} 个 .py")
    tests = len(list((ROOT / "backend" / "tests").rglob("test_*.py")))
    print(f"  tests/         {tests} 个测试文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
