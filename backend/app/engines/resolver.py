"""LocatorResolver —— 把 (element_id, platform, engine_key) 解析成有序回退链。

排序规则（M1 FR9 冻结）：
  1) ``engine_key`` 精确匹配 **优先于** ``'*'`` 通配（即使通配的 priority 更小）
  2) 同组内按 ``priority`` 升序（小的先试）
  3) 完全并列按 ``id`` 升序（保证结果稳定可复现）
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core.errors import LocatorNotFoundError
from app.engines.base import Locator, LocatorChain, Platform


@dataclass(frozen=True, slots=True)
class LocatorRow:
    """element_locator 的一行（含通配行）。"""
    id: int
    element_id: int
    platform: str
    engine_key: str
    locator_type: str
    locator_value: str
    priority: int
    enabled: bool = True


class LocatorRepositoryLike(Protocol):
    async def find_locators(self, element_id: int, platform: str,
                            engine_key: str) -> list[LocatorRow]: ...

    async def list_platforms(self, element_id: int) -> list[str]: ...


class LocatorResolver:
    """数据获取通过注入的 repo 完成 —— 便于单测用内存数据。"""

    def __init__(self, repo: LocatorRepositoryLike) -> None:
        self._repo = repo

    async def resolve(self, element_id: int, platform: Platform | str,
                      engine_key: str) -> LocatorChain:
        rows = await self._repo.find_locators(element_id, str(platform), engine_key)
        return self._build(element_id, rows, engine_key)

    async def resolve_optional(self, element_id: int | None, platform: Platform | str,
                               engine_key: str) -> LocatorChain | None:
        """``requires_element=0`` 的步骤传 None，直接返回 None。"""
        if element_id is None:
            return None
        chain = await self.resolve(element_id, platform, engine_key)
        if not chain:
            configured = await self._repo.list_platforms(element_id)
            raise LocatorNotFoundError(
                f"元素 {element_id} 在 platform={platform}, engine={engine_key} 下无任何定位符；"
                f"该元素已配置的端：{configured}",
                {"element_id": element_id, "platform": str(platform),
                 "engine_key": engine_key, "configured_platforms": configured},
            )
        return chain

    @staticmethod
    def _build(element_id: int, rows: list[LocatorRow], engine_key: str) -> LocatorChain:
        enabled = [r for r in rows if r.enabled]
        # 精确(0) 先于通配(1)；再 priority；再 id 稳定
        enabled.sort(key=lambda r: (0 if r.engine_key == engine_key else 1, r.priority, r.id))
        return LocatorChain.of(
            element_id,
            [Locator(type=r.locator_type, value=r.locator_value, locator_id=r.id)
             for r in enabled],
        )


class InMemoryLocatorRepository:
    """内存实现（单测 / 契约测试用）。"""

    def __init__(self, rows: list[LocatorRow] | None = None) -> None:
        self._rows = rows or []

    async def find_locators(self, element_id: int, platform: str,
                            engine_key: str) -> list[LocatorRow]:
        return [r for r in self._rows
                if r.element_id == element_id and r.platform == platform
                and r.engine_key in (engine_key, "*")]

    async def list_platforms(self, element_id: int) -> list[str]:
        return sorted({r.platform for r in self._rows if r.element_id == element_id})
