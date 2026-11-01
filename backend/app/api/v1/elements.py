"""元素端点（M2 §3.3 E1–E9）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.schemas.requests import ElementCreate, ElementMove, ElementUpdate, OrderUpdate
from app.schemas.serialize import element_to_dict, tree_node_to_dict
from app.services import element_service

router = APIRouter(tags=["elements"])


@router.get("/projects/{project_id}/elements")
async def list_elements(project_id: int, parent_id: int | None = None,
                        keyword: str | None = Query(default=None, min_length=1),
                        db: AsyncSession = Depends(get_session)):
    data = await element_service.list_tree(db, project_id, parent_id=parent_id, keyword=keyword)

    if "flat" in data:
        items = []
        for row in data["flat"]:
            payload = element_to_dict(row["node"],
                                      locator_count=data["counts"].get(row["node"].id))
            payload["path_names"] = row["path_names"]
            items.append(payload)
        return {"mode": "flat", "items": items, "total": data["total"]}

    return {
        "mode": "tree",
        "items": [tree_node_to_dict(node) for node in data["items"]],
        "total": data["total"],
    }


@router.post("/projects/{project_id}/elements", status_code=201)
async def create_element(project_id: int, body: ElementCreate,
                         db: AsyncSession = Depends(get_session)):
    node = await element_service.create(
        db, project_id=project_id, parent_id=body.parent_id,
        element_name=body.element_name, node_type=body.node_type,
        description=body.description, memo=body.memo,
    )
    return element_to_dict(node)


@router.get("/elements/{element_id}")
async def get_element(element_id: int, db: AsyncSession = Depends(get_session)):
    node = await element_service.get_or_404(db, element_id)
    from app.repositories.locator_repo import locator_repo
    rows = await locator_repo.list_by_element(db, element_id)
    coverage = {"WEB": 0, "ANDROID": 0, "IOS": 0}
    for row in rows:
        coverage[str(row.platform)] = coverage.get(str(row.platform), 0) + 1
    return element_to_dict(node, locator_count=coverage)


@router.patch("/elements/{element_id}")
async def update_element(element_id: int, body: ElementUpdate,
                         db: AsyncSession = Depends(get_session)):
    node = await element_service.update(
        db, element_id, element_name=body.element_name, description=body.description,
        memo=body.memo, node_type=body.node_type,
    )
    return element_to_dict(node)


@router.delete("/elements/{element_id}")
async def delete_element(element_id: int, force: bool = False,
                         db: AsyncSession = Depends(get_session)):
    return await element_service.delete(db, element_id, force=force)


@router.post("/elements/{element_id}/move")
async def move_element(element_id: int, body: ElementMove,
                       db: AsyncSession = Depends(get_session)):
    node = await element_service.move(db, element_id, new_parent_id=body.parent_id,
                                      index=body.index)
    return element_to_dict(node)


@router.put("/elements/{element_id}/children-order")
async def reorder_children(element_id: int, body: OrderUpdate,
                           db: AsyncSession = Depends(get_session)):
    await element_service.reorder_children(db, element_id, body.ordered_ids)
    return {"element_id": element_id, "ordered_ids": body.ordered_ids}


@router.get("/elements/{element_id}/references")
async def element_references(element_id: int, db: AsyncSession = Depends(get_session)):
    await element_service.get_or_404(db, element_id)
    return {"element_id": element_id, "references": await element_service.references(db, element_id)}


@router.post("/elements/{element_id}/duplicate", status_code=201)
async def duplicate_element(element_id: int, target_parent_id: int | None = None,
                            new_name: str | None = None,
                            db: AsyncSession = Depends(get_session)):
    node = await element_service.duplicate(db, element_id, target_parent_id=target_parent_id,
                                           new_name=new_name)
    return element_to_dict(node)
