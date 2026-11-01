"""页面扫描的纯逻辑（domain.scan）+ 服务导入（M3.5）。"""
from __future__ import annotations

import pytest

from app.core.errors import ScanImportEmpty, ScanTargetRequired
from app.domain.scan import Candidate, build_candidates, should_include
from app.models import Project
from app.schemas.scan import ScanImportRequest, ScanRequest
from app.services import scan_service


# ─────────────────────────── domain.scan ───────────────────────────
def _item(**overrides):
    base = {
        "tag": "div", "id": None, "testid": None, "name": None, "role": None,
        "ariaLabel": None, "placeholder": None, "href": None, "src": None,
        "alt": None, "title": None, "classes": [], "text": "", "visible": True,
    }
    base.update(overrides)
    return base


def test_priority_testid_over_id():
    cands, _ = build_candidates([
        _item(tag="input", testid="new-todo", id="raw-id", placeholder="要做什么？"),
    ])
    assert cands[0].locators[0].locator_type == "testid"
    assert cands[0].locators[0].locator_value == "new-todo"
    assert cands[0].locators[0].primary is True
    assert cands[0].strength == "strong"


def test_id_when_no_testid():
    cands, _ = build_candidates([_item(tag="button", id="submit", text="登录")])
    assert cands[0].locators[0].locator_type == "id"
    assert cands[0].strength == "strong"


def test_class_only_is_weak():
    cands, _ = build_candidates([_item(tag="p", classes=["lead", "bold"])])
    assert cands[0].strength == "weak"
    assert cands[0].locators[0].locator_type == "css"


def test_text_is_weak_for_leaf():
    cands, _ = build_candidates([_item(tag="p", text="欢迎使用")])
    assert cands[0].strength == "weak"
    assert cands[0].locators[0].locator_type == "text"


def test_placeholder_is_medium():
    cands, _ = build_candidates([_item(tag="input", placeholder="请输入用户名")])
    assert cands[0].strength == "medium"
    assert cands[0].locators[0].locator_type == "placeholder"


def test_container_skipped_unless_unique_attr():
    assert should_include(_item(tag="div")) is False
    assert should_include(_item(tag="div", testid="panel")) is True
    assert should_include(_item(tag="span", id="x")) is True
    assert should_include(_item(tag="script")) is False


def test_default_name_prefers_placeholder():
    cands, _ = build_candidates([_item(tag="input", placeholder="新待办", ariaLabel="待办输入")])
    assert cands[0].name == "待办输入"       # ariaLabel 优先


def test_default_name_falls_back_to_text():
    cands, _ = build_candidates([_item(tag="button", text="添加")])
    assert cands[0].name == "添加"


def test_duplicate_primary_deduped():
    cands, stats = build_candidates([
        _item(tag="input", testid="dup"),
        _item(tag="input", testid="dup"),
    ])
    assert len(cands) == 1
    assert stats["skipped"] == 1


def test_invisible_skipped():
    cands, stats = build_candidates([
        _item(tag="button", testid="hidden", visible=False),
    ])
    assert cands == []
    assert stats["skipped"] == 1


# ─────────────────────────── scan_service ───────────────────────────
async def _project(db, code="scan-p1", target_id=None) -> Project:
    row = Project(name="扫描项目", code=code, platform="WEB", engine_key="playwright",
                  target_id=target_id, default_timeout_ms=5000)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@pytest.mark.asyncio
async def test_scan_requires_target_or_url(db):
    project = await _project(db, target_id=None)
    with pytest.raises(ScanTargetRequired):
        await scan_service.scan(db, project.id, ScanRequest(url=None))


@pytest.mark.asyncio
async def test_import_empty_rejected(db):
    project = await _project(db)
    # Pydantic 已拦（min_length=1）；这里绕过验证 service 的兜底
    req = ScanImportRequest.model_construct(candidates=[])
    with pytest.raises(ScanImportEmpty):
        await scan_service.import_candidates(db, project.id, req)


@pytest.mark.asyncio
async def test_import_creates_elements_and_locators(db):
    project = await _project(db)
    result = await scan_service.import_candidates(db, project.id, ScanImportRequest(
        candidates=[
            {"name": "添加按钮", "locators": [
                {"locator_type": "testid", "locator_value": "add"}]},
            {"name": "输入框", "locators": [
                {"locator_type": "testid", "locator_value": "todo"}]},
        ]))
    assert len(result["created"]) == 2
    assert result["failed"] == []
    for item in result["created"]:
        assert item["element_id"] > 0
        assert item["locator_ids"]


@pytest.mark.asyncio
async def test_import_duplicate_name_goes_to_failed(db):
    project = await _project(db)
    body = ScanImportRequest(candidates=[
        {"name": "按钮", "locators": [{"locator_type": "testid", "locator_value": "a"}]}])
    first = await scan_service.import_candidates(db, project.id, body)
    assert len(first["created"]) == 1

    second = await scan_service.import_candidates(db, project.id, body)
    assert second["created"] == []
    assert len(second["failed"]) == 1
    assert second["failed"][0]["code"] == "ELEMENT_NAME_DUPLICATED"


@pytest.mark.asyncio
async def test_import_partial_locator_failure(db):
    """定位符类型不合法时，元素仍创建但 locator_ids 为空，失败进入 failed（不中断）。"""
    project = await _project(db)
    result = await scan_service.import_candidates(db, project.id, ScanImportRequest(
        candidates=[
            {"name": "按钮", "locators": [
                {"locator_type": "resource_id", "locator_value": "x"}]},
        ]))
    assert result["created"][0]["locator_ids"] == []   # 元素建了，定位符没建成
    assert len(result["failed"]) == 1
    assert result["failed"][0]["code"] == "LOCATOR_PARTIAL"
