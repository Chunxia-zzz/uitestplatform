"""元素服务：CRUD / 软删 / 引用保护 / 树形读取。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ElementFolderNotEmpty, ElementNameDuplicated, ElementNodeTypeConflict,
    ElementNotFound, ElementReferenced,
)
from app.models import Element, ElementLocator, TestStep
from app.repositories.element_repo import element_repo
from app.repositories.locator_repo import locator_repo
from app.services import tree_service


async def get_or_404(db: AsyncSession, element_id: int) -> Element:
    node = await element_repo.get(db, element_id)
    if node is None:
        raise ElementNotFound(f"元素 {element_id} 不存在", {"element_id": element_id})
    return node


async def _assert_name_free(db: AsyncSession, project_id: int, parent_id: int, name: str,
                            exclude_id: int | None = None) -> None:
    conflict = await element_repo.name_exists(db, project_id, parent_id, name,
                                              exclude_id=exclude_id)
    if conflict:
        raise ElementNameDuplicated(
            f"同级已存在同名节点「{name}」",
            {"element_name": name, "parent_id": parent_id, "conflict_id": conflict},
        )


async def create(db: AsyncSession, *, project_id: int, parent_id: int, element_name: str,
                 node_type: str = "ELEMENT", description: str | None = None,
                 memo: str | None = None) -> Element:
    name = tree_service.require_name(element_name)
    parent = None
    if parent_id:
        parent = await get_or_404(db, parent_id)
        if parent.project_id != project_id:
            from app.core.errors import ElementParentNotFound
            raise ElementParentNotFound("父节点不属于该项目", {"parent_id": parent_id})
        tree_service.ensure_folder(parent)

    await _assert_name_free(db, project_id, parent_id, name)

    node = Element(project_id=project_id, parent_id=parent_id, path="",
                   element_name=name, node_type=node_type,
                   description=description, memo=memo, sort=0, deleted_seq=0)
    db.add(node)
    await db.flush()                      # 拿到 id，仍在同一事务内

    node.path = tree_service.build_path(parent.path if parent else tree_service.ROOT_PATH, node.id)
    tree_service.assert_depth(node.path)  # 超限 → ELEMENT_DEPTH_EXCEEDED
    await db.commit()
    await db.refresh(node)
    return node


async def update(db: AsyncSession, element_id: int, *, element_name: str | None = None,
                 description: str | None = None, memo: str | None = None,
                 node_type: str | None = None) -> Element:
    node = await get_or_404(db, element_id)

    if element_name is not None and element_name.strip() != node.element_name:
        name = tree_service.require_name(element_name)
        await _assert_name_free(db, node.project_id, node.parent_id, name, exclude_id=node.id)
        node.element_name = name

    if node_type is not None and node_type != node.node_type:
        child_count = await element_repo.count_children(db, node.project_id, node.id)
        locator_count = await locator_repo.count_by_element(db, node.id)
        if child_count or locator_count:
            raise ElementNodeTypeConflict(
                "节点已有子节点或定位符，不能切换类型",
                {"child_count": child_count, "locator_count": locator_count},
            )
        node.node_type = node_type

    if description is not None:
        node.description = description
    if memo is not None:
        node.memo = memo

    await db.commit()
    await db.refresh(node)
    return node


async def move(db: AsyncSession, element_id: int, *, new_parent_id: int,
               index: int | None = None) -> Element:
    node = await get_or_404(db, element_id)
    new_parent_path = await tree_service.parent_path(db, node.project_id, new_parent_id)

    if new_parent_id:
        new_parent = await get_or_404(db, new_parent_id)
        tree_service.ensure_folder(new_parent)

    tree_service.move_guard(node, new_parent_path)

    # 一次取回子树（同时用于"高度"与"改写后同步内存对象"）
    subtree_rows = await element_repo.subtree(db, node.project_id, node.path)
    deepest = max((tree_service.depth_of(r.path) for r in subtree_rows),
                  default=tree_service.depth_of(node.path))
    height = deepest - tree_service.depth_of(node.path) + 1

    new_path = tree_service.build_path(new_parent_path, node.id)
    tree_service.assert_depth(new_path, extra_height=height)

    if new_parent_id != node.parent_id:
        await _assert_name_free(db, node.project_id, new_parent_id, node.element_name,
                                exclude_id=node.id)

    old_path = node.path
    await element_repo.rewrite_path_prefix(db, node.project_id, old_path, new_path)

    # 同步身份映射里的子树对象（避免用 expire_all —— 那会把调用方持有的对象也置为过期，
    # 后续任何属性访问都会触发 greenlet 之外的懒加载）
    for item in subtree_rows:
        item.path = new_path + item.path[len(old_path):]
    node.parent_id = new_parent_id

    siblings = [s for s in await element_repo.children(db, node.project_id, new_parent_id)
                if s.id != node.id]
    ordered = [s.id for s in siblings]
    ordered.insert(index if index is not None and 0 <= index <= len(ordered) else len(ordered),
                   node.id)
    await element_repo.set_sort_batch(db, ordered)

    await db.commit()
    return node


async def reorder_children(db: AsyncSession, element_id: int, ordered_ids: list[int]) -> None:
    """`element_id` 只用于定位父节点语义：提交的是它的**子节点**顺序。"""
    node = await get_or_404(db, element_id)
    current = [c.id for c in await element_repo.children(db, node.project_id, node.id)]
    tree_service.assert_order_complete(current, ordered_ids)
    await element_repo.set_sort_batch(db, ordered_ids)
    await db.commit()


async def references(db: AsyncSession, element_id: int, limit: int = 500) -> list[dict]:
    stmt = (select(TestStep, )
            .where(TestStep.element_id == element_id)
            .order_by(TestStep.case_id, TestStep.seq)
            .limit(limit + 1))
    rows = (await db.execute(stmt)).scalars().all()
    truncated = len(rows) > limit
    from app.models import TestCase
    result: list[dict] = []
    for step in rows[:limit]:
        case = (await db.execute(select(TestCase).where(TestCase.id == step.case_id))
                ).scalar_one_or_none()
        result.append({
            "case_id": step.case_id,
            "title": case.title if case else "(用例已删除)",
            "step_seq": step.seq,
            "action_key": step.action_key,
        })
    if truncated:
        result.append({"truncated": True, "limit": limit})
    return result


async def delete(db: AsyncSession, element_id: int, *, force: bool = False) -> dict:
    node = await get_or_404(db, element_id)

    child_count = await element_repo.count_children(db, node.project_id, node.id)
    if child_count:
        raise ElementFolderNotEmpty(
            f"目录下还有 {child_count} 个子节点", {"child_count": child_count})

    refs = await references(db, element_id)
    affected = [r for r in refs if not r.get("truncated")]
    if affected and not force:
        raise ElementReferenced(
            f"元素被 {len(affected)} 个用例步骤引用，无法删除",
            {"references": affected},
        )

    node.is_deleted = True
    node.deleted_at = datetime.now()
    # ★ 0 = 未删；删除时置为自身 id —— 使「删两次同名元素」不再撞唯一键（M2 F-M2-2）
    node.deleted_seq = node.id
    deleted_locators = await locator_repo.delete_by_element(db, node.id)
    await db.commit()
    return {"deleted_id": element_id, "deleted_locators": deleted_locators,
            "affected_cases": affected}


async def duplicate(db: AsyncSession, element_id: int, *, target_parent_id: int | None = None,
                    new_name: str | None = None) -> Element:
    src = await get_or_404(db, element_id)
    parent_id = src.parent_id if target_parent_id is None else target_parent_id
    name = tree_service.require_name(new_name or f"{src.element_name} 副本")
    clone = await create(db, project_id=src.project_id, parent_id=parent_id,
                         element_name=name, node_type=src.node_type,
                         description=src.description, memo=src.memo)
    for loc in await locator_repo.list_by_element(db, src.id):
        db.add(ElementLocator(
            element_id=clone.id, platform=loc.platform, engine_key=loc.engine_key,
            locator_type=loc.locator_type, locator_value=loc.locator_value,
            priority=loc.priority, is_primary=loc.is_primary,
            status=loc.status, probe_detail=loc.probe_detail, enabled=loc.enabled,
            remark=loc.remark,
        ))
    await db.commit()
    await db.refresh(clone)
    return clone


async def list_tree(db: AsyncSession, project_id: int, *, parent_id: int | None = None,
                    keyword: str | None = None) -> dict:
    """一次查全量 + 内存组装（不走逐层递归，避免 8 次往返）。"""
    counts = await element_repo.locator_counts(db, project_id)

    if keyword:
        rows = await element_repo.search(db, project_id, keyword)
        by_id = {r.id: r for r in await element_repo.list_by_project(db, project_id)}
        items = []
        for row in rows:
            names = [by_id[i].element_name for i in
                     (int(p) for p in row.path.strip("/").split("/") if p) if i in by_id]
            items.append({"node": row, "path_names": names})
        return {"flat": items, "total": len(items), "counts": counts}

    rows = await element_repo.list_by_project(db, project_id)
    nodes = {r.id: {"node": r, "children": [], "locator_count": counts.get(r.id, {})}
             for r in rows}
    roots: list[dict] = []
    for row in rows:
        bucket = nodes[row.id]
        if row.parent_id and row.parent_id in nodes:
            nodes[row.parent_id]["children"].append(bucket)
        elif parent_id in (None, 0):
            roots.append(bucket)

    if parent_id:
        root = nodes.get(parent_id)
        return {"items": [root] if root else [], "total": 1, "counts": counts}
    return {"items": roots, "total": len(rows), "counts": counts}


async def stats(db: AsyncSession, project_id: int) -> dict:
    counts = await element_repo.locator_counts(db, project_id)
    total = sum(1 for _ in counts)
    coverage = {
        platform: {
            "configured": sum(1 for c in counts.values() if c.get(platform, 0) > 0),
            "missing": sum(1 for c in counts.values() if c.get(platform, 0) == 0),
        }
        for platform in ("WEB", "ANDROID", "IOS")
    }
    return {"total_elements": total, "coverage": coverage}


async def resolve_chain_for(db: AsyncSession, element_id: int, platform: str,
                            engine_key: str):
    """给执行器/验证器用：解析回退链。"""
    from app.engines.resolver import LocatorResolver
    from app.repositories.locator_repo import locator_repo as repo

    class _DbRepo:
        async def find_locators(self, eid, p, e):
            return await repo.find_locators(db, eid, p, e)

        async def list_platforms(self, eid):
            return await repo.list_platforms(db, eid)

    return await LocatorResolver(_DbRepo()).resolve_optional(element_id, platform, engine_key)
