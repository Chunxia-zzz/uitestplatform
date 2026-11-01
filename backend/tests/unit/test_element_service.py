"""元素服务：软删唯一键 / 移动子树 / 排序 / 引用保护（M2 V1/V5/V6/V7/V9）。"""
from __future__ import annotations

import pytest

from app.core.errors import (
    ElementFolderNotEmpty, ElementNameDuplicated, ElementOrderIncomplete,
    ElementParentMustBeFolder, ElementReferenced,
)
from app.services import element_service


@pytest.mark.asyncio
async def test_create_builds_path(db):
    root = await element_service.create(db, project_id=1, parent_id=0,
                                        element_name="登录模块", node_type="FOLDER")
    child = await element_service.create(db, project_id=1, parent_id=root.id,
                                         element_name="登录按钮")
    assert root.path == f"/{root.id}/"
    assert child.path == f"/{root.id}/{child.id}/"
    assert child.parent_id == root.id


@pytest.mark.asyncio
async def test_element_cannot_be_parent(db):
    parent = await element_service.create(db, project_id=1, parent_id=0, element_name="按钮")
    with pytest.raises(ElementParentMustBeFolder):
        await element_service.create(db, project_id=1, parent_id=parent.id,
                                     element_name="子节点")


@pytest.mark.asyncio
async def test_duplicate_name_rejected(db):
    await element_service.create(db, project_id=1, parent_id=0, element_name="同名")
    with pytest.raises(ElementNameDuplicated):
        await element_service.create(db, project_id=1, parent_id=0, element_name="同名")


@pytest.mark.asyncio
async def test_soft_delete_allows_recreating_and_deleting_twice(db):
    """★ V6 / F-M2-2 回归：布尔 is_deleted 参与唯一键时，第二次删除必然撞键。"""
    first = await element_service.create(db, project_id=1, parent_id=0, element_name="按钮A")
    await element_service.delete(db, first.id)

    second = await element_service.create(db, project_id=1, parent_id=0, element_name="按钮A")
    await element_service.delete(db, second.id)      # 不应抛 Duplicate entry

    third = await element_service.create(db, project_id=1, parent_id=0, element_name="按钮A")
    assert third.id != first.id
    assert third.deleted_seq == 0


@pytest.mark.asyncio
async def test_delete_folder_with_children_rejected(db):
    folder = await element_service.create(db, project_id=1, parent_id=0,
                                          element_name="目录", node_type="FOLDER")
    await element_service.create(db, project_id=1, parent_id=folder.id, element_name="子")
    with pytest.raises(ElementFolderNotEmpty):
        await element_service.delete(db, folder.id)


@pytest.mark.asyncio
async def test_move_rewrites_all_descendant_paths(db):
    """V1：移动整棵子树后，后代的 path 必须全部跟着改。"""
    a = await element_service.create(db, project_id=1, parent_id=0,
                                     element_name="A", node_type="FOLDER")
    b = await element_service.create(db, project_id=1, parent_id=0,
                                     element_name="B", node_type="FOLDER")
    mid = await element_service.create(db, project_id=1, parent_id=a.id,
                                       element_name="mid", node_type="FOLDER")
    leaf = await element_service.create(db, project_id=1, parent_id=mid.id,
                                        element_name="leaf")

    mid_id, leaf_id = mid.id, leaf.id
    await element_service.move(db, a.id, new_parent_id=b.id)

    # move() 会 expire_all（子树 path 被批量改写），因此重新查询而不是复用旧对象
    refreshed_mid = await element_service.get_or_404(db, mid_id)
    refreshed_leaf = await element_service.get_or_404(db, leaf_id)
    assert refreshed_mid.path == f"/{b.id}/{a.id}/{mid_id}/"
    assert refreshed_leaf.path == f"/{b.id}/{a.id}/{mid_id}/{leaf_id}/"
    assert refreshed_leaf.parent_id == mid_id


@pytest.mark.asyncio
async def test_reorder_children(db):
    parent = await element_service.create(db, project_id=1, parent_id=0,
                                          element_name="p", node_type="FOLDER")
    c1 = await element_service.create(db, project_id=1, parent_id=parent.id, element_name="c1")
    c2 = await element_service.create(db, project_id=1, parent_id=parent.id, element_name="c2")
    c3 = await element_service.create(db, project_id=1, parent_id=parent.id, element_name="c3")

    await element_service.reorder_children(db, parent.id, [c3.id, c1.id, c2.id])

    from app.repositories.element_repo import element_repo
    children = [c.id for c in await element_repo.children(db, 1, parent.id)]
    assert children == [c3.id, c1.id, c2.id]

    with pytest.raises(ElementOrderIncomplete):
        await element_service.reorder_children(db, parent.id, [c1.id])


@pytest.mark.asyncio
async def test_delete_blocked_by_case_reference(db):
    from app.models import TestCase, TestStep

    element = await element_service.create(db, project_id=1, parent_id=0,
                                           element_name="被引用")
    case = TestCase(project_id=1, title="t")
    db.add(case)
    await db.commit()
    await db.refresh(case)
    db.add(TestStep(case_id=case.id, seq=1, action_key="click",
                    element_id=element.id, params={}))
    await db.commit()

    with pytest.raises(ElementReferenced) as exc:
        await element_service.delete(db, element.id)
    assert exc.value.detail["references"][0]["case_id"] == case.id

    result = await element_service.delete(db, element.id, force=True)
    assert result["deleted_id"] == element.id
