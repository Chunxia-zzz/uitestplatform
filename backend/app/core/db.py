"""数据库装配：异步引擎、会话工厂、建表与动作字典种子。"""
from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_dir() -> None:
    if settings.is_sqlite:
        raw = settings.database_url.split("///", 1)[-1]
        path = Path(raw)
        if path.parent and str(path.parent) not in ("", "."):
            path.parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_dir()

engine = create_async_engine(settings.database_url, echo=settings.db_echo, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db(*, seed: bool = True) -> dict[str, int]:
    """建表 + 幂等种子动作字典。返回统计，供 /healthz 与启动日志使用。"""
    from app import models  # noqa: F401  注册元数据

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    counts = {"actions": 0, "projects": 0, "elements": 0}
    if not seed:
        return counts

    from sqlalchemy import func, select

    from app.domain.action_keys import ACTION_CATALOG, sort_of
    from app.models import ActionCatalog

    async with SessionLocal() as session:
        action_rows = await session.execute(select(ActionCatalog))
        existing = {row.action_key: row for row in action_rows.scalars().all()}
        added = updated = 0
        for spec in ACTION_CATALOG:
            row = existing.get(spec.key)
            # M3.8：已存在的 key 同步可变字段 —— 字典由代码驱动（单一事实来源），
            # params_schema 等扩展（如 set_variable 增 scope）必须落到 DB 镜像，
            # 否则启动校验（矩阵 ↔ DB 双向）会拿旧 schema。
            if row is not None:
                row.name = spec.name
                row.category = spec.category
                row.platforms = list(spec.platforms)
                row.engines = list(spec.engines)
                row.params_schema = spec.params_schema
                row.requires_element = spec.requires_element
                row.sort = sort_of(spec.key)
                updated += 1
                continue
            session.add(ActionCatalog(
                action_key=spec.key,
                name=spec.name,
                category=spec.category,
                platforms=list(spec.platforms),
                engines=list(spec.engines),
                params_schema=spec.params_schema,
                requires_element=spec.requires_element,
                sort=sort_of(spec.key),
                enabled=True,
            ))
            added += 1
        await session.commit()
        counts["actions"] = (await session.execute(
            select(func.count(ActionCatalog.id)))).scalar_one()
        logger.info("action_catalog seeded: +%s (synced %s, total %s)",
                    added, updated, counts["actions"])
    return counts
