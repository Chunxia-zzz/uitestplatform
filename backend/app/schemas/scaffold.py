"""一键接入（M3.4）的请求模型。

设计取向：**API 只认一种规范化形态**（elements + actions 用 key 引用），
不在这里兼容"动作内联元素"的便捷写法 —— 那是前端提交前做的转换。
一种写法的好处是校验只有一套、错误信息只有一种。
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ScaffoldProject(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    #: 幂等键：同一 code 重复接入会复用（除非端/引擎不一致）
    code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    platform: Literal["WEB", "ANDROID", "IOS"] = "WEB"
    engine_key: str = "playwright"
    description: str | None = None


class ScaffoldTarget(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    #: 透传给 SessionConfig.options（viewport / device / storage_state …）
    options: dict[str, Any] = Field(default_factory=dict)


class ScaffoldLocator(BaseModel):
    locator_type: str = Field(min_length=1, max_length=32)
    locator_value: str = Field(min_length=1)


class ScaffoldElement(BaseModel):
    #: 只在本次请求内有效，用于 action 引用，不落库
    key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    #: 至少一条 —— D14 不做拾取，没有"自动猜定位符"的兜底
    locators: list[ScaffoldLocator] = Field(min_length=1)


class ScaffoldAction(BaseModel):
    action_key: str = Field(min_length=1, max_length=64)
    element_key: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    output_var: str | None = None
    timeout_ms: int | None = Field(default=None, ge=1, le=600_000)
    on_failure: Literal["ABORT", "CONTINUE", "RETRY"] = "ABORT"
    retry_times: int = Field(default=0, ge=0, le=5)


class ScaffoldCase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    #: reuse：同名用例已存在则复用且不重复加步骤；recreate：软删后重建
    strategy: Literal["reuse", "recreate"] = "reuse"


class ScaffoldSuite(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None


class ScaffoldRequest(BaseModel):
    project: ScaffoldProject
    #: 绝对地址；用于推导 target.base_url（scheme://host[:port]）
    url: str = Field(min_length=1, max_length=2048)
    target: ScaffoldTarget | None = None
    elements: list[ScaffoldElement] = Field(default_factory=list)
    actions: list[ScaffoldAction] = Field(min_length=1)
    case: ScaffoldCase
    suite: ScaffoldSuite
    run: bool = True
