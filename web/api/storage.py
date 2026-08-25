# -*- coding: utf-8 -*-
"""储存库接口：全局存储位置与存储物品资产库。"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from database import crud

router = APIRouter(prefix="/storage", tags=["储存库"])


class LocationPayload(BaseModel):
    name: str
    type: str = "其他"
    temperature: str = ""
    capacity: str = ""
    notes: str = ""
    enabled: bool = True


class LocationUpdatePayload(BaseModel):
    name: str | None = None
    type: str | None = None
    temperature: str | None = None
    capacity: str | None = None
    notes: str | None = None
    enabled: bool | None = None


class ItemPayload(BaseModel):
    item_type: str = "其他"
    name: str
    quantity: str = ""
    unit: str = ""
    concentration: str = ""
    location_id: int | None = None
    position: str = ""
    storage_condition: str = ""
    owner: str = ""
    source_experiment_id: str = ""
    stored_at: str = ""
    expires_at: str = ""
    status: str = "in_storage"
    notes: str = ""


class ItemUpdatePayload(BaseModel):
    item_type: str | None = None
    name: str | None = None
    quantity: str | None = None
    unit: str | None = None
    concentration: str | None = None
    location_id: int | None = None
    position: str | None = None
    storage_condition: str | None = None
    owner: str | None = None
    source_experiment_id: str | None = None
    stored_at: str | None = None
    expires_at: str | None = None
    status: str | None = None
    notes: str | None = None


@router.get("/stats")
def stats():
    return crud.storage_stats()


@router.get("/locations")
def locations():
    return {"items": crud.list_storage_locations()}


@router.post("/locations")
def create_location(payload: LocationPayload):
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="存储位置名称不能为空。")
    return crud.create_storage_location(payload.model_dump())


@router.patch("/locations/{location_id}")
def edit_location(location_id: int, payload: LocationUpdatePayload):
    try:
        result = crud.update_storage_location(location_id, payload.model_dump(exclude_none=True))
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))
    if result is None:
        raise HTTPException(status_code=404, detail="存储位置不存在。")
    return result


@router.delete("/locations/{location_id}")
def remove_location(location_id: int):
    if not crud.delete_storage_location(location_id):
        raise HTTPException(status_code=404, detail="存储位置不存在。")
    return {"ok": True}


@router.get("/items")
def items(
    q: str = Query(default=""),
    item_type: str = Query(default=""),
    location_id: str | None = Query(default=None),
    status: str = Query(default=""),
):
    loc_id = int(location_id) if location_id else None
    return {
        "items": crud.list_storage_items(q=q, item_type=item_type, location_id=loc_id, status=status)
    }


@router.post("/items")
def create_item(payload: ItemPayload):
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="存储物品名称不能为空。")
    return crud.create_storage_item(payload.model_dump())


@router.patch("/items/{item_id}")
def edit_item(item_id: int, payload: ItemUpdatePayload):
    data = payload.model_dump(exclude_none=True)
    # 允许将 location_id 显式置空
    if "location_id" in payload.model_fields_set:
        data["location_id"] = payload.location_id
    try:
        result = crud.update_storage_item(item_id, data)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))
    if result is None:
        raise HTTPException(status_code=404, detail="存储物品不存在。")
    return result


@router.delete("/items/{item_id}")
def remove_item(item_id: int):
    if not crud.delete_storage_item(item_id):
        raise HTTPException(status_code=404, detail="存储物品不存在。")
    return {"ok": True}
