"""页面扫描端点（M3.5）。

两个端点：
* ``POST /element-scan`` —— 只读探测，返回候选（不落库）；
* ``POST /element-scan/import`` —— 人工确认后批量落库。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.schemas.scan import ScanImportRequest, ScanRequest
from app.services import scan_service

router = APIRouter(tags=["scan"])


@router.post("/projects/{project_id}/element-scan")
async def scan_page(project_id: int, body: ScanRequest,
                    db: AsyncSession = Depends(get_session)):
    """扫描页面元素，返回候选清单（强/中/弱分级），**不写入数据库**。"""
    return await scan_service.scan(db, project_id, body)


@router.post("/projects/{project_id}/element-scan/import")
async def import_scan(project_id: int, body: ScanImportRequest,
                      db: AsyncSession = Depends(get_session)):
    """把用户确认的候选写入元素库。部分失败不中断，逐条报告。"""
    return await scan_service.import_candidates(db, project_id, body)
