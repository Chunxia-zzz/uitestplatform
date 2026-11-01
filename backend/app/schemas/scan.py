"""页面扫描（M3.5）的请求/响应模型。

扫描 = 只读探测（不落库）；导入 = 人工确认后的写库。二者是两个端点。
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

SCAN_INCLUDES = ("text", "image", "link", "form", "button", "other")


class ScanRequest(BaseModel):
    #: 缺省用项目默认执行目标的 base_url
    url: str | None = Field(default=None, max_length=2048)
    max_elements: int = Field(default=200, ge=1, le=500)
    include: list[str] = Field(default_factory=lambda: list(SCAN_INCLUDES))


class ScanImportLocator(BaseModel):
    locator_type: str = Field(min_length=1, max_length=32)
    locator_value: str = Field(min_length=1)


class ScanImportCandidate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    locators: list[ScanImportLocator] = Field(min_length=1, max_length=50)


class ScanImportRequest(BaseModel):
    candidates: list[ScanImportCandidate] = Field(min_length=1, max_length=200)
