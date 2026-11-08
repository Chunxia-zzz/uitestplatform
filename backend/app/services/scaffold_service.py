"""一键接入（M3.4）：URL + 动作清单 → 项目 / 元素 / 用例 / 用例集 / 执行。

七步严格串行（S1→S7），因为后一步的输入是前一步的产物（外键语义决定）。

两段式保证"失败不留垃圾"：
1. **S0 全量静态校验**（写库前）—— 动作、参数、元素引用、定位类型全部先验一遍；
2. **补偿删除** —— 只兜"写库中途异常"。逆序软删本次新建的对象，复用的绝不碰。

诚实边界：补偿不是数据库级原子性（底层各服务各自 commit，签名已冻结）。
API 视角无残留，极端情况下 DB 里可能有孤儿行。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    AppError,
    ScaffoldElementRequired,
    ScaffoldElementUnexpected,
    ScaffoldElementWithoutLocator,
    ScaffoldEmptyActions,
    ScaffoldInvalidUrl,
    ScaffoldProjectConflict,
    ScaffoldUnknownElementKey,
    ValidationFailed,
)
from app.engines.registry import registry
from app.models import Element, ExecutionTarget, Project, TestCase, TestSuite, TestSuiteCase
from app.schemas.scaffold import ScaffoldRequest
from app.services import (
    case_service,
    element_service,
    locator_service,
    project_service,
    suite_service,
)

logger = logging.getLogger(__name__)


# ─────────────────────────── 数据结构 ───────────────────────────
@dataclass
class _Action:
    seq: int
    action_key: str
    element_key: str | None
    params: dict
    output_var: str | None
    timeout_ms: int | None
    on_failure: str
    retry_times: int


@dataclass
class _Tracker:
    """按创建顺序记录，补偿时逆序删。只记**本次新建**的对象。"""
    entries: list[tuple[str, int]] = field(default_factory=list)

    def add(self, kind: str, object_id: int) -> None:
        self.entries.append((kind, object_id))


def _origin(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ScaffoldInvalidUrl(
            f"url 必须是 http/https 绝对地址：{url}", {"url": url})
    return f"{parsed.scheme}://{parsed.netloc}", parsed.netloc


# ─────────────────────────── S0 规范化 ───────────────────────────
def normalize(spec: ScaffoldRequest) -> tuple[str, list[_Action], list[str]]:
    """写库前的全部校验。返回 (base_url, actions, warnings)。"""
    base_url, _ = _origin(spec.url)

    if not spec.actions:
        raise ScaffoldEmptyActions("actions 不能为空", {})

    # 路由本身必须合法（端/引擎组合存在）；"本批次只支持 WEB" 放到 _precheck_project，
    # 这样"项目 code 已存在但端不一致"能报更准确的 409，而不是笼统的 422。
    registry.validate_route(spec.project.platform, spec.project.engine_key)

    # 元素：key 唯一、name 唯一、至少一条定位符
    # （定位类型校验依赖 platform，放到项目判定之后 —— 否则"端冲突"会被
    #  一个不相干的定位类型错误抢先报出来）
    seen_keys: set[str] = set()
    seen_names: set[str] = set()
    for element in spec.elements:
        if element.key in seen_keys:
            raise ValidationFailed(f"元素 key 重复：{element.key}", {"key": element.key})
        seen_keys.add(element.key)
        if element.name in seen_names:
            raise ValidationFailed(f"元素名称重复：{element.name}", {"name": element.name})
        seen_names.add(element.name)
        if not element.locators:
            raise ScaffoldElementWithoutLocator(
                f"元素「{element.name}」至少需要一条定位符", {"element": element.name})

    warnings: list[str] = []
    actions: list[_Action] = []
    for index, action in enumerate(spec.actions, start=1):
        needs = case_service.element_requirement(action.action_key, action.params)
        if needs and not action.element_key:
            raise ScaffoldElementRequired(
                f"第 {index} 条动作 {action.action_key} 需要绑定元素",
                {"seq": index, "action_key": action.action_key})
        if not needs and action.element_key:
            raise ScaffoldElementUnexpected(
                f"第 {index} 条动作 {action.action_key} 不应绑定元素",
                {"seq": index, "action_key": action.action_key,
                 "element_key": action.element_key})
        if action.element_key and action.element_key not in seen_keys:
            raise ScaffoldUnknownElementKey(
                f"第 {index} 条动作引用了未声明的元素 key：{action.element_key}",
                {"seq": index, "element_key": action.element_key,
                 "declared": sorted(seen_keys)})

        # 参数 schema（与 Cases API 同一份校验）
        case_service.validate_action(action.action_key, bool(action.element_key),
                                     action.params)

        params = dict(action.params)
        if action.action_key == "navigate" and "wait_until" not in params:
            # 一键接入场景：domcontentloaded 常常拿不到 SPA 的元素，load 更稳
            params["wait_until"] = "load"
            warnings.append(
                f"第 {index} 条 navigate 未指定 wait_until，已按 load 生成（SPA 场景更稳）")

        actions.append(_Action(
            seq=index, action_key=action.action_key, element_key=action.element_key,
            params=params, output_var=action.output_var, timeout_ms=action.timeout_ms,
            on_failure=action.on_failure, retry_times=action.retry_times))

    return base_url, actions, warnings


def validate_locator_types(platform: str, engine_key: str, elements) -> None:
    """定位类型与端/引擎匹配（复用 M2 的字典校验，不另写一套）。"""
    for element in elements:
        for locator in element.locators:
            locator_service.validate_type(platform, engine_key, locator.locator_type)


# ─────────────────────────── 各步 ensure ───────────────────────────
async def _find_project(db: AsyncSession, code: str) -> Project | None:
    return (await db.execute(
        select(Project).where(Project.code == code, Project.is_deleted.is_(False))
    )).scalar_one_or_none()


async def _precheck_project(db: AsyncSession, spec) -> Project | None:
    """写库前的项目判定。

    * 已存在且端/引擎一致 → 复用；
    * 已存在但不一致 → 409（比笼统的"只支持 WEB"更准确）；
    * 不存在且不是 WEB → 422（本批次能力边界：Appium/u2 仍是桩）。
    """
    found = await _find_project(db, spec.code)
    if found is not None:
        if str(found.platform) != spec.platform or found.engine_key != spec.engine_key:
            raise ScaffoldProjectConflict(
                f"项目 code「{spec.code}」已存在，但端/引擎不一致",
                {"code": spec.code, "existing": {
                    "platform": str(found.platform), "engine_key": found.engine_key},
                 "incoming": {"platform": spec.platform, "engine_key": spec.engine_key}})
        return found
    if spec.platform != "WEB":
        raise ValidationFailed(
            "M3.4 只支持 WEB 端（Appium / uiautomator2 仍是桩，见 M4）",
            {"platform": spec.platform, "engine_key": spec.engine_key})
    return None


async def _ensure_project(db: AsyncSession, spec, tracker: _Tracker) -> tuple[Project, bool]:
    found = await _find_project(db, spec.code)
    if found is not None:
        return found, False

    # 软删的同 code 项目会占着唯一键 —— 回收它的 code（改名）后新建
    ghosts = list((await db.execute(
        select(Project).where(Project.code == spec.code, Project.is_deleted.is_(True))
    )).scalars().all())
    for ghost in ghosts:
        ghost.code = f"{spec.code[:40]}#del#{ghost.id}"
    if ghosts:
        await db.commit()

    project = Project(
        name=spec.name.strip(), code=spec.code.strip(), platform=spec.platform,
        engine_key=spec.engine_key, description=spec.description,
        default_timeout_ms=15_000,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    tracker.add("project", project.id)
    return project, True


async def _ensure_target(db: AsyncSession, project: Project, base_url: str,
                         spec_target, tracker: _Tracker) -> tuple[ExecutionTarget, bool]:
    found = (await db.execute(
        select(ExecutionTarget).where(ExecutionTarget.project_id == project.id,
                                      ExecutionTarget.base_url == base_url)
    )).scalar_one_or_none()
    if found is not None:
        options = dict(spec_target.options) if spec_target else {}
        if options and options != (found.options or {}):
            found.options = options            # 以本次输入为准
            await db.commit()
        if project.target_id != found.id:
            project.target_id = found.id
            await db.commit()
        return found, False

    target = ExecutionTarget(
        project_id=project.id,
        name=(spec_target.name if spec_target and spec_target.name else f"{project.name} 默认目标"),
        platform=str(project.platform), engine_key=project.engine_key,
        base_url=base_url, options=dict(spec_target.options) if spec_target else {},
        enabled=True,
    )
    db.add(target)
    await db.commit()
    await db.refresh(target)

    project.target_id = target.id
    await db.commit()
    tracker.add("target", target.id)
    return target, True


async def _ensure_elements(db: AsyncSession, project: Project, spec,
                           tracker: _Tracker) -> dict[str, tuple[int, bool, list[int]]]:
    """返回 {element_key: (element_id, created, locator_ids)}。"""
    result: dict[str, tuple[int, bool, list[int]]] = {}
    for element in spec.elements:
        found = (await db.execute(
            select(Element).where(Element.project_id == project.id,
                                  Element.parent_id == 0,
                                  Element.element_name == element.name,
                                  Element.is_deleted.is_(False))
        )).scalar_one_or_none()
        if found is not None:
            result[element.key] = (found.id, False, [])
            continue

        created = await element_service.create(
            db, project_id=project.id, parent_id=0,
            element_name=element.name, description=element.description)
        tracker.add("element", created.id)
        result[element.key] = (created.id, True, [])
    return result


async def _ensure_locators(db: AsyncSession, spec, elements: dict, platform: str,
                           engine_key: str, tracker: _Tracker) -> None:
    """补齐缺失的定位符（已存在的跳过，不重复插入）。"""
    from app.repositories import locator_repo

    for element in spec.elements:
        element_id, _, locator_ids = elements[element.key]
        rows = await locator_repo.group_rows(db, element_id, platform, engine_key)
        existing = {(row.locator_type, row.locator_value) for row in rows}

        for locator in element.locators:
            key = (locator.locator_type, locator.locator_value.strip())
            if key in existing:
                continue
            row = await locator_service.create(
                db, element_id=element_id, platform=platform, engine_key=engine_key,
                locator_type=locator.locator_type, locator_value=locator.locator_value)
            tracker.add("locator", row.id)
            locator_ids.append(row.id)
        elements[element.key] = (element_id, elements[element.key][1], locator_ids)


async def _ensure_case(db: AsyncSession, project: Project, spec, actions: list[_Action],
                       elements: dict, tracker: _Tracker) -> tuple[int, bool, list[int]]:
    """返回 (case_id, created, step_ids)。"""
    found = (await db.execute(
        select(TestCase).where(
            TestCase.project_id == project.id,
            TestCase.title == spec.case.title,
            TestCase.is_deleted.is_(False))
    )).scalar_one_or_none()

    if found is not None and spec.case.strategy == "recreate":
        await case_service.delete_case(db, found.id)     # 软删，deleted_seq 让同名可重建
        found = None

    if found is not None:
        steps = await case_service.list_steps(db, found.id)
        if steps:
            # 幂等核心：复用 case 时**绝不重复追加步骤**
            return found.id, False, [s.id for s in steps]

    created_case = found or await case_service.create_case(
        db, project_id=project.id, title=spec.case.title,
        description=spec.case.description)
    if found is None:
        tracker.add("case", created_case.id)

    step_ids: list[int] = []
    for action in actions:
        element_id = elements[action.element_key][0] if action.element_key else None
        step = await case_service.create_step(
            db, created_case.id, seq=action.seq, action_key=action.action_key,
            element_id=element_id, params=action.params,
            output_var=action.output_var, timeout_ms=action.timeout_ms,
            on_failure=action.on_failure, retry_times=action.retry_times,
        )
        step_ids.append(step.id)
    return created_case.id, found is None, step_ids


async def _ensure_suite(db: AsyncSession, project: Project, spec_case_id: int,
                        spec, tracker: _Tracker) -> tuple[TestSuite, bool, int]:
    found = (await db.execute(
        select(TestSuite).where(TestSuite.project_id == project.id,
                                TestSuite.name == spec.suite.name,
                                TestSuite.is_deleted.is_(False))
    )).scalar_one_or_none()
    created = False
    if found is None:
        found = await suite_service.create(
            db, project_id=project.id, name=spec.suite.name,
            description=spec.suite.description)
        tracker.add("suite", found.id)
        created = True

    await suite_service.add_cases(db, found.id, [spec_case_id])
    count = int((await db.execute(
        select(func.count(TestSuiteCase.id)).where(TestSuiteCase.suite_id == found.id)
    )).scalar_one())
    return found, created, count


# ─────────────────────────── 补偿 ───────────────────────────
async def _compensate(db: AsyncSession, tracker: _Tracker) -> None:
    for kind, object_id in reversed(tracker.entries):
        try:
            if kind == "suite":
                await suite_service.delete(db, object_id)
            elif kind == "case":
                await case_service.delete_case(db, object_id)
            elif kind == "locator":
                await locator_service.delete(db, object_id)
            elif kind == "element":
                await element_service.delete(db, object_id, force=True)
            elif kind == "target":
                row = await db.get(ExecutionTarget, object_id)
                if row is not None:
                    await db.delete(row)
                    await db.commit()
            elif kind == "project":
                await project_service.delete(db, object_id)
        except Exception:
            logger.warning("scaffold 补偿删除失败：%s#%s", kind, object_id, exc_info=True)


# ─────────────────────────── 主流程 ───────────────────────────
async def run(db: AsyncSession, spec: ScaffoldRequest) -> dict:
    started = time.perf_counter()
    base_url, actions, warnings = normalize(spec)          # S0：结构校验，零写入
    await _precheck_project(db, spec.project)              # S0.5：项目冲突 / 端支持
    validate_locator_types(                                   # S0.6：定位类型与端匹配
        spec.project.platform, spec.project.engine_key, spec.elements)

    tracker = _Tracker()
    try:
        # S1 项目
        project, project_created = await _ensure_project(db, spec.project, tracker)

        # S2 执行目标
        target, target_created = await _ensure_target(
            db, project, base_url, spec.target, tracker)

        # S3 元素
        elements = await _ensure_elements(db, project, spec, tracker)

        # S4 定位符
        await _ensure_locators(
            db, spec, elements, str(project.platform), project.engine_key, tracker)

        # S5 用例 + 步骤
        case_id, case_created, step_ids = await _ensure_case(
            db, project, spec, actions, elements, tracker)

        # S6 用例集
        suite, suite_created, case_count = await _ensure_suite(
            db, project, case_id, spec, tracker)
    except AppError:
        await _compensate(db, tracker)
        raise
    except Exception:
        await _compensate(db, tracker)
        raise

    # S7 执行（不在补偿范围内：资产已建好，执行失败是运行时问题）
    execution_payload = None
    if spec.run:
        try:
            execution = await suite_service.run(
                db, suite.id, trigger_type="MANUAL", target_id=target.id)
            execution_payload = {
                "id": execution.id, "status": str(execution.status),
                "suite_id": suite.id, "case_count": len(execution.case_ids or []),
                "queued_at": execution.created_at.isoformat(timespec="seconds")
                if execution.created_at else None,
            }
        except Exception as exc:                 # QueueFull 等
            warnings.append(f"资产已创建，但提交执行失败：{type(exc).__name__}: {exc}")

    return {
        "project": {"id": project.id, "code": project.code,
                    "platform": str(project.platform), "engine_key": project.engine_key,
                    "created": project_created},
        "target": {"id": target.id, "base_url": target.base_url,
                   "created": target_created},
        "elements": [
            {"key": element.key, "id": elements[element.key][0], "name": element.name,
             "created": elements[element.key][1],
             "locator_ids": elements[element.key][2]}
            for element in spec.elements
        ],
        "case": {"id": case_id, "title": spec.case.title, "created": case_created,
                 "step_ids": step_ids, "step_count": len(step_ids)},
        "suite": {"id": suite.id, "name": suite.name, "created": suite_created,
                  "case_count": case_count},
        "execution": execution_payload,
        "warnings": warnings,
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }
