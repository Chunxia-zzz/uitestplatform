"""请求体模型（写入期校验的第一道门）。"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

NodeTypeLiteral = Literal["ELEMENT", "FOLDER"]
PlatformLiteral = Literal["WEB", "ANDROID", "IOS"]


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    platform: PlatformLiteral
    engine_key: str = Field(min_length=1, max_length=64)
    target_id: int | None = None
    description: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    platform: PlatformLiteral | None = None
    engine_key: str | None = None
    target_id: int | None = None
    description: str | None = None
    default_timeout_ms: int | None = Field(default=None, ge=1000, le=300_000)


class TargetCreate(BaseModel):
    """创建执行目标（M3.6 GAP-42）。路由合法性由 target_service 用 registry 校验。"""
    name: str = Field(min_length=1, max_length=128)
    platform: PlatformLiteral
    engine_key: str = Field(min_length=1, max_length=64)
    base_url: str | None = Field(default=None, max_length=512)
    options: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        return v.strip()


class TargetUpdate(BaseModel):
    """部分更新执行目标（exclude_unset 语义，与 ProjectUpdate 同款）。"""
    name: str | None = Field(default=None, min_length=1, max_length=128)
    platform: PlatformLiteral | None = None
    engine_key: str | None = None
    base_url: str | None = Field(default=None, max_length=512)
    options: dict[str, Any] | None = None
    enabled: bool | None = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str | None) -> str | None:
        return v.strip() if v else v


class ElementCreate(BaseModel):
    parent_id: int = 0
    element_name: str = Field(min_length=1, max_length=255)
    node_type: NodeTypeLiteral = "ELEMENT"
    description: str | None = Field(default=None, max_length=512)
    memo: str | None = None

    @field_validator("element_name")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class ElementUpdate(BaseModel):
    element_name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=512)
    memo: str | None = None
    node_type: NodeTypeLiteral | None = None


class ElementMove(BaseModel):
    parent_id: int = 0
    index: int | None = Field(default=None, ge=0)


class OrderUpdate(BaseModel):
    ordered_ids: list[int] = Field(min_length=0)


class LocatorCreate(BaseModel):
    platform: PlatformLiteral
    engine_key: str = "*"
    locator_type: str = Field(min_length=1, max_length=32)
    locator_value: str = Field(min_length=1)
    priority: int | None = Field(default=None, ge=1, le=99_999)


class LocatorBulkCreate(BaseModel):
    bulk: Literal[True] = True
    items: list[LocatorCreate] = Field(min_length=1, max_length=50)


class LocatorUpdate(BaseModel):
    locator_value: str | None = Field(default=None, min_length=1)
    enabled: bool | None = None
    remark: str | None = Field(default=None, max_length=255)


class LocatorOrder(BaseModel):
    platform: PlatformLiteral
    engine_key: str = "*"
    ordered_ids: list[int]


class LocatorDraft(BaseModel):
    locator_type: str = Field(min_length=1, max_length=32)
    locator_value: str = Field(min_length=1)


class VerifyRequest(BaseModel):
    platform: PlatformLiteral
    engine_key: str = "*"
    target_id: int | None = None
    url: str | None = None
    include_saved: bool = True
    drafts: list[LocatorDraft] = Field(default_factory=list, max_length=20)


class ExecutionCreate(BaseModel):
    project_id: int
    #: 二选一：给 suite_id 表示"跑整个用例集"，否则按 case_ids 临时执行
    case_ids: list[int] = Field(default_factory=list, max_length=100)
    suite_id: int | None = None
    target_id: int | None = None

    @model_validator(mode="after")
    def _need_target(self):
        if not self.suite_id and not self.case_ids:
            raise ValueError("必须提供 suite_id 或 case_ids")
        return self


# ─────────────────────────── 用例集（M3.3）──────────────────────
class SuiteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=512)
    schedule_cron: str | None = Field(default=None, max_length=64,
                                      description="5 段 cron；空表示只手动运行")
    schedule_enabled: bool = False

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        return v.strip()


class SuiteUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=512)
    schedule_cron: str | None = None
    schedule_enabled: bool | None = None


class SuiteCasesAdd(BaseModel):
    case_ids: list[int] = Field(min_length=1, max_length=200)


class SuiteCaseOrder(BaseModel):
    ordered_case_ids: list[int]


class CaseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None


class StepCreate(BaseModel):
    #: 缺省时自动追加到末尾（M3.2 StepEditor：前端不必自己算 seq）
    seq: int | None = Field(default=None, ge=1)
    action_key: str
    element_id: int | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    output_var: str | None = None
    timeout_ms: int | None = None
    on_failure: Literal["ABORT", "CONTINUE", "RETRY"] = "ABORT"
    retry_times: int = Field(default=0, ge=0, le=5)
    enabled: bool = True
    remark: str | None = None


class CaseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None


class StepUpdate(BaseModel):
    """PATCH 语义：只改传了的字段。

    用 ``model_dump(exclude_unset=True)`` 判断"没传"与"显式传 null"的区别 ——
    否则永远无法把 ``element_id`` 从有改成无。
    """
    seq: int | None = Field(default=None, ge=1)
    action_key: str | None = None
    element_id: int | None = None
    params: dict[str, Any] | None = None
    output_var: str | None = None
    timeout_ms: int | None = None
    on_failure: Literal["ABORT", "CONTINUE", "RETRY"] | None = None
    retry_times: int | None = Field(default=None, ge=0, le=5)
    enabled: bool | None = None
    remark: str | None = None


class StepOrder(BaseModel):
    ordered_ids: list[int] = Field(min_length=1)


class SuiteCaseToggle(BaseModel):
    """GAP-38：只切成员启用状态，不动排序。"""
    enabled: bool
