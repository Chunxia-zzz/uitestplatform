"""定位符服务：三层校验 / 唯一性 / 验证结果判定（M2 V2/V4/V8/V9）。"""
from __future__ import annotations

import pytest

from app.core.errors import (
    ElementFolderHasNoLocator,
    ElementLocatorDuplicated,
    ElementLocatorTypeEngineUnsupported,
    ElementLocatorTypeInvalid,
    ElementLocatorWildcardUnscoped,
    ProjectPlatformEngineMismatch,
)
from app.domain.enums import LocatorStatus
from app.services import element_service, locator_service


@pytest.mark.asyncio
async def test_folder_cannot_hold_locator(db):
    folder = await element_service.create(db, project_id=1, parent_id=0,
                                          element_name="dir", node_type="FOLDER")
    with pytest.raises(ElementFolderHasNoLocator):
        await locator_service.create(db, element_id=folder.id, platform="WEB",
                                     engine_key="playwright", locator_type="css",
                                     locator_value="#x")


@pytest.mark.asyncio
async def test_three_layer_validation(db):
    element = await element_service.create(db, project_id=1, parent_id=0, element_name="el")

    # ① 类型不属于该平台
    with pytest.raises(ElementLocatorTypeInvalid):
        await locator_service.create(db, element_id=element.id, platform="IOS",
                                     engine_key="appium", locator_type="css",
                                     locator_value="#x")

    # ② 引擎不支持该类型
    with pytest.raises(ElementLocatorTypeEngineUnsupported):
        await locator_service.create(db, element_id=element.id, platform="ANDROID",
                                     engine_key="uiautomator2", locator_type="uiautomator",
                                     locator_value='new UiSelector().text("登录")')

    # ③ 引擎专属类型不能通配
    with pytest.raises(ElementLocatorWildcardUnscoped):
        await locator_service.create(db, element_id=element.id, platform="ANDROID",
                                     engine_key="*", locator_type="uiautomator",
                                     locator_value='new UiSelector().text("登录")')

    # ④ 引擎不属于该平台
    with pytest.raises(ProjectPlatformEngineMismatch):
        await locator_service.create(db, element_id=element.id, platform="IOS",
                                     engine_key="uiautomator2", locator_type="xpath",
                                     locator_value="//x")


@pytest.mark.asyncio
async def test_semantic_type_works_for_both_android_engines(db):
    """★ F-M2-1 的价值：一条 resource_id 同时服务 appium 与 u2（engine_key='*'）。"""
    element = await element_service.create(db, project_id=1, parent_id=0, element_name="el")
    locator = await locator_service.create(
        db, element_id=element.id, platform="ANDROID", engine_key="*",
        locator_type="resource_id", locator_value="com.demo:id/login")
    assert locator.engine_key == "*"
    assert locator.priority == 10          # rank 1 → 10
    assert locator.is_primary is True      # 组内第一条自动首选


@pytest.mark.asyncio
async def test_duplicate_locator_rejected(db):
    element = await element_service.create(db, project_id=1, parent_id=0, element_name="el")
    await locator_service.create(db, element_id=element.id, platform="WEB",
                                 engine_key="playwright", locator_type="css",
                                 locator_value="#a")
    with pytest.raises(ElementLocatorDuplicated):
        await locator_service.create(db, element_id=element.id, platform="WEB",
                                     engine_key="playwright", locator_type="css",
                                     locator_value="#a")


@pytest.mark.asyncio
async def test_bulk_allows_partial_success(db):
    element = await element_service.create(db, project_id=1, parent_id=0, element_name="el")
    result = await locator_service.create_bulk(db, element.id, [
        {"platform": "WEB", "engine_key": "playwright", "locator_type": "testid",
         "locator_value": "ok"},
        {"platform": "IOS", "engine_key": "appium", "locator_type": "css",
         "locator_value": "#bad"},
    ])
    assert len(result["created"]) == 1
    assert len(result["failed"]) == 1
    assert result["failed"][0]["code"] == "ELEMENT_LOCATOR_TYPE_INVALID"


@pytest.mark.asyncio
async def test_reorder_and_set_primary(db):
    element = await element_service.create(db, project_id=1, parent_id=0, element_name="el")
    a = await locator_service.create(db, element_id=element.id, platform="WEB",
                                     engine_key="playwright", locator_type="css",
                                     locator_value="#a")
    b = await locator_service.create(db, element_id=element.id, platform="WEB",
                                     engine_key="playwright", locator_type="css",
                                     locator_value="#b")

    await locator_service.reorder(db, element.id, "WEB", "playwright", [b.id, a.id])
    await db.refresh(a)
    await db.refresh(b)
    assert (b.priority, a.priority) == (10, 20)

    await locator_service.set_primary(db, b.id)
    await db.refresh(a)
    await db.refresh(b)
    assert b.is_primary is True and a.is_primary is False


@pytest.mark.asyncio
async def test_mark_verified_multiple_keeps_status(db):
    """★ FR25：matched>1 只警告，不落 INVALID（列表页定位符本来就命中多行）。"""
    element = await element_service.create(db, project_id=1, parent_id=0, element_name="el")
    locator = await locator_service.create(db, element_id=element.id, platform="WEB",
                                           engine_key="playwright", locator_type="css",
                                           locator_value=".list-item")

    locator_service.mark_verified(locator, matched=3, verdict="MULTIPLE",
                                  sample={"tag": "li"}, error=None)
    assert locator.status == LocatorStatus.UNVERIFIED
    assert locator.probe_detail["matched"] == 3

    locator_service.mark_verified(locator, matched=1, verdict="VALID", sample={}, error=None)
    assert locator.status == LocatorStatus.VALID

    locator_service.mark_verified(locator, matched=0, verdict="NONE", sample=None, error=None)
    assert locator.status == LocatorStatus.INVALID
