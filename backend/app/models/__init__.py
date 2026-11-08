"""SQLAlchemy 模型 —— 11 张表（M1 附录 A + M2 修正）。

DDL 的最终事实源是 ``backend/sql/schema.sql``；本文件是 ORM 视图，两者必须同步。
M2 修正：``element.deleted_seq``（软删唯一键）、``element_locator.probe_detail``。
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.domain.enums import (
    ActionCategory,
    ExecutionStatus,
    LocatorStatus,
    NodeType,
    OnFailure,
    Platform,
    StepStatus,
    TriggerType,
)


def enum_col(py_enum: type[StrEnum], name: str, length: int = 24):
    return sa.Enum(
        py_enum, name=name, native_enum=True, validate_strings=True,
        values_callable=lambda e: [m.value for m in e], length=length,
    )


def pk():
    """BIGINT 主键。

    ★ SQLite 只有 ``INTEGER PRIMARY KEY`` 才会自增，``BIGINT`` 不会 —— 因此用
    ``with_variant`` 在 SQLite 上退化为 INTEGER，生产 MySQL 仍是 BIGINT。
    """
    return mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True, autoincrement=True,
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now())


class SoftDeleteMixin:
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa.text("0"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)


# ────────────────────────── 1. project ──────────────────────────
class Project(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "project"

    id: Mapped[int] = pk()
    name: Mapped[str] = mapped_column(String(128))
    code: Mapped[str] = mapped_column(String(64), unique=True)
    # ★ P1 显式路由：端与引擎是两个独立字段，绝不用"用例用了什么动作"反推
    platform: Mapped[str] = mapped_column(enum_col(Platform, "platform_enum", 16))
    engine_key: Mapped[str] = mapped_column(String(64))
    target_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    description: Mapped[str | None] = mapped_column(String(512), default=None)
    default_timeout_ms: Mapped[int] = mapped_column(Integer, default=15_000)


# ────────────────────── 2. execution_target ────────────────────
class ExecutionTarget(Base, TimestampMixin, SoftDeleteMixin):
    """执行目标（M3.6 GAP-42 起支持软删：D29/D30/D31）。

    软删唯一键与 element / test_suite 同款：活记录 ``deleted_seq=0``，
    删除时置为自身 id，使同名可重建（D30）。
    """
    __tablename__ = "execution_target"

    id: Mapped[int] = pk()
    project_id: Mapped[int] = mapped_column(BigInteger, index=True)
    name: Mapped[str] = mapped_column(String(128))
    platform: Mapped[str] = mapped_column(enum_col(Platform, "platform_enum", 16))
    engine_key: Mapped[str] = mapped_column(String(64))
    base_url: Mapped[str | None] = mapped_column(String(512), default=None)
    options: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # ★ 0 = 未删；删除时置为自身 id（GAP-41 教训：唯一键必须同时进 ORM）
    deleted_seq: Mapped[int] = mapped_column(BigInteger, default=0)

    __table_args__ = (
        sa.UniqueConstraint("project_id", "name", "deleted_seq", name="uk_target_name"),
        sa.Index("idx_target_project", "project_id", "is_deleted"),
    )


# ────────────────────────── 3. element ─────────────────────────
class Element(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "element"

    id: Mapped[int] = pk()
    project_id: Mapped[int] = mapped_column(BigInteger, index=True)
    parent_id: Mapped[int] = mapped_column(BigInteger, default=0)
    path: Mapped[str] = mapped_column(String(512), default="/")
    element_name: Mapped[str] = mapped_column(String(255))
    node_type: Mapped[str] = mapped_column(
        enum_col(NodeType, "node_type_enum", 16), default=NodeType.ELEMENT)
    description: Mapped[str | None] = mapped_column(String(512), default=None)
    memo: Mapped[str | None] = mapped_column(Text, default=None)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    # ★ M2 F-M2-2：0 = 未删；删除时置为自身 id，使已删记录互不冲突
    deleted_seq: Mapped[int] = mapped_column(BigInteger, default=0)
    created_by: Mapped[int | None] = mapped_column(BigInteger, default=None)
    updated_by: Mapped[int | None] = mapped_column(BigInteger, default=None)

    # ★ 与 sql/schema.sql 对齐（GAP-33 由 Alembic autogenerate 发现缺失）：
    #   此前 ORM 没有这两组键，导致 create_all 建的开发库没有唯一约束 ——
    #   "同名元素"只靠应用层检查，并发下会漏。
    __table_args__ = (
        sa.UniqueConstraint("project_id", "parent_id", "element_name", "deleted_seq",
                            name="uk_element_name"),
        sa.Index("idx_element_project", "project_id", "is_deleted"),
        sa.Index("idx_element_path", "project_id", "path"),
        sa.Index("idx_element_name", "project_id", "element_name"),
    )


# ─────────────────── 4. element_locator（P2 核心）─────────────
class ElementLocator(Base, TimestampMixin):
    __tablename__ = "element_locator"

    id: Mapped[int] = pk()
    element_id: Mapped[int] = mapped_column(BigInteger, index=True)
    # ★ 二维定位：platform（业务端） × engine_key（技术引擎），'*' = 该端所有引擎通用
    platform: Mapped[str] = mapped_column(enum_col(Platform, "platform_enum", 16))
    engine_key: Mapped[str] = mapped_column(String(64), default="*")
    locator_type: Mapped[str] = mapped_column(String(32))
    locator_value: Mapped[str] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    status: Mapped[str] = mapped_column(
        enum_col(LocatorStatus, "locator_status_enum", 16), default=LocatorStatus.UNVERIFIED)
    # ★ M2 新增：最近一次验证详情（UI 展示用，不参与解析）
    probe_detail: Mapped[dict | None] = mapped_column(JSON, default=None)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    remark: Mapped[str | None] = mapped_column(String(255), default=None)

    __table_args__ = (
        sa.UniqueConstraint("element_id", "platform", "engine_key", "locator_type",
                            "locator_value", name="uk_locator"),
        sa.Index("idx_locator_lookup", "element_id", "platform", "engine_key",
                 "enabled", "priority"),
    )


# ───────────────────── 5. action_catalog ───────────────────────
class ActionCatalog(Base):
    __tablename__ = "action_catalog"

    id: Mapped[int] = pk()
    action_key: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(enum_col(ActionCategory, "action_category_enum", 24))
    platforms: Mapped[list] = mapped_column(JSON)
    engines: Mapped[list] = mapped_column(JSON)
    params_schema: Mapped[dict] = mapped_column(JSON)
    requires_element: Mapped[bool] = mapped_column(Boolean, default=False)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


# ────────────────────────── 6. test_case ───────────────────────
class TestCase(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "test_case"
    #: 防止 pytest 把 ORM 类当测试类收集
    __test__ = False

    id: Mapped[int] = pk()
    project_id: Mapped[int] = mapped_column(BigInteger, index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(1024), default=None)
    state: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger, default=None)
    updated_by: Mapped[int | None] = mapped_column(BigInteger, default=None)
    # 注：无 project_type —— 端类型统一从 project 继承（P1）


# ────────────────────────── 7. test_step ───────────────────────
class TestStep(Base, TimestampMixin):
    __tablename__ = "test_step"
    #: 名字以 Test 开头，pytest 会尝试收集它（PytestCollectionWarning）
    __test__ = False

    id: Mapped[int] = pk()
    case_id: Mapped[int] = mapped_column(BigInteger, index=True)
    seq: Mapped[int] = mapped_column(Integer)
    action_key: Mapped[str] = mapped_column(String(64))
    element_id: Mapped[int | None] = mapped_column(BigInteger, default=None, index=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    output_var: Mapped[str | None] = mapped_column(String(64), default=None)
    assert_expr: Mapped[dict | None] = mapped_column(JSON, default=None)
    timeout_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    on_failure: Mapped[str] = mapped_column(
        enum_col(OnFailure, "on_failure_enum", 16), default=OnFailure.ABORT)
    retry_times: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    remark: Mapped[str | None] = mapped_column(String(255), default=None)

    __table_args__ = (sa.UniqueConstraint("case_id", "seq", name="uk_step_seq"),)


# ───────────────────── 8. test_suite / 8.1 成员 ─────────────────
class TestSuite(Base, TimestampMixin, SoftDeleteMixin):
    """用例集：项目 → 用例集 → 用例 → 元素+动作 的第三层。

    用例集是**执行单元**：单次手动运行或按 cron 定时运行，产出报告。
    """
    __tablename__ = "test_suite"
    __test__ = False

    id: Mapped[int] = pk()
    project_id: Mapped[int] = mapped_column(BigInteger, index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(String(512), default=None)
    #: 5 段 cron（分 时 日 月 周）；空表示只手动运行
    schedule_cron: Mapped[str | None] = mapped_column(String(64), default=None)
    schedule_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    deleted_seq: Mapped[int] = mapped_column(BigInteger, default=0)
    created_by: Mapped[int | None] = mapped_column(BigInteger, default=None)

    __table_args__ = (
        sa.UniqueConstraint("project_id", "name", "deleted_seq", name="uk_suite_name"),
    )


class TestSuiteCase(Base):
    __tablename__ = "test_suite_case"

    id: Mapped[int] = pk()
    suite_id: Mapped[int] = mapped_column(BigInteger, index=True)
    case_id: Mapped[int] = mapped_column(BigInteger, index=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        sa.UniqueConstraint("suite_id", "case_id", name="uk_suite_case"),
    )


# ────────────────────────── 9. execution ───────────────────────
class Execution(Base):
    __tablename__ = "execution"

    id: Mapped[int] = pk()
    project_id: Mapped[int] = mapped_column(BigInteger, index=True)
    target_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    #: M3.3：由用例集触发时记录来源（快照 name，改名不影响历史）
    suite_id: Mapped[int | None] = mapped_column(BigInteger, default=None, index=True)
    suite_name: Mapped[str | None] = mapped_column(String(128), default=None)
    trigger_type: Mapped[str] = mapped_column(
        enum_col(TriggerType, "trigger_type_enum", 16), default=TriggerType.MANUAL)
    case_ids: Mapped[list] = mapped_column(JSON)
    engine_key: Mapped[str] = mapped_column(String(64))
    platform: Mapped[str] = mapped_column(enum_col(Platform, "platform_enum", 16))
    status: Mapped[str] = mapped_column(
        enum_col(ExecutionStatus, "execution_status_enum", 16), default=ExecutionStatus.PENDING)
    total: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    errored: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, default=None)
    #: M3.1：终态原因（进程重启中断 / 用户取消 / 队列满）
    message: Mapped[str | None] = mapped_column(String(512), default=None)
    created_by: Mapped[int | None] = mapped_column(BigInteger, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ─────────────── 9. execution_step_result（定位稳定性埋点）──────
class ExecutionStepResult(Base):
    __tablename__ = "execution_step_result"

    id: Mapped[int] = pk()
    execution_id: Mapped[int] = mapped_column(BigInteger, index=True)
    case_id: Mapped[int] = mapped_column(BigInteger)
    step_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    seq: Mapped[int] = mapped_column(Integer)
    action_key: Mapped[str] = mapped_column(String(64))
    element_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    status: Mapped[str] = mapped_column(enum_col(StepStatus, "step_status_enum", 16))
    #: M3.1：第几次尝试（重试每次一行，便于看到"第一次为什么失败"）
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    duration_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    message: Mapped[str | None] = mapped_column(Text, default=None)
    # ★ 让"哪条定位符最稳"成为可统计事实（二期自愈的数据基础）
    used_locator_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    fallback_index: Mapped[int | None] = mapped_column(Integer, default=None)
    # 二期 WebView 预留：M1 起就要写入，保证历史数据格式一致
    active_platform: Mapped[str | None] = mapped_column(String(16), default=None)
    active_engine: Mapped[str | None] = mapped_column(String(64), default=None)
    screenshot_artifact_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ─────────────────────────── 10. report ────────────────────────
class Report(Base):
    __tablename__ = "report"

    id: Mapped[int] = pk()
    execution_id: Mapped[int] = mapped_column(BigInteger, index=True)
    format: Mapped[str] = mapped_column(String(16), default="HTML")
    path: Mapped[str | None] = mapped_column(String(512), default=None)
    summary: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # ★ GAP-35：一次执行每种格式只应有一份报告。此前靠"先删后插"保幂等，
    #   并发生成会短暂出现重复行（两个请求都插成功）。加唯一键后由 DB 兜底。
    __table_args__ = (
        sa.UniqueConstraint("execution_id", "format", name="uk_report_execution_format"),
    )


# ────────────────────────── 11. artifact ───────────────────────
class Artifact(Base):
    __tablename__ = "artifact"

    id: Mapped[int] = pk()
    execution_id: Mapped[int | None] = mapped_column(BigInteger, index=True, default=None)
    step_result_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    kind: Mapped[str] = mapped_column(String(32), default="SCREENSHOT")
    storage: Mapped[str] = mapped_column(String(16), default="LOCAL")
    path: Mapped[str] = mapped_column(String(512))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


__all__ = [
    "ActionCatalog", "Artifact", "Element", "ElementLocator", "Execution",
    "ExecutionStepResult", "ExecutionTarget", "Project", "Report", "TestCase", "TestStep",
    "TestSuite", "TestSuiteCase",
]
