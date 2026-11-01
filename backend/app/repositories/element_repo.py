"""元素仓储：树形查询与**子树路径重写**。

``rewrite_path_prefix`` 是全项目最危险的一条 SQL：写错了不报错，只是整棵树的 path 静默错位。
"""
from __future__ import annotations

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Element, ElementLocator


class ElementRepository:
    async def get(self, db: AsyncSession, element_id: int, *,
                  include_deleted: bool = False) -> Element | None:
        stmt = select(Element).where(Element.id == element_id)
        if not include_deleted:
            stmt = stmt.where(Element.is_deleted.is_(False))
        return (await db.execute(stmt)).scalar_one_or_none()

    async def list_by_project(self, db: AsyncSession, project_id: int) -> list[Element]:
        stmt = (select(Element)
                .where(Element.project_id == project_id, Element.is_deleted.is_(False))
                .order_by(Element.parent_id, Element.sort, Element.id))
        return list((await db.execute(stmt)).scalars().all())

    async def search(self, db: AsyncSession, project_id: int, keyword: str) -> list[Element]:
        stmt = (select(Element)
                .where(Element.project_id == project_id, Element.is_deleted.is_(False),
                       Element.element_name.like(f"%{keyword}%"))
                .order_by(Element.path)
                .limit(200))
        return list((await db.execute(stmt)).scalars().all())

    async def children(self, db: AsyncSession, project_id: int,
                       parent_id: int) -> list[Element]:
        stmt = (select(Element)
                .where(Element.project_id == project_id, Element.parent_id == parent_id,
                       Element.is_deleted.is_(False))
                .order_by(Element.sort, Element.id))
        return list((await db.execute(stmt)).scalars().all())

    async def count_children(self, db: AsyncSession, project_id: int, parent_id: int) -> int:
        stmt = (select(func.count(Element.id))
                .where(Element.project_id == project_id, Element.parent_id == parent_id,
                       Element.is_deleted.is_(False)))
        return (await db.execute(stmt)).scalar_one()

    async def name_exists(self, db: AsyncSession, project_id: int, parent_id: int,
                          name: str, *, exclude_id: int | None = None) -> int | None:
        stmt = (select(Element.id)
                .where(Element.project_id == project_id, Element.parent_id == parent_id,
                       Element.element_name == name, Element.is_deleted.is_(False)))
        if exclude_id is not None:
            stmt = stmt.where(Element.id != exclude_id)
        return (await db.execute(stmt.limit(1))).scalar_one_or_none()

    async def subtree(self, db: AsyncSession, project_id: int, path_prefix: str) -> list[Element]:
        stmt = (select(Element)
                .where(Element.project_id == project_id, Element.is_deleted.is_(False),
                       Element.path.like(f"{path_prefix}%"))
                .order_by(Element.path))
        return list((await db.execute(stmt)).scalars().all())

    async def rewrite_path_prefix(self, db: AsyncSession, project_id: int,
                                  old_prefix: str, new_prefix: str) -> int:
        """一条 UPDATE 重写整棵子树的 path（含自身）。

        ``SUBSTRING(path, old_len + 1)`` 取"旧前缀之后"的部分（MySQL/SQLite 均为 1-based）。
        用 ``LIKE 'old%'`` 而不是全表扫 —— 走 ``idx_element_path``。
        """
        stmt = text(
            "UPDATE element "
            "SET path = " + ("CONCAT(:new_prefix, SUBSTR(path, :cut))"
                             if db.get_bind().dialect.name != "sqlite"
                             else ":new_prefix || SUBSTR(path, :cut)") + " "
            "WHERE project_id = :project_id AND path LIKE :like"
        )
        result = await db.execute(stmt, {
            "new_prefix": new_prefix,
            "cut": len(old_prefix) + 1,
            "project_id": project_id,
            "like": f"{old_prefix}%",
        })
        return result.rowcount or 0

    async def set_sort_batch(self, db: AsyncSession, ordered_ids: list[int]) -> None:
        for index, element_id in enumerate(ordered_ids, start=1):
            await db.execute(update(Element).where(Element.id == element_id)
                             .values(sort=index * 10))

    async def locator_counts(self, db: AsyncSession, project_id: int) -> dict[int, dict[str, int]]:
        """一次 LEFT JOIN + GROUP BY 拿全项目覆盖度（避免 N+1）。"""
        stmt = (select(Element.id,
                       ElementLocator.platform,
                       func.count(ElementLocator.id))
                .outerjoin(ElementLocator,
                           (ElementLocator.element_id == Element.id)
                           & (ElementLocator.enabled.is_(True)))
                .where(Element.project_id == project_id, Element.is_deleted.is_(False))
                .group_by(Element.id, ElementLocator.platform))
        counts: dict[int, dict[str, int]] = {}
        for element_id, platform, count in (await db.execute(stmt)).all():
            bucket = counts.setdefault(int(element_id), {"WEB": 0, "ANDROID": 0, "IOS": 0})
            if platform:
                bucket[str(platform)] = int(count)
        return counts


element_repo = ElementRepository()
