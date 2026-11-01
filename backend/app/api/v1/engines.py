"""引擎与动作字典端点（前端下拉数据源）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.domain.capabilities import CAPABILITY_MATRIX
from app.engines.registry import registry
from app.models import ActionCatalog

router = APIRouter(tags=["engines"])


@router.get("/engines")
async def list_engines():
    return {"items": registry.describe(), "total": len(registry.keys)}


@router.get("/engines/{engine_key}/capabilities")
async def engine_capabilities(engine_key: str):
    meta = registry.meta(engine_key)          # 未注册 → ENGINE_NOT_FOUND
    return {
        "engine_key": meta.key,
        "label": meta.label,
        "platforms": sorted(meta.platforms),
        "implemented": meta.implemented,
        "actions": sorted(CAPABILITY_MATRIX.get(engine_key, frozenset())),
        "action_count": len(CAPABILITY_MATRIX.get(engine_key, frozenset())),
    }


@router.get("/actions")
async def list_actions(engine_key: str | None = None,
                       db: AsyncSession = Depends(get_session)):
    rows = list((await db.execute(
        select(ActionCatalog).order_by(ActionCatalog.sort))).scalars().all())
    items = [
        {
            "action_key": a.action_key, "name": a.name, "category": str(a.category),
            "platforms": a.platforms, "engines": a.engines,
            "params_schema": a.params_schema, "requires_element": bool(a.requires_element),
            "sort": a.sort, "enabled": bool(a.enabled),
        }
        for a in rows
    ]
    if engine_key:
        items = [i for i in items if engine_key in (i["engines"] or [])]
    return {"items": items, "total": len(items)}
