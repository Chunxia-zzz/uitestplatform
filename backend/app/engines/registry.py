"""引擎注册表 + 启动期强校验（P1 / P3）。"""
from __future__ import annotations

import importlib
import logging
from collections.abc import Callable, Iterable
from typing import Any

from app.core.errors import EngineNotFound, ProjectPlatformEngineMismatch
from app.domain.capabilities import (
    CAPABILITY_MATRIX,
    ENGINES,
    EngineMeta,
    assert_engine_platform_consistency,
)
from app.domain.enums import PLATFORM_ENGINES
from app.engines.base import EngineAdapter

logger = logging.getLogger(__name__)


class EngineRegistry:
    """引擎注册表。注册的是**工厂**，实例由 SessionManager 按需创建。"""

    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], EngineAdapter]] = {}

    def register(self, engine_key: str, factory: Callable[[], EngineAdapter]) -> None:
        self._factories[engine_key] = factory

    def register_path(self, engine_key: str, dotted_path: str) -> None:
        """延迟导入：避免启动时 import playwright（未装也能起服务）。"""
        module_path, _, attr = dotted_path.partition(":")

        def _factory() -> EngineAdapter:
            module = importlib.import_module(module_path)
            return getattr(module, attr)()

        self._factories[engine_key] = _factory

    # ── 查询 ────────────────────────────────────────────────
    @property
    def keys(self) -> list[str]:
        return sorted(self._factories)

    @property
    def platforms(self) -> frozenset[str]:
        return frozenset(PLATFORM_ENGINES)

    @property
    def platform_engines(self) -> dict[str, frozenset[str]]:
        return PLATFORM_ENGINES

    def meta(self, engine_key: str) -> EngineMeta:
        meta = ENGINES.get(engine_key)
        if not meta:
            raise EngineNotFound(f"引擎 {engine_key} 未注册", {"engine_key": engine_key})
        return meta

    def validate_route(self, platform: str, engine_key: str) -> EngineMeta:
        """P1：端与引擎必须匹配（写入期拦截，执行期再校验一次）。"""
        meta = self.meta(engine_key)
        if platform not in meta.platforms:
            raise ProjectPlatformEngineMismatch(
                f"引擎 {engine_key} 不支持平台 {platform}",
                {"platform": platform, "engine_key": engine_key,
                 "supported_platforms": sorted(meta.platforms)},
            )
        return meta

    def create(self, engine_key: str) -> EngineAdapter:
        factory = self._factories.get(engine_key)
        if not factory:
            raise EngineNotFound(f"引擎 {engine_key} 未注册", {"engine_key": engine_key})
        adapter = factory()
        if adapter.key != engine_key:
            raise RuntimeError(f"适配器 key 不一致：注册为 {engine_key}，实例为 {adapter.key}")
        return adapter

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "key": meta.key, "label": meta.label,
                "platforms": sorted(meta.platforms),
                "implemented": meta.implemented,
                "action_count": len(CAPABILITY_MATRIX.get(meta.key, ())),
            }
            for meta in (ENGINES[k] for k in self.keys)
        ]


def build_default_registry() -> EngineRegistry:
    registry = EngineRegistry()
    for key, meta in ENGINES.items():
        registry.register_path(key, meta.adapter_path)
    return registry


#: 进程级注册表（无状态，可安全共享；**有状态的是 SessionManager，不是它**）
registry = build_default_registry()


# ─────────────────────── 启动期强校验 ───────────────────────
def assert_catalog_consistency(rows: Iterable[tuple[str, list[str]]]) -> None:
    """动作字典（DB）与能力矩阵（代码）**双向**校验（M1 FR7 / F2）。

    单向只能发现"声明了但矩阵没有"；反方向的遗漏会让动作永远选不到（下拉由字典驱动）
    → 死代码，且无人发现。
    """
    declared_in_db: dict[str, set[str]] = {}
    for action_key, engines in rows:
        for engine in engines or []:
            declared_in_db.setdefault(engine, set()).add(action_key)

    errors: list[str] = []
    for engine, matrix_actions in CAPABILITY_MATRIX.items():
        db_actions = declared_in_db.get(engine, set())
        missing_in_db = matrix_actions - db_actions
        missing_in_matrix = db_actions - matrix_actions
        if missing_in_db:
            errors.append(f"[{engine}] 矩阵有但字典未声明: {sorted(missing_in_db)}")
        if missing_in_matrix:
            errors.append(f"[{engine}] 字典声明但矩阵没有: {sorted(missing_in_matrix)}")

    for engine in declared_in_db:
        if engine not in CAPABILITY_MATRIX:
            errors.append(f"字典声明了未注册引擎: {engine}")

    if errors:
        raise RuntimeError("动作字典/能力矩阵不一致，拒绝启动：\n" + "\n".join(errors))
    logger.info("动作字典 ↔ 能力矩阵 双向校验通过（%s 个引擎）", len(CAPABILITY_MATRIX))


def assert_locator_dict_consistency() -> None:
    """定位字典 vs 引擎注册表（M2 §2.5.5 的三道检查）。"""
    from app.domain.locator_types import LOCATOR_TYPES

    assert_engine_platform_consistency()

    for platform in LOCATOR_TYPES:
        if platform not in PLATFORM_ENGINES:
            raise RuntimeError(f"定位字典含未知平台 {platform}")

    for platform, engine_keys in PLATFORM_ENGINES.items():
        for engine in engine_keys:
            supported = [
                t for t in LOCATOR_TYPES[platform].types.values() if engine in t.engines
            ]
            if not supported:
                raise RuntimeError(
                    f"平台 {platform} 的引擎 {engine} 在定位字典中无任何可用类型 → "
                    f"该引擎的元素永远配不出来")
    for platform, pl in LOCATOR_TYPES.items():
        for spec in pl.types.values():
            extra = spec.engines - pl.engines
            if extra:
                raise RuntimeError(f"{platform}.{spec.key} 声明了不属于该平台的引擎 {extra}")

    logger.info("定位字典 ↔ 引擎注册表 校验通过（%s 端 / %s 类型）",
                len(LOCATOR_TYPES), sum(len(p.types) for p in LOCATOR_TYPES.values()))
