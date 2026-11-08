"""领域枚举 —— 全项目的取值唯一来源（D5：端只有三个）。"""
from __future__ import annotations

from enum import StrEnum


class Platform(StrEnum):
    WEB = "WEB"
    ANDROID = "ANDROID"
    IOS = "IOS"


class EngineKey(StrEnum):
    PLAYWRIGHT = "playwright"
    APPIUM = "appium"
    UIAUTOMATOR2 = "uiautomator2"


class NodeType(StrEnum):
    ELEMENT = "ELEMENT"
    FOLDER = "FOLDER"


class LocatorStatus(StrEnum):
    UNVERIFIED = "UNVERIFIED"
    VALID = "VALID"
    INVALID = "INVALID"


class VerifyVerdict(StrEnum):
    """验证器的单条判定（M2 §2.8.4）。注意 MULTIPLE 不落 INVALID。"""

    VALID = "VALID"
    MULTIPLE = "MULTIPLE"
    NONE = "NONE"
    ERROR = "ERROR"


class VerifySummary(StrEnum):
    ALL_VALID = "ALL_VALID"
    HAS_PROBLEM = "HAS_PROBLEM"
    ALL_INVALID = "ALL_INVALID"


class ExecutionStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


class StepStatus(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"


class TriggerType(StrEnum):
    MANUAL = "MANUAL"
    SCHEDULE = "SCHEDULE"
    API = "API"


class OnFailure(StrEnum):
    ABORT = "ABORT"
    CONTINUE = "CONTINUE"
    RETRY = "RETRY"


class ActionCategory(StrEnum):
    ELEMENT = "ELEMENT"
    APP_LIFECYCLE = "APP_LIFECYCLE"
    CONTEXT = "CONTEXT"
    NAVIGATION = "NAVIGATION"
    ASSERT = "ASSERT"
    DATA = "DATA"
    SYSTEM = "SYSTEM"
    #: M3.8（GAP-09）：网络 mock / 响应检索；SQLite 列为 VARCHAR 无 CHECK，
    #: 值校验在应用层；MySQL DDL（schema.sql）的 ENUM 已同步扩值。
    NETWORK = "NETWORK"


#: 端 → 可用引擎（P1 路由的合法组合；与 registry 双向校验）
PLATFORM_ENGINES: dict[str, frozenset[str]] = {
    Platform.WEB: frozenset({EngineKey.PLAYWRIGHT}),
    Platform.ANDROID: frozenset({EngineKey.APPIUM, EngineKey.UIAUTOMATOR2}),
    Platform.IOS: frozenset({EngineKey.APPIUM}),
}

MAX_TREE_DEPTH = 8
MAX_BATCH_SIZE = 500
MAX_VERIFY_LOCATORS = 20
