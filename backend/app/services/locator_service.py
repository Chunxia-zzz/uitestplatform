"""定位符服务：三层写入校验 / 批量 / priority 重排 / is_primary 唯一。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    BatchLimitExceeded, ElementFolderHasNoLocator, ElementLocatorDuplicated,
    ElementLocatorNotFound, ElementLocatorTypeEngineUnsupported,
    ElementLocatorTypeInvalid, ElementLocatorWildcardUnscoped, ProjectPlatformEngineMismatch,
)
from app.domain.enums import PLATFORM_ENGINES, LocatorStatus, NodeType
from app.domain.locator_types import LOCATOR_TYPES, default_priority, get_spec, platform_engines
from app.models import ElementLocator
from app.repositories.locator_repo import locator_repo
from app.services.element_service import get_or_404


def validate_type(platform: str, engine_key: str, locator_type: str):
    """三层校验，**顺序不能乱**（决定用户看到哪条报错）。

    1. 类型是否属于该平台
    2. 该类型是否被目标引擎支持
    3. engine_key='*' 时，该类型是否被平台**全部**引擎支持
    """
    if platform not in PLATFORM_ENGINES:
        raise ElementLocatorTypeInvalid(f"未知平台 {platform}", {"platform": platform})
    if engine_key != "*" and engine_key not in PLATFORM_ENGINES[platform]:
        raise ProjectPlatformEngineMismatch(
            f"引擎 {engine_key} 不支持平台 {platform}",
            {"platform": platform, "engine_key": engine_key,
             "supported_engines": sorted(PLATFORM_ENGINES[platform])},
        )

    spec = get_spec(platform, locator_type)
    if spec is None:
        raise ElementLocatorTypeInvalid(
            f"定位类型 {locator_type} 不属于平台 {platform}",
            {"platform": platform, "locator_type": locator_type,
             "allowed": sorted(LOCATOR_TYPES[platform].types)},
        )

    if engine_key != "*" and engine_key not in spec.engines:
        raise ElementLocatorTypeEngineUnsupported(
            f"定位类型 {locator_type} 不被引擎 {engine_key} 支持",
            {"locator_type": locator_type, "engine_key": engine_key,
             "supported_engines": sorted(spec.engines)},
        )

    if engine_key == "*" and spec.engines != platform_engines(platform):
        only = sorted(spec.engines)
        raise ElementLocatorWildcardUnscoped(
            f"定位类型 {locator_type} 仅 {', '.join(only)} 支持，不能用于 engine_key='*'；"
            f"请显式指定 engine_key，或改用通用类型（如 resource_id）",
            {"locator_type": locator_type, "only_engines": only},
        )
    return spec


async def _require_element(db: AsyncSession, element_id: int):
    element = await get_or_404(db, element_id)
    if element.node_type == NodeType.FOLDER:
        raise ElementFolderHasNoLocator(
            f"目录 {element_id} 不能配置定位符", {"element_id": element_id})
    return element


async def create(db: AsyncSession, *, element_id: int, platform: str, engine_key: str,
                 locator_type: str, locator_value: str,
                 priority: int | None = None) -> ElementLocator:
    await _require_element(db, element_id)
    validate_type(platform, engine_key, locator_type)

    value = (locator_value or "").strip()
    if not value:
        raise ElementLocatorTypeInvalid("定位值不能为空", {"locator_value": locator_value})

    dup = await locator_repo.exists_same(
        db, element_id=element_id, platform=platform, engine_key=engine_key,
        locator_type=locator_type, locator_value=value)
    if dup:
        raise ElementLocatorDuplicated(
            "同一定位符已存在", {"existing_id": dup, "locator_value": value})

    group = await locator_repo.group_rows(db, element_id, platform, engine_key)
    locator = ElementLocator(
        element_id=element_id, platform=platform, engine_key=engine_key,
        locator_type=locator_type, locator_value=value,
        priority=priority if priority is not None else default_priority(platform, locator_type),
        is_primary=not group,                      # 组内第一条自动设为首选
        status=LocatorStatus.UNVERIFIED,
    )
    db.add(locator)
    await db.commit()
    await db.refresh(locator)
    return locator


async def create_bulk(db: AsyncSession, element_id: int, items: list[dict]) -> dict:
    """批量新增：**事务粒度按条**，允许 207 部分成功。

    理由：用户一次配三端时，若 iOS 那条类型写错，不该让 Web/Android 也白填。
    """
    if len(items) > 50:
        raise BatchLimitExceeded("单次最多新增 50 条定位符", {"limit": 50, "actual": len(items)})

    created: list[int] = []
    failed: list[dict] = []
    for index, item in enumerate(items):
        try:
            locator = await create(
                db, element_id=element_id,
                platform=item["platform"], engine_key=item.get("engine_key", "*"),
                locator_type=item["locator_type"], locator_value=item["locator_value"],
                priority=item.get("priority"),
            )
            created.append(locator.id)
        except Exception as exc:                     # noqa: BLE001 —— 逐条报告，不中断
            failed.append({
                "index": index,
                "code": getattr(exc, "code", "ERROR"),
                "message": getattr(exc, "message", str(exc)),
                "detail": getattr(exc, "detail", {}),
            })
    return {"created": created, "failed": failed}


async def update(db: AsyncSession, locator_id: int, *, locator_value: str | None = None,
                 enabled: bool | None = None, remark: str | None = None) -> ElementLocator:
    locator = await locator_repo.get(db, locator_id)
    if locator is None:
        raise ElementLocatorNotFound(f"定位符 {locator_id} 不存在", {"locator_id": locator_id})

    if locator_value is not None and locator_value.strip() != locator.locator_value:
        value = locator_value.strip()
        validate_type(str(locator.platform), locator.engine_key, locator.locator_type)
        dup = await locator_repo.exists_same(
            db, element_id=locator.element_id, platform=str(locator.platform),
            engine_key=locator.engine_key, locator_type=locator.locator_type,
            locator_value=value, exclude_id=locator.id)
        if dup:
            raise ElementLocatorDuplicated("同一定位符已存在", {"existing_id": dup})
        locator.locator_value = value
        locator.status = LocatorStatus.UNVERIFIED
        locator.probe_detail = None

    if enabled is not None:
        locator.enabled = enabled
    if remark is not None:
        locator.remark = remark

    await db.commit()
    await db.refresh(locator)
    return locator


async def delete(db: AsyncSession, locator_id: int) -> None:
    if not await locator_repo.delete(db, locator_id):
        raise ElementLocatorNotFound(f"定位符 {locator_id} 不存在", {"locator_id": locator_id})
    await db.commit()


async def reorder(db: AsyncSession, element_id: int, platform: str, engine_key: str,
                  ordered_ids: list[int]) -> None:
    from app.services.tree_service import assert_order_complete
    current = await locator_repo.ids_in_group(db, element_id, platform, engine_key)
    assert_order_complete(current, ordered_ids)
    for index, locator_id in enumerate(ordered_ids, start=1):
        await locator_repo.set_priority(db, locator_id, index * 10)
    await db.commit()


async def set_primary(db: AsyncSession, locator_id: int) -> ElementLocator:
    locator = await locator_repo.get(db, locator_id)
    if locator is None:
        raise ElementLocatorNotFound(f"定位符 {locator_id} 不存在", {"locator_id": locator_id})
    await locator_repo.clear_primary(db, locator.element_id, str(locator.platform),
                                     locator.engine_key)
    await locator_repo.set_primary(db, locator.id)
    await db.commit()
    await db.refresh(locator)
    return locator


async def group_payload(db: AsyncSession, element_id: int) -> dict:
    """按 (platform, engine_key) 分组返回；**空组也要有**（前端要稳定渲染三个 tab）。"""
    rows = await locator_repo.list_by_element(db, element_id)
    groups: dict[tuple[str, str], list[ElementLocator]] = {}
    for row in rows:
        groups.setdefault((str(row.platform), row.engine_key), []).append(row)

    payload = []
    for (platform, engine_key), items in sorted(groups.items()):
        payload.append({
            "platform": platform,
            "engine_key": engine_key,
            "primary_id": next((i.id for i in items if i.is_primary), None),
            "items": items,
        })
    coverage = {p: 0 for p in PLATFORM_ENGINES}
    for row in rows:
        coverage[str(row.platform)] = coverage.get(str(row.platform), 0) + 1
    return {"element_id": element_id, "groups": payload, "coverage": coverage}


def mark_verified(locator: ElementLocator, *, matched: int, verdict: str,
                  sample: dict | None, error: str | None) -> None:
    """验证结果落库（M2 §2.8.4）：**只有确定无效才落 INVALID**。

    ``matched > 1`` 只写 probe_detail 供 UI 警告 —— 列表页定位符本来就会命中多行，
    一律标红会让用户不再相信这个功能。
    """
    locator.verified_at = datetime.now()
    locator.probe_detail = {
        "matched": matched, "verdict": verdict, "sample": sample,
        "error": error, "at": datetime.now().isoformat(timespec="seconds"),
    }
    if matched == 1 and not error:
        locator.status = LocatorStatus.VALID
    elif matched == 0 or error:
        locator.status = LocatorStatus.INVALID
    # matched > 1：保持原 status 不变
