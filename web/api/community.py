# -*- coding: utf-8 -*-
"""社区：发布、浏览、导入通用试剂配方与实验方案。"""
import json
import re
import uuid

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

import domain
from database import crud

router = APIRouter(prefix="/community")


class PublishPayload(BaseModel):
    kind: str
    title: str
    content: dict
    author: str = ""
    tags: str = ""


class ImportPayload(BaseModel):
    # 导入时前端不需要额外内容，由后端按 entry_id 读取
    pass


def _new_unique_id(base_id: str) -> str:
    if not base_id:
        return "community-" + uuid.uuid4().hex[:12]
    existing_reagent = {p.reagent_prep_id for p in domain.reagent_preps().list_all()}
    existing_protocol = {p.protocol_id for p in domain.protocols().list_all()}
    if base_id not in existing_reagent and base_id not in existing_protocol:
        return base_id
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", base_id).strip("-") or "community"
    i = 2
    while f"{slug}-community-{i}" in existing_reagent or f"{slug}-community-{i}" in existing_protocol:
        i += 1
    return f"{slug}-community-{i}"


@router.get("")
def list_community(q: str = "", kind: str = "", limit: int = 200):
    return {"items": crud.list_community_entries(q=q, kind=kind, limit=min(limit, 500))}


@router.post("")
def publish(payload: PublishPayload):
    kind = payload.kind.strip()
    if kind not in ("reagent_prep", "protocol"):
        raise HTTPException(status_code=400, detail="kind 只支持 reagent_prep 或 protocol")
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="标题不能为空")
    content = payload.content
    if not isinstance(content, dict):
        raise HTTPException(status_code=400, detail="content 必须是 JSON 对象")
    try:
        json.dumps(content, ensure_ascii=False)
    except Exception:
        raise HTTPException(status_code=400, detail="content 不是合法 JSON")
    row = crud.create_community_entry(
        kind=kind,
        title=title,
        content_json=json.dumps(content, ensure_ascii=False),
        author=payload.author.strip(),
        tags=payload.tags.strip(),
    )
    return {"ok": True, "entry": row}


@router.get("/{entry_id}")
def get_entry(entry_id: int):
    row = crud.get_community_entry(entry_id)
    if not row:
        raise HTTPException(status_code=404, detail="社区条目不存在")
    row["content"] = json.loads(row["content_json"])
    return {"entry": row}


@router.post("/{entry_id}/import")
def import_entry(entry_id: int):
    row = crud.get_community_entry(entry_id)
    if not row:
        raise HTTPException(status_code=404, detail="社区条目不存在")
    content = json.loads(row["content_json"])
    # 给导入的副本一个新 id，避免覆盖本地已有条目
    if row["kind"] == "reagent_prep":
        content["reagent_prep_id"] = _new_unique_id(content.get("reagent_prep_id", ""))
        try:
            saved = domain.add_reagent_prep(content)
        except Exception as error:
            raise HTTPException(status_code=400, detail=f"导入失败：{error}")
    elif row["kind"] == "protocol":
        content["protocol_id"] = _new_unique_id(content.get("protocol_id", ""))
        try:
            saved = domain.add_protocol(content)
        except Exception as error:
            raise HTTPException(status_code=400, detail=f"导入失败：{error}")
    else:
        raise HTTPException(status_code=400, detail="未知类型")
    crud.increment_community_downloads(entry_id)
    return {"ok": True, "saved": saved}


@router.delete("/{entry_id}")
def delete_entry(entry_id: int):
    # 目前先允许直接删除；后续可加作者/管理员鉴权
    ok = crud.delete_community_entry(entry_id)
    if not ok:
        raise HTTPException(status_code=404, detail="社区条目不存在")
    return {"ok": True}
