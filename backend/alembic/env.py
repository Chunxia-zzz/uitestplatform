"""Alembic 环境（GAP-33）。

设计要点
--------
1. **URL 从应用配置读取**（``settings.database_url``），不在 ``alembic.ini`` 里重复一份；
2. 应用用异步驱动（aiosqlite / aiomysql），迁移用同步驱动 —— 这里做一次显式转换，
   不做"猜驱动"的魔法；
3. SQLite 不支持大部分 ALTER，``render_as_batch=True`` 让它用"建新表 + 拷贝"实现；
4. ``compare_type=True``：字段类型变化也能被 ``alembic check`` 发现。
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import create_engine

# 保证 `alembic` 在 backend/ 下执行时能 import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings  # noqa: E402
from app.core.db import Base  # noqa: E402
from app import models  # noqa: E402,F401  注册全部元数据

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _sync_url(url: str) -> str:
    """异步驱动 → 同步驱动。未识别的 URL 原样返回。"""
    mapping = {
        "sqlite+aiosqlite": "sqlite",
        "mysql+aiomysql": "mysql+pymysql",
    }
    for async_driver, sync_driver in mapping.items():
        if url.startswith(async_driver):
            return url.replace(async_driver, sync_driver, 1)
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_sync_url(settings.database_url),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        render_as_batch=settings.is_sqlite,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_sync_url(settings.database_url), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=settings.is_sqlite,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
