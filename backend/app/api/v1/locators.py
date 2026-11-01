"""定位符端点（M2 §3.3 L1–L7）。"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.errors import ValidationFailed
from app.schemas.requests import LocatorOrder, LocatorUpdate, VerifyRequest
from app.schemas.serialize import locator_group_to_dict, locator_to_dict
from app.services import locator_service, locator_verify_service

router = APIRouter(tags=["locators"])


@router.get("/elements/{element_id}/locators")
async def list_locators(element_id: int, db: AsyncSession = Depends(get_session)):
    from app.services.element_service import get_or_404
    await get_or_404(db, element_id)
    data = await locator_service.group_payload(db, element_id)
    return {
        "element_id": element_id,
        "groups": [locator_group_to_dict(g) for g in data["groups"]],
        "coverage": data["coverage"],
    }


@router.post("/elements/{element_id}/locators", status_code=201)
async def create_locator(element_id: int, response: Response,
                         body: dict = Body(...),
                         db: AsyncSession = Depends(get_session)):
    """单条 → 201；批量（``bulk: true``）→ 207 逐条结果（允许部分成功）。"""
    if body.get("bulk"):
        result = await locator_service.create_bulk(db, element_id, body.get("items") or [])
        response.status_code = 207 if result["failed"] else 201
        if not result["failed"]:
            result["items"] = [locator_to_dict(await _get(db, i)) for i in result["created"]]
        return result

    try:
        platform = body["platform"]
        locator_type = body["locator_type"]
        locator_value = body["locator_value"]
    except KeyError as exc:
        raise ValidationFailed(f"缺少字段 {exc.args[0]}") from exc

    locator = await locator_service.create(
        db, element_id=element_id, platform=platform,
        engine_key=body.get("engine_key", "*"), locator_type=locator_type,
        locator_value=locator_value, priority=body.get("priority"),
    )
    return locator_to_dict(locator)


async def _get(db: AsyncSession, locator_id: int):
    from app.repositories.locator_repo import locator_repo
    return await locator_repo.get(db, locator_id)


@router.patch("/element-locators/{locator_id}")
async def update_locator(locator_id: int, body: LocatorUpdate,
                         db: AsyncSession = Depends(get_session)):
    locator = await locator_service.update(
        db, locator_id, locator_value=body.locator_value,
        enabled=body.enabled, remark=body.remark,
    )
    return locator_to_dict(locator)


@router.delete("/element-locators/{locator_id}", status_code=204)
async def delete_locator(locator_id: int, db: AsyncSession = Depends(get_session)):
    await locator_service.delete(db, locator_id)
    return Response(status_code=204)


@router.put("/elements/{element_id}/locators/order")
async def reorder_locators(element_id: int, body: LocatorOrder,
                           db: AsyncSession = Depends(get_session)):
    await locator_service.reorder(db, element_id, body.platform, body.engine_key,
                                   body.ordered_ids)
    return {"element_id": element_id, "ordered_ids": body.ordered_ids}


@router.post("/elements/{element_id}/locators:verify")
async def verify_locators(element_id: int, body: VerifyRequest,
                          db: AsyncSession = Depends(get_session)):
    return await locator_verify_service.verify(
        db, element_id, platform=body.platform, engine_key=body.engine_key,
        target_id=body.target_id, url=body.url, include_saved=body.include_saved,
        drafts=[d.model_dump() for d in body.drafts],
    )


@router.post("/element-locators/{locator_id}:set-primary")
async def set_primary(locator_id: int, db: AsyncSession = Depends(get_session)):
    locator = await locator_service.set_primary(db, locator_id)
    return locator_to_dict(locator)
