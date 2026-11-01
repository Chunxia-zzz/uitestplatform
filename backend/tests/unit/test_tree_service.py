"""树形模型（M2 U3–U7）：path / 深度 / 循环 / 排序。"""
from __future__ import annotations

import pytest

from app.core.errors import ElementMoveIntoDescendant, ElementOrderIncomplete
from app.services import tree_service
from app.services.tree_service import build_path, depth_of, is_self_or_descendant


@pytest.mark.parametrize("path,expected", [
    ("/", 0), ("/7/", 1), ("/7/12/", 2), ("/7/12/45/", 3),
])
def test_depth(path, expected):
    assert depth_of(path) == expected


def test_build_path():
    assert build_path("/", 7) == "/7/"
    assert build_path("/7/", 12) == "/7/12/"


def test_assert_depth_limit():
    tree_service.assert_depth("/1/2/3/4/5/6/7/8/", max_depth=8)
    with pytest.raises(Exception) as exc:
        tree_service.assert_depth("/1/2/3/4/5/6/7/8/9/", max_depth=8)
    assert "ELEMENT_DEPTH_EXCEEDED" == getattr(exc.value, "code")


def test_cycle_detection_uses_prefix_not_substring():
    """★ id 是字符串子串的陷阱：7 不能把 17 当祖先，反之亦然。"""
    assert is_self_or_descendant("/7/12/", "/7/") is True
    assert is_self_or_descendant("/17/", "/7/") is False
    assert is_self_or_descendant("/7/", "/7/") is True
    assert is_self_or_descendant("/1/7/", "/7/") is False


@pytest.mark.asyncio
async def test_move_into_own_subtree_rejected(db):
    from app.services import element_service

    root = await element_service.create(db, project_id=1, parent_id=0,
                                        element_name="root", node_type="FOLDER")
    child = await element_service.create(db, project_id=1, parent_id=root.id,
                                         element_name="child", node_type="FOLDER")
    with pytest.raises(ElementMoveIntoDescendant):
        await element_service.move(db, root.id, new_parent_id=child.id)


def test_order_must_be_complete():
    tree_service.assert_order_complete([1, 2, 3], [3, 1, 2])
    with pytest.raises(ElementOrderIncomplete):
        tree_service.assert_order_complete([1, 2, 3], [1, 2])
    with pytest.raises(ElementOrderIncomplete):
        tree_service.assert_order_complete([1, 2], [1, 2, 3])
    with pytest.raises(ElementOrderIncomplete):
        tree_service.assert_order_complete([1, 2], [1, 2, 2])
