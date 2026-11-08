"""统一错误体系。

约定（M1 FR10/FR11、M2 §3.2）：
* 响应体：``{"error": {"code", "message", "detail", "trace_id"}}``
* 错误码命名：``<域>_<语义>``，域 = **资源名**（ELEMENT / ELEMENT_LOCATOR / LOCATOR_VERIFY …），
  不是操作名。所以 ``ELEMENT_LOCATOR_TYPE_INVALID`` 的域是「元素定位符」。
"""
from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    code: str = "INTERNAL_ERROR"
    http_status: int = 500
    message: str = "服务内部错误"

    def __init__(self, message: str | None = None, detail: dict[str, Any] | None = None):
        self.message = message or self.message
        self.detail = detail or {}
        super().__init__(self.message)

    def to_body(self, trace_id: str = "") -> dict[str, Any]:
        return {"error": {
            "code": self.code,
            "message": self.message,
            "detail": self.detail,
            "trace_id": trace_id,
        }}


# ─────────────────────────── 通用 ───────────────────────────
class ValidationFailed(AppError):
    code, http_status, message = "VALIDATION_ERROR", 422, "参数校验失败"


class BatchLimitExceeded(AppError):
    code, http_status, message = "BATCH_LIMIT_EXCEEDED", 422, "批量数量超限"


class ProjectNotFound(AppError):
    code, http_status, message = "PROJECT_NOT_FOUND", 404, "项目不存在"


class ProjectPlatformEngineMismatch(AppError):
    code, http_status, message = "PROJECT_PLATFORM_ENGINE_MISMATCH", 422, "端与引擎不匹配"


class EngineNotFound(AppError):
    code, http_status, message = "ENGINE_NOT_FOUND", 404, "引擎未注册"


# ─────────────────────────── 元素 ───────────────────────────
class ElementNotFound(AppError):
    code, http_status, message = "ELEMENT_NOT_FOUND", 404, "元素不存在"


class ElementParentNotFound(AppError):
    code, http_status, message = "ELEMENT_PARENT_NOT_FOUND", 422, "父节点不存在"


class ElementParentMustBeFolder(AppError):
    code, http_status, message = "ELEMENT_PARENT_MUST_BE_FOLDER", 422, "父节点必须是目录"


class ElementDepthExceeded(AppError):
    code, http_status, message = "ELEMENT_DEPTH_EXCEEDED", 422, "元素层级超过上限"


class ElementMoveIntoDescendant(AppError):
    code, http_status, message = "ELEMENT_MOVE_INTO_DESCENDANT", 422, "不能移动到自身或子树下"


class ElementNameDuplicated(AppError):
    code, http_status, message = "ELEMENT_NAME_DUPLICATED", 409, "同级已存在同名节点"


class ElementReferenced(AppError):
    code, http_status, message = "ELEMENT_REFERENCED", 409, "元素被用例引用，无法删除"


class ElementFolderNotEmpty(AppError):
    code, http_status, message = "ELEMENT_FOLDER_NOT_EMPTY", 409, "目录下还有子节点"


class ElementFolderHasNoLocator(AppError):
    code, http_status, message = "ELEMENT_FOLDER_HAS_NO_LOCATOR", 422, "目录不能配置定位符"


class ElementNodeTypeConflict(AppError):
    code, http_status, message = "ELEMENT_NODE_TYPE_CONFLICT", 409, "节点类型变更与现有数据冲突"


class ElementOrderIncomplete(AppError):
    code, http_status, message = "ELEMENT_ORDER_INCOMPLETE", 422, "排序提交的 id 集合与现有不一致"


# ──────────────────────── 元素定位符 ────────────────────────
class ElementLocatorNotFound(AppError):
    code, http_status, message = "ELEMENT_LOCATOR_NOT_FOUND", 404, "定位符不存在"


class ElementLocatorTypeInvalid(AppError):
    code, http_status, message = "ELEMENT_LOCATOR_TYPE_INVALID", 422, "定位类型不属于该平台"


class ElementLocatorTypeEngineUnsupported(AppError):
    code, http_status, message = (
        "ELEMENT_LOCATOR_TYPE_ENGINE_UNSUPPORTED", 422, "该引擎不支持此定位类型")


class ElementLocatorWildcardUnscoped(AppError):
    code, http_status, message = (
        "ELEMENT_LOCATOR_WILDCARD_UNSCOPED", 422, "引擎专属定位类型不能用于通配 '*'")


class ElementLocatorDuplicated(AppError):
    code, http_status, message = "ELEMENT_LOCATOR_DUPLICATED", 409, "定位符已存在"


# ────────────────────────── 验证器 ──────────────────────────
class LocatorVerifyTargetRequired(AppError):
    code, http_status, message = "LOCATOR_VERIFY_TARGET_REQUIRED", 422, "必须提供 target_id 或 url"


class LocatorVerifyTimeout(AppError):
    code, http_status, message = "LOCATOR_VERIFY_TIMEOUT", 504, "定位符验证超时"


# ────────────────────────── 执行 ──────────────────────────
class CaseNotFound(AppError):
    code, http_status, message = "CASE_NOT_FOUND", 404, "用例不存在"


class StepNotFound(AppError):
    code, http_status, message = "STEP_NOT_FOUND", 404, "步骤不存在"


class StepSeqDuplicated(AppError):
    code, http_status, message = "STEP_SEQ_DUPLICATED", 409, "用例内步骤序号重复"


# ────────────────────────── 执行（M3）──────────────────────────
class ExecutionNotFound(AppError):
    code, http_status, message = "EXECUTION_NOT_FOUND", 404, "执行不存在"


class ExecutionCannotCancel(AppError):
    code, http_status, message = "EXECUTION_CANNOT_CANCEL", 409, "该执行已结束，无法取消"


class ReportNotReady(AppError):
    code, http_status, message = "REPORT_NOT_READY", 409, "报告尚未生成"


class QueueFull(AppError):
    code, http_status, message = "QUEUE_FULL", 429, "执行队列已满，请稍后重试"


# ────────────────────────── 用例集（M3.3）──────────────────────
class SuiteNotFound(AppError):
    code, http_status, message = "SUITE_NOT_FOUND", 404, "用例集不存在"


class SuiteNameDuplicated(AppError):
    code, http_status, message = "SUITE_NAME_DUPLICATED", 409, "项目内已存在同名用例集"


class SuiteEmpty(AppError):
    code, http_status, message = "SUITE_EMPTY", 422, "用例集没有可执行的用例"


class SuiteCronInvalid(AppError):
    code, http_status, message = "SUITE_CRON_INVALID", 422, "cron 表达式不合法"


# ────────────────────────── 产物（M3.2）──────────────────────
class ArtifactNotFound(AppError):
    code, http_status, message = "ARTIFACT_NOT_FOUND", 404, "产物不存在"


class ArtifactPathForbidden(AppError):
    code, http_status, message = "ARTIFACT_PATH_FORBIDDEN", 403, "产物路径不在允许目录内"


class SuiteMemberNotFound(AppError):
    code, http_status, message = "SUITE_MEMBER_NOT_FOUND", 404, "用例不在该用例集中"


# ────────────────────────── 一键接入（M3.4）──────────────────────
class ScaffoldInvalidUrl(AppError):
    code, http_status, message = "SCAFFOLD_INVALID_URL", 422, "url 必须是 http/https 绝对地址"


class ScaffoldEmptyActions(AppError):
    code, http_status, message = "SCAFFOLD_EMPTY_ACTIONS", 422, "actions 不能为空"


class ScaffoldUnknownElementKey(AppError):
    code, http_status, message = "SCAFFOLD_UNKNOWN_ELEMENT_KEY", 422, "动作引用了未声明的元素 key"


class ScaffoldElementWithoutLocator(AppError):
    code, http_status, message = "SCAFFOLD_ELEMENT_WITHOUT_LOCATOR", 422, "元素至少需要一条定位符"


class ScaffoldElementRequired(AppError):
    code, http_status, message = "SCAFFOLD_ELEMENT_REQUIRED", 422, "该动作需要绑定元素"


class ScaffoldElementUnexpected(AppError):
    code, http_status, message = "SCAFFOLD_ELEMENT_UNEXPECTED", 422, "该动作不应绑定元素"


class ScaffoldProjectConflict(AppError):
    code, http_status, message = "SCAFFOLD_PROJECT_CONFLICT", 409, "项目 code 已存在但端/引擎不一致"


# ────────────────────────── 页面扫描（M3.5）──────────────────────
class ScanTargetRequired(AppError):
    code, http_status, message = "SCAN_TARGET_REQUIRED", 422, "既未提供 url，项目也没有默认执行目标"


class ScanEmptyCandidates(AppError):
    code, http_status, message = (
        "SCAN_EMPTY_CANDIDATES", 422,
        "扫描结果为空（页面不可访问或无可见元素）")


class ScanImportEmpty(AppError):
    code, http_status, message = "SCAN_IMPORT_EMPTY", 422, "导入的候选清单不能为空"


class UnsupportedActionError(AppError):
    code, http_status, message = "UNSUPPORTED_ACTION", 422, "该引擎不支持此动作"


class LocatorNotFoundError(AppError):
    code, http_status, message = "LOCATOR_NOT_FOUND", 422, "元素在目标端下没有可用定位符"


# ─────────────────────── 执行目标（M3.6 GAP-42）──────────────────────
class TargetNotFound(AppError):
    code, http_status, message = "TARGET_NOT_FOUND", 404, "执行目标不存在"


class TargetNameDuplicated(AppError):
    code, http_status, message = "TARGET_NAME_DUPLICATED", 409, "项目内已存在同名执行目标"


# ─────────────────────── 通知（M3.6 GAP-20）──────────────────────
class NotifyNotConfigured(AppError):
    code, http_status, message = (
        "NOTIFY_NOT_CONFIGURED", 422,
        "当前通知渠道未配置 webhook（检查 UIP_NOTIFY_CHANNEL 与对应 webhook）")


class NotifySendFailed(AppError):
    code, http_status, message = "NOTIFY_SEND_FAILED", 502, "通知发送失败"


ERROR_CODES: dict[str, tuple[int, str]] = {
    cls.code: (cls.http_status, cls.message)
    for cls in (
        ValidationFailed, BatchLimitExceeded, ProjectNotFound, ProjectPlatformEngineMismatch,
        EngineNotFound, ElementNotFound, ElementParentNotFound, ElementParentMustBeFolder,
        ElementDepthExceeded, ElementMoveIntoDescendant, ElementNameDuplicated,
        ElementReferenced, ElementFolderNotEmpty, ElementFolderHasNoLocator,
        ElementNodeTypeConflict, ElementOrderIncomplete, ElementLocatorNotFound,
        ElementLocatorTypeInvalid, ElementLocatorTypeEngineUnsupported,
        ElementLocatorWildcardUnscoped, ElementLocatorDuplicated,
        LocatorVerifyTargetRequired, LocatorVerifyTimeout, CaseNotFound,
        UnsupportedActionError, LocatorNotFoundError,
        ExecutionNotFound, ExecutionCannotCancel, ReportNotReady, QueueFull,
        SuiteNotFound, SuiteNameDuplicated, SuiteEmpty, SuiteCronInvalid,
        ArtifactNotFound, ArtifactPathForbidden, SuiteMemberNotFound,
        StepNotFound, StepSeqDuplicated,
        ScaffoldInvalidUrl, ScaffoldEmptyActions, ScaffoldUnknownElementKey,
        ScaffoldElementWithoutLocator, ScaffoldElementRequired,
        ScaffoldElementUnexpected, ScaffoldProjectConflict,
        ScanTargetRequired, ScanEmptyCandidates, ScanImportEmpty,
        TargetNotFound, TargetNameDuplicated,
        NotifyNotConfigured, NotifySendFailed,
    )
}


# ─────────────────────── FastAPI 装配 ───────────────────────
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    trace_id = getattr(request.state, "trace_id", "")
    return JSONResponse(status_code=exc.http_status, content=exc.to_body(trace_id),
                        headers={"x-trace-id": trace_id} if trace_id else None)


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    trace_id = getattr(request.state, "trace_id", "")
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "服务内部错误",
                           "detail": {"type": type(exc).__name__}, "trace_id": trace_id}},
        headers={"x-trace-id": trace_id} if trace_id else None,
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Pydantic 请求校验失败也必须走统一信封（FR10）。

    默认 FastAPI 返回 ``{"detail": [...]}``，前端拦截器拿不到 ``error.code``，
    只能显示 "Request failed with status code 422" —— 等于把可读信息丢了。
    """
    trace_id = getattr(request.state, "trace_id", "")
    return JSONResponse(
        status_code=422,
        content={"error": {
            "code": "VALIDATION_ERROR",
            "message": "参数校验失败",
            "detail": {"errors": jsonable_encoder(exc.errors())[:10]},
            "trace_id": trace_id,
        }},
        headers={"x-trace-id": trace_id} if trace_id else None,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """框架层 HTTPException（如 404 路由不存在）同样包进统一信封。"""
    trace_id = getattr(request.state, "trace_id", "")
    code = "NOT_FOUND" if exc.status_code == 404 else (
        "METHOD_NOT_ALLOWED" if exc.status_code == 405 else "HTTP_ERROR")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": str(exc.detail),
                           "detail": {}, "trace_id": trace_id}},
        headers={"x-trace-id": trace_id} if trace_id else None,
    )
