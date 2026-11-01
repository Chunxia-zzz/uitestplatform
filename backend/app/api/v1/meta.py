"""元数据端点：定位类型字典 + 元素覆盖统计（M2 M1/M2）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.domain.locator_types import as_dict
from app.services import element_service

router = APIRouter(tags=["meta"])


@router.get("/locator-types")
async def locator_types():
    """三端字典：前端据此渲染下拉，并**直接过滤掉不合法的选项**。

    服务端校验是防线，前端过滤是体验 —— 两层都要有（M2 §4.7 F7）。
    """
    return {
        "platforms": as_dict(),
        "rules": [
            "locator_type 只表达语义，不含引擎前缀",
            "engine_key='*' 表示该平台下所有引擎通用",
            "引擎专属类型（如 uiautomator / predicate）必须显式指定 engine_key",
        ],
    }


@router.get("/projects/{project_id}/element-stats")
async def element_stats(project_id: int, db: AsyncSession = Depends(get_session)):
    return await element_service.stats(db, project_id)
