"""树形服务：物化路径的组装、深度、循环检测与完整性校验（M2 §2.4）。

path 格式：``/7/12/45/`` —— ``/`` 开头结尾、每层是元素 id、**含自身**。
三条不变量：
  INV-1 每个节点 path = 父 path + 自身 id + '/'
  INV-2 path 以自身 id 结尾
  INV-3 深度 = path 中 '/' 的个数 - 1，且 ≤ MAX_DEPTH
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import ElementDepthExceeded, ElementMoveIntoDescendant, ValidationFailed
from app.models import Element
from app.repositories.element_repo import element_repo

ROOT_PATH = "/"


def depth_of(path: str) -> int:
    """``/`` → 0；``/7/`` → 1；``/7/12/`` → 2。"""
    if not path or path == ROOT_PATH:
        return 0
    return path.count("/") - 1


def build_path(parent_path: str, element_id: int) -> str:
    return f"{parent_path or ROOT_PATH}{element_id}/"


def assert_depth(path: str, *, extra_height: int = 1, max_depth: int | None = None) -> None:
    limit = max_depth or settings.max_tree_depth
    depth = depth_of(path) + extra_height - 1
    if depth > limit:
        raise ElementDepthExceeded(
            f"元素深度 {depth} 超过上限 {limit}",
            {"depth": depth, "max_depth": limit, "path": path},
        )


def is_self_or_descendant(target_path: str, node_path: str) -> bool:
    """``target_path`` 是否落在 ``node_path`` 的子树内（含自身）。

    ★ 必须用 ``startswith`` 而不是 ``in``：``in`` 会被 id 子串误判
      （``'/1/7/'`` 包含 ``'/7/'``，于是 id=7 会错误地把 id=17 当祖先）。
    """
    return target_path.startswith(node_path)


def path_names(path: str, name_map: dict[int, str]) -> list[str]:
    ids = [int(part) for part in path.strip("/").split("/") if part]
    return [name_map.get(i, str(i)) for i in ids]


async def parent_path(db: AsyncSession, project_id: int, parent_id: int) -> str:
    if not parent_id:
        return ROOT_PATH
    parent = await element_repo.get(db, parent_id)
    if parent is None or parent.project_id != project_id:
        from app.core.errors import ElementParentNotFound
        raise ElementParentNotFound(f"父节点 {parent_id} 不存在", {"parent_id": parent_id})
    return parent.path


async def subtree_height(db: AsyncSession, node: Element) -> int:
    """子树相对高度（只有自己 = 1）。"""
    rows = await element_repo.subtree(db, node.project_id, node.path)
    deepest = max((depth_of(r.path) for r in rows), default=depth_of(node.path))
    return deepest - depth_of(node.path) + 1


def move_guard(node: Element, new_parent_path: str) -> None:
    """移动到自身/子树下 → 拒绝（循环检测）。纯字符串判断，无需 async。"""
    if is_self_or_descendant(new_parent_path, node.path):
        raise ElementMoveIntoDescendant(
            f"不能把元素 {node.id} 移动到它自己的子树下（{new_parent_path}）",
            {"element_id": node.id, "target_path": new_parent_path, "node_path": node.path},
        )


async def assert_integrity(db: AsyncSession, project_id: int) -> list[dict]:
    """全量校验（运维排查用）：返回所有不满足不变量的节点。"""
    rows = await element_repo.list_by_project(db, project_id)
    by_id = {r.id: r for r in rows}
    broken: list[dict] = []
    for node in rows:
        expected = ROOT_PATH if not node.parent_id else by_id.get(node.parent_id, node).path
        if node.parent_id and node.parent_id not in by_id:
            broken.append({"id": node.id, "reason": "父节点不存在", "path": node.path})
            continue
        if node.path != build_path(expected, node.id):
            broken.append({"id": node.id, "reason": "path 与父链不符", "path": node.path,
                           "expected": build_path(expected, node.id)})
        if depth_of(node.path) > settings.max_tree_depth:
            broken.append({"id": node.id, "reason": "超过深度上限", "path": node.path})
    return broken


def assert_order_complete(current: list[int], submitted: list[int]) -> None:
    """排序提交的 id 集合必须与现有**完全一致**（不多、不少、不重）。"""
    from app.core.errors import ElementOrderIncomplete
    if len(submitted) != len(set(submitted)):
        raise ElementOrderIncomplete("排序列表含重复 id", {"duplicated": True})
    missing = sorted(set(current) - set(submitted))
    extra = sorted(set(submitted) - set(current))
    if missing or extra:
        raise ElementOrderIncomplete(
            "排序提交的 id 集合与现有不一致",
            {"missing_ids": missing, "extra_ids": extra},
        )


def ensure_folder(parent: Element | None) -> None:
    from app.core.errors import ElementParentMustBeFolder
    if parent is not None and parent.node_type != "FOLDER":
        raise ElementParentMustBeFolder(
            f"父节点 {parent.id} 是元素而非目录，不能挂子节点",
            {"parent_id": parent.id, "parent_type": parent.node_type},
        )


def require_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ValidationFailed("元素名称不能为空")
    if len(name) > 255:
        raise ValidationFailed("元素名称过长（上限 255）")
    return name
