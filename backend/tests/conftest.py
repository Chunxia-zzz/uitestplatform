"""测试基线：每个用例一个独立的内存 SQLite 库。"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.db import Base
from app import models  # noqa: F401  注册全部表


@pytest.fixture(autouse=True)
def isolate_notify_settings(monkeypatch):
    """测试不得受本地 ``backend/.env`` 影响：通知配置统一回到默认值。

    D41 之后本地开发常把渠道切成 feishu；若不隔离，老测试会走真实飞书 webhook。
    用例内部的 monkeypatch 在此之后执行，仍可覆盖这些值。
    """
    from app.core.config import settings

    monkeypatch.setattr(settings, "notify_channel", "wecom", raising=False)
    monkeypatch.setattr(settings, "notify_wecom_webhook", "", raising=False)
    monkeypatch.setattr(settings, "notify_feishu_webhook", "", raising=False)
    monkeypatch.setattr(settings, "notify_feishu_keyword", "UI自动化平台", raising=False)
    monkeypatch.setattr(settings, "notify_on", "failure", raising=False)
    monkeypatch.setattr(settings, "public_base_url", "", raising=False)
    yield


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
