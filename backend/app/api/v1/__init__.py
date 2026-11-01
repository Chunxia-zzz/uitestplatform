"""v1 路由聚合。"""
from fastapi import APIRouter

from app.api.v1 import (
    cases, elements, engines, executions, locators, meta, notifications, projects,
    scaffold, scan, suites, targets,
)

api_router = APIRouter()
for module in (projects, engines, elements, locators, cases, suites, executions,
               scaffold, scan, meta, targets, notifications):
    api_router.include_router(module.router)

__all__ = ["api_router"]
