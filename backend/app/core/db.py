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
        action_rows = await session.execute(select(ActionCatalog.action_key))
        existing = {row[0] for row in action_rows.all()}
        added = 0
        for spec in ACTION_CATALOG:
            if spec.key in existing:
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
        logger.info("action_catalog seeded: +%s (total %s)", added, counts["actions"])
    return counts
