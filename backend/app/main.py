"""FastAPI 应用装配。

启动顺序（失败即拒绝启动，这是 P3 的落地方式）：
  1. 建表 + 动作字典种子
  2. 动作字典（DB） ↔ 能力矩阵（代码）双向校验
  3. 定位字典 ↔ 引擎注册表校验
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api import ws
from app.api.v1 import api_router
from app.core.config import settings
from app.core.db import SessionLocal, engine, init_db
from app.core.errors import (
    AppError,
    app_error_handler,
    http_exception_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from app.core.logging import TraceMiddleware, setup_logging
from app.domain.locator_types import LOCATOR_TYPES
from app.engines.registry import assert_catalog_consistency, assert_locator_dict_consistency
from app.models import ActionCatalog
from app.services import execution_service, scheduler
from app.services.execution_queue import execution_queue

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.log_level)
    counts = await init_db(seed=True)

    async with SessionLocal() as session:
        rows = (await session.execute(
            select(ActionCatalog.action_key, ActionCatalog.engines))).all()
    assert_catalog_consistency([(key, list(engines or [])) for key, engines in rows])
    assert_locator_dict_consistency()

    # M3.1：启动自愈（残留 RUNNING/PENDING → ERROR），再拉起执行队列
    async with SessionLocal() as session:
        orphans = await execution_service.reconcile_orphans(session)
    if orphans:
        logger.warning("reconciled %s orphan executions", orphans, extra={
            "event": "execution.reconcile", "count": orphans})
    await execution_queue.start()
    await scheduler.start()             # M3.3：重建用例集定时任务

    logger.info("startup ok", extra={
        "event": "app.startup",
        "engines": len(__import__("app.engines.registry", fromlist=["registry"]).registry.keys),
        "actions": counts.get("actions", 0),
        "platforms": sorted(LOCATOR_TYPES),
        "concurrency": settings.max_concurrent_executions,
        "scheduled_suites": len(scheduler.jobs()),
        "version": __version__,
    })
    yield
    await scheduler.stop()
    await execution_queue.stop()
    await engine.dispose()
    logger.info("shutdown", extra={"event": "app.shutdown"})


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="多引擎 UI 自动化平台（M1 骨架 + M2 元素库）",
        lifespan=lifespan,
    )
    app.add_middleware(TraceMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["x-trace-id"],
    )
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
    app.include_router(api_router, prefix="/api/v1")
    app.include_router(ws.router)          # /ws/executions/{id}（不在 /api/v1 下）

    @app.get("/healthz", tags=["ops"])
    async def healthz():
        async with SessionLocal() as session:
            action_count = len((await session.execute(
                select(ActionCatalog.id))).all())
        from app.engines.registry import registry
        return {
            "status": "ok",
            "version": __version__,
            "env": settings.env,
            "engines": registry.describe(),
            "action_count": action_count,
            "platforms": sorted(LOCATOR_TYPES),
            "database": "sqlite" if settings.is_sqlite else "mysql",
            "scheduled_suites": len(scheduler.jobs()),
        }

    return app


app = create_app()
