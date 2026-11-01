"""定位符仓储（实现 LocatorResolver 依赖的 Protocol）。"""
from __future__ import annotations

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.resolver import LocatorRow
from app.models import ElementLocator


class LocatorRepository:
    async def get(self, db: AsyncSession, locator_id: int) -> ElementLocator | None:
        return (await db.execute(
            select(ElementLocator).where(ElementLocator.id == locator_id)
        )).scalar_one_or_none()

    async def list_by_element(self, db: AsyncSession, element_id: int) -> list[ElementLocator]:
        stmt = (select(ElementLocator)
                .where(ElementLocator.element_id == element_id)
                .order_by(ElementLocator.platform, ElementLocator.engine_key,
                          ElementLocator.priority, ElementLocator.id))
        return list((await db.execute(stmt)).scalars().all())

    async def group_rows(self, db: AsyncSession, element_id: int, platform: str,
                         engine_key: str) -> list[ElementLocator]:
        stmt = (select(ElementLocator)
                .where(ElementLocator.element_id == element_id,
                       ElementLocator.platform == platform,
                       ElementLocator.engine_key == engine_key)
                .order_by(ElementLocator.priority, ElementLocator.id))
        return list((await db.execute(stmt)).scalars().all())

    async def ids_in_group(self, db: AsyncSession, element_id: int, platform: str,
                           engine_key: str) -> list[int]:
        return [int(r.id) for r in await self.group_rows(db, element_id, platform, engine_key)]

    # ── LocatorResolver Protocol ────────────────────────────
    async def find_locators(self, db: AsyncSession, element_id: int, platform: str,
                            engine_key: str) -> list[LocatorRow]:
        stmt = (select(ElementLocator)
                .where(ElementLocator.element_id == element_id,
                       ElementLocator.platform == platform,
                       ElementLocator.engine_key.in_([engine_key, "*"]))
                .order_by(ElementLocator.priority, ElementLocator.id))
        rows = (await db.execute(stmt)).scalars().all()
        return [LocatorRow(id=r.id, element_id=r.element_id, platform=str(r.platform),
                           engine_key=r.engine_key, locator_type=r.locator_type,
                           locator_value=r.locator_value, priority=r.priority,
                           enabled=bool(r.enabled)) for r in rows]

    async def list_platforms(self, db: AsyncSession, element_id: int) -> list[str]:
        stmt = select(ElementLocator.platform).where(ElementLocator.element_id == element_id)
        return sorted({str(p) for p in (await db.execute(stmt)).scalars().all()})

    async def exists_same(self, db: AsyncSession, *, element_id: int, platform: str,
                          engine_key: str, locator_type: str, locator_value: str,
                          exclude_id: int | None = None) -> int | None:
        stmt = (select(ElementLocator.id)
                .where(ElementLocator.element_id == element_id,
                       ElementLocator.platform == platform,
                       ElementLocator.engine_key == engine_key,
                       ElementLocator.locator_type == locator_type,
                       ElementLocator.locator_value == locator_value))
        if exclude_id is not None:
            stmt = stmt.where(ElementLocator.id != exclude_id)
        return (await db.execute(stmt.limit(1))).scalar_one_or_none()

    async def count_by_element(self, db: AsyncSession, element_id: int) -> int:
        stmt = select(func.count(ElementLocator.id)).where(
            ElementLocator.element_id == element_id)
        return (await db.execute(stmt)).scalar_one()

    async def set_priority(self, db: AsyncSession, locator_id: int, priority: int) -> None:
        await db.execute(update(ElementLocator).where(ElementLocator.id == locator_id)
                         .values(priority=priority))

    async def clear_primary(self, db: AsyncSession, element_id: int, platform: str,
                            engine_key: str) -> None:
        await db.execute(update(ElementLocator)
                         .where(ElementLocator.element_id == element_id,
                                ElementLocator.platform == platform,
                                ElementLocator.engine_key == engine_key)
                         .values(is_primary=False))

    async def set_primary(self, db: AsyncSession, locator_id: int) -> None:
        await db.execute(update(ElementLocator).where(ElementLocator.id == locator_id)
                         .values(is_primary=True))

    async def delete_by_element(self, db: AsyncSession, element_id: int) -> int:
        result = await db.execute(
            delete(ElementLocator).where(ElementLocator.element_id == element_id))
        return result.rowcount or 0

    async def delete(self, db: AsyncSession, locator_id: int) -> int:
        result = await db.execute(
            delete(ElementLocator).where(ElementLocator.id == locator_id))
        return result.rowcount or 0


locator_repo = LocatorRepository()
