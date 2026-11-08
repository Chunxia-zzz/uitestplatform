"""一键接入（M3.4）：装配、幂等、补偿与全部前置校验。

核心断言不是"能建出来"，而是：
* 同一个输入重复提交，**前六类资产 id 不变、步骤不翻倍**；
* 任何静态错误都在**写库之前**被拦下（事后按 code 查不到项目）；
* 复用 case 与新建 case 的分支行为不同但都可预期。
"""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.core.errors import (
    ElementLocatorTypeInvalid,
    ScaffoldElementRequired,
    ScaffoldElementUnexpected,
    ScaffoldElementWithoutLocator,
    ScaffoldInvalidUrl,
    ScaffoldProjectConflict,
    ScaffoldUnknownElementKey,
    ValidationFailed,
)
from app.models import Project, TestCase, TestStep
from app.schemas.scaffold import ScaffoldRequest
from app.services import scaffold_service


def make_spec(**overrides) -> ScaffoldRequest:
    payload = {
        "project": {"name": "Scaffold 项目", "code": "scaffold-demo",
                    "platform": "WEB", "engine_key": "playwright"},
        "url": "http://127.0.0.1:8899/login.html",
        "elements": [
            {"key": "username", "name": "用户名输入框",
             "locators": [{"locator_type": "testid", "locator_value": "username"}]},
            {"key": "submit", "name": "登录按钮",
             "locators": [
                 {"locator_type": "testid", "locator_value": "submit-not-exist"},
                 {"locator_type": "css", "locator_value": "#submit"},
             ]},
        ],
        "actions": [
            {"action_key": "navigate", "params": {"url": "/login.html"}},
            {"action_key": "input", "element_key": "username", "params": {"text": "jerry"}},
            {"action_key": "click", "element_key": "submit", "params": {}},
        ],
        "case": {"title": "登录主链路"},
        "suite": {"name": "冒烟回归"},
        "run": False,
    }
    payload.update(overrides)
    return ScaffoldRequest(**payload)


async def project_count(db) -> int:
    return int((await db.execute(select(func.count(Project.id)))).scalar_one())


# ─────────────────────────── 正常装配 ───────────────────────────
@pytest.mark.asyncio
async def test_scaffold_creates_full_chain(db):
    result = await scaffold_service.run(db, make_spec())

    assert result["project"]["created"] is True
    assert result["target"]["created"] is True
    assert result["target"]["base_url"] == "http://127.0.0.1:8899"
    assert [e["created"] for e in result["elements"]] == [True, True]
    assert result["case"]["created"] is True
    assert result["case"]["step_count"] == 3
    assert result["suite"]["created"] is True
    assert result["suite"]["case_count"] == 1
    assert result["execution"] is None          # run=False

    # 步骤 seq 与输入顺序一致，element_id 正确绑定
    steps = list((await db.execute(
        select(TestStep).order_by(TestStep.seq))).scalars().all())
    assert [s.seq for s in steps] == [1, 2, 3]
    assert [s.action_key for s in steps] == ["navigate", "input", "click"]
    element_ids = {e["id"] for e in result["elements"]}
    assert steps[1].element_id in element_ids
    assert steps[2].element_id in element_ids
    assert steps[0].element_id is None


@pytest.mark.asyncio
async def test_two_locators_form_priority_chain(db):
    result = await scaffold_service.run(db, make_spec())
    submit = next(e for e in result["elements"] if e["key"] == "submit")
    assert len(submit["locator_ids"]) == 2

    from app.repositories import locator_repo
    rows = await locator_repo.group_rows(db, submit["id"], "WEB", "playwright")
    by_value = {r.locator_value: r for r in rows}
    # testid 的 rank 高于 css → priority 更小，且自动成为 is_primary
    assert by_value["submit-not-exist"].priority < by_value["#submit"].priority
    assert by_value["submit-not-exist"].is_primary is True


@pytest.mark.asyncio
async def test_navigate_gets_default_wait_until(db):
    result = await scaffold_service.run(db, make_spec())
    assert any("wait_until" in w for w in result["warnings"])

    steps = list((await db.execute(
        select(TestStep).order_by(TestStep.seq))).scalars().all())
    assert steps[0].params["wait_until"] == "load"


@pytest.mark.asyncio
async def test_explicit_wait_until_is_kept(db):
    spec = make_spec(actions=[
        {"action_key": "navigate",
         "params": {"url": "/login.html", "wait_until": "domcontentloaded"}},
    ])
    result = await scaffold_service.run(db, spec)
    assert not any("wait_until" in w for w in result["warnings"])
    steps = list((await db.execute(select(TestStep))).scalars().all())
    assert steps[0].params["wait_until"] == "domcontentloaded"


# ─────────────────────────── 幂等 ───────────────────────────
@pytest.mark.asyncio
async def test_same_input_twice_is_idempotent(db):
    first = await scaffold_service.run(db, make_spec())
    second = await scaffold_service.run(db, make_spec())

    assert second["project"]["id"] == first["project"]["id"]
    assert second["project"]["created"] is False
    assert second["target"]["id"] == first["target"]["id"]
    assert [e["id"] for e in second["elements"]] == [e["id"] for e in first["elements"]]
    assert second["case"]["id"] == first["case"]["id"]
    assert second["suite"]["id"] == first["suite"]["id"]
    assert second["case"]["step_count"] == first["case"]["step_count"] == 3

    # 真正的幂等判据：步骤没有翻倍
    assert int((await db.execute(select(func.count(TestStep.id)))).scalar_one()) == 3


@pytest.mark.asyncio
async def test_recreate_replaces_case(db):
    first = await scaffold_service.run(db, make_spec())
    spec = make_spec(case={"title": "登录主链路", "strategy": "recreate"})
    second = await scaffold_service.run(db, spec)

    assert second["case"]["id"] != first["case"]["id"]
    assert second["case"]["created"] is True
    # 旧用例软删（其步骤保留以便追溯），新用例一套步骤 → **存活用例**的步骤数是 3
    alive_steps = int((await db.execute(
        select(func.count(TestStep.id))
        .join(TestCase, TestCase.id == TestStep.case_id)
        .where(TestCase.is_deleted.is_(False)))).scalar_one())
    assert alive_steps == 3
    alive = list((await db.execute(
        select(TestCase).where(TestCase.is_deleted.is_(False)))).scalars().all())
    assert len(alive) == 1


@pytest.mark.asyncio
async def test_reuse_case_with_zero_steps_gets_steps(db):
    """复用一个空用例时应补步骤（否则用例集跑起来是 0 步）。"""
    from app.services import case_service

    await scaffold_service.run(db, make_spec())
    project = (await db.execute(select(Project))).scalar_one()
    empty = await case_service.create_case(db, project_id=project.id, title="空用例")

    spec = make_spec(case={"title": "空用例"})
    result = await scaffold_service.run(db, spec)
    assert result["case"]["id"] == empty.id
    assert result["case"]["created"] is False
    assert result["case"]["step_count"] == 3


@pytest.mark.asyncio
async def test_project_conflict_on_platform_mismatch(db):
    await scaffold_service.run(db, make_spec())
    with pytest.raises(ScaffoldProjectConflict):
        await scaffold_service.run(db, make_spec(project={
            "name": "Scaffold 项目", "code": "scaffold-demo",
            "platform": "ANDROID", "engine_key": "appium"}))


# ───────────────────── 前置校验：失败不留数据 ─────────────────────
@pytest.mark.asyncio
async def test_invalid_url_creates_nothing(db):
    with pytest.raises(ScaffoldInvalidUrl):
        await scaffold_service.run(db, make_spec(url="ftp://example.com"))
    assert await project_count(db) == 0


@pytest.mark.asyncio
async def test_unknown_element_key_creates_nothing(db):
    spec = make_spec(actions=[
        {"action_key": "click", "element_key": "not-declared", "params": {}},
    ])
    with pytest.raises(ScaffoldUnknownElementKey):
        await scaffold_service.run(db, spec)
    assert await project_count(db) == 0


@pytest.mark.asyncio
async def test_action_requiring_element_without_key(db):
    spec = make_spec(actions=[{"action_key": "click", "params": {}}])
    with pytest.raises(ScaffoldElementRequired):
        await scaffold_service.run(db, spec)
    assert await project_count(db) == 0


@pytest.mark.asyncio
async def test_plain_action_with_element_key(db):
    spec = make_spec(actions=[
        {"action_key": "navigate", "element_key": "username",
         "params": {"url": "/x"}},
    ])
    with pytest.raises(ScaffoldElementUnexpected):
        await scaffold_service.run(db, spec)
    assert await project_count(db) == 0


@pytest.mark.asyncio
async def test_element_without_locator_rejected(db):
    spec = make_spec()
    # Pydantic 层已拦（min_length=1）；这里绕过它验证 service 的兜底
    spec.elements[0] = type(spec.elements[0]).model_construct(
        key="a", name="无定位符元素", description=None, locators=[])
    with pytest.raises(ScaffoldElementWithoutLocator):
        await scaffold_service.run(db, spec)
    assert await project_count(db) == 0


@pytest.mark.asyncio
async def test_locator_type_must_match_platform(db):
    """WEB/playwright 不能用 Android 语义类型（resource_id）。"""
    spec = make_spec(elements=[
        {"key": "a", "name": "按钮",
         "locators": [{"locator_type": "resource_id", "locator_value": "x"}]},
    ], actions=[{"action_key": "click", "element_key": "a", "params": {}}])
    with pytest.raises(ElementLocatorTypeInvalid):
        await scaffold_service.run(db, spec)
    assert await project_count(db) == 0


@pytest.mark.asyncio
async def test_unknown_action_creates_nothing(db):
    spec = make_spec(actions=[{"action_key": "no_such", "params": {}}])
    with pytest.raises(ValidationFailed):
        await scaffold_service.run(db, spec)
    assert await project_count(db) == 0


@pytest.mark.asyncio
async def test_params_must_match_schema(db):
    spec = make_spec(actions=[{"action_key": "navigate", "params": {}}])
    with pytest.raises(ValidationFailed):
        await scaffold_service.run(db, spec)
    assert await project_count(db) == 0


@pytest.mark.asyncio
async def test_non_web_platform_rejected(db):
    spec = make_spec(project={
        "name": "P", "code": "p-android", "platform": "ANDROID", "engine_key": "appium"})
    with pytest.raises(ValidationFailed):
        await scaffold_service.run(db, spec)


# ─────────────────────────── 执行衔接 ───────────────────────────
@pytest.mark.asyncio
async def test_run_true_submits_execution(db, monkeypatch):
    """run=true 时装配完成后应调用 suite_service.run（这里替换成假对象）。"""
    calls: list[dict] = []

    class FakeExecution:
        id = 777
        status = "PENDING"
        case_ids = [1]
        created_at = None

    async def fake_run(db_, suite_id, **kwargs):
        calls.append({"suite_id": suite_id, **kwargs})
        return FakeExecution()

    monkeypatch.setattr(scaffold_service.suite_service, "run", fake_run)
    result = await scaffold_service.run(db, make_spec(run=True))

    assert result["execution"]["id"] == 777
    assert result["execution"]["suite_id"] == result["suite"]["id"]
    assert calls and calls[0]["suite_id"] == result["suite"]["id"]


@pytest.mark.asyncio
async def test_run_failure_keeps_assets_and_warns(db, monkeypatch):
    async def boom(db_, suite_id, **kwargs):
        raise RuntimeError("queue full")

    monkeypatch.setattr(scaffold_service.suite_service, "run", boom)
    result = await scaffold_service.run(db, make_spec(run=True))

    assert result["execution"] is None
    assert any("提交执行失败" in w for w in result["warnings"])
    assert await project_count(db) == 1        # 资产保留，不回滚


@pytest.mark.asyncio
async def test_soft_deleted_project_code_is_reclaimed(db):
    """项目软删后同 code 仍可再次接入（唯一键不会被幽灵行占住）。"""
    from app.services import project_service

    first = await scaffold_service.run(db, make_spec())
    await project_service.delete(db, first["project"]["id"])

    second = await scaffold_service.run(db, make_spec())
    assert second["project"]["created"] is True
    assert second["project"]["id"] != first["project"]["id"]
