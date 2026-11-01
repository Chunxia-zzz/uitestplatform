"""回退链解析（M1 V6 的排序行为表）。"""
from __future__ import annotations

import pytest

from app.engines.resolver import InMemoryLocatorRepository, LocatorResolver, LocatorRow


def row(id_, engine, priority, ltype="css", value="x", element_id=101, platform="ANDROID"):
    return LocatorRow(id=id_, element_id=element_id, platform=platform, engine_key=engine,
                      locator_type=ltype, locator_value=value, priority=priority)


@pytest.mark.asyncio
async def test_exact_engine_wins_over_wildcard_even_with_larger_priority():
    repo = InMemoryLocatorRepository([
        row(1, "*", 10), row(2, "appium", 100),
    ])
    chain = await LocatorResolver(repo).resolve(101, "ANDROID", "appium")
    assert [l.locator_id for l in chain.locators] == [2, 1]


@pytest.mark.asyncio
async def test_priority_ascending_within_group():
    repo = InMemoryLocatorRepository([
        row(1, "appium", 100), row(2, "appium", 10), row(3, "appium", 50),
    ])
    chain = await LocatorResolver(repo).resolve(101, "ANDROID", "appium")
    assert [l.locator_id for l in chain.locators] == [2, 3, 1]


@pytest.mark.asyncio
async def test_tie_broken_by_id_for_stability():
    repo = InMemoryLocatorRepository([row(9, "*", 10), row(4, "*", 10)])
    chain = await LocatorResolver(repo).resolve(101, "ANDROID", "appium")
    assert [l.locator_id for l in chain.locators] == [4, 9]


@pytest.mark.asyncio
async def test_disabled_rows_are_skipped():
    disabled = LocatorRow(id=1, element_id=101, platform="ANDROID", engine_key="appium",
                          locator_type="css", locator_value="x", priority=10, enabled=False)
    repo = InMemoryLocatorRepository([disabled, row(2, "appium", 20)])
    chain = await LocatorResolver(repo).resolve(101, "ANDROID", "appium")
    assert [l.locator_id for l in chain.locators] == [2]


@pytest.mark.asyncio
async def test_empty_chain_raises_with_configured_platforms():
    repo = InMemoryLocatorRepository([row(1, "appium", 10, platform="IOS")])
    with pytest.raises(Exception) as exc:
        await LocatorResolver(repo).resolve_optional(101, "ANDROID", "appium")
    assert "IOS" in str(exc.value)
