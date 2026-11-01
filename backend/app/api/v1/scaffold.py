"""一键接入端点（M3.4）。

一个请求完成：建项目 → 建执行目标 → 建元素与定位符 → 建用例与步骤 →
建用例集 → 触发执行。步骤顺序与依赖见 D2-M3.4 §1。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.schemas.scaffold import ScaffoldRequest
from app.services import scaffold_service

router = APIRouter(tags=["scaffold"])


@router.post("/scaffold")
async def scaffold(body: ScaffoldRequest, db: AsyncSession = Depends(get_session)):
    """返回 200 + 完整 id 链；`run=true` 时 `execution` 为 202 语义的入队结果。"""
    return await scaffold_service.run(db, body)
