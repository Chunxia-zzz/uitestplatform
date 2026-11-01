"""测试基线：每个用例一个独立的内存 SQLite 库。"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.db import Base
from app import models  # noqa: F401  注册全部表


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def project(db):
    from app.models import Project

    row = Project(name="T", code="t", platform="WEB", engine_key="playwright",
                  default_timeout_ms=5000)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row
