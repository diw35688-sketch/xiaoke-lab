# -*- coding: utf-8 -*-
"""社区：发布、浏览、导入通用试剂配方与实验方案。"""
import json
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from api.auth import require_user
from attribution import signature_of
from pydantic import BaseModel

from src.core.reagent_prep import ReagentPrep
from src.storage.protocol_store import ProtocolStore, ProtocolStoreError

import domain
from community_sync import sync_remote_to_local
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


class ImportUrlPayload(BaseModel):
    url: str


class CommentPayload(BaseModel):
    content: str


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


def _validate_template(kind: str, content: dict) -> None:
    """发布/导入前按正式模板合同校验，无效模板不允许进入社区库。"""
    if kind == "reagent_prep":
        ReagentPrep.from_dict(content)
        return
    if kind == "protocol":
        try:
            ProtocolStore._parse_protocol(content, index=1)
        except ProtocolStoreError as error:
            raise ValueError(f"方案模板不满足标准：{error}")
        return
    raise ValueError("未知模板类型")


@router.get("")
def list_community(q: str = "", kind: str = "", limit: int = 200):
    items = crud.list_community_entries(q=q, kind=kind, limit=min(limit, 500))
    if not items and not q and not kind:
        # 本地还没有模板时，把远程社区已有模板同步进来（只同步一次，靠标题去重）。
        try:
            sync_remote_to_local()
        except Exception:
            pass
        items = crud.list_community_entries(q=q, kind=kind, limit=min(limit, 500))
    return {"items": items}


@router.post("")
def publish(payload: PublishPayload, user=Depends(require_user)):
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
    try:
        _validate_template(kind, content)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=f"模板不满足标准：{error}")
    # 作者取自登录态，不再信客户端传来的 author：
    # 原先谁都能以任意名字投稿，署名等于没有约束力。
    author_id, author_name = signature_of(user)
    row = crud.create_community_entry(
        kind=kind,
        title=title,
        content_json=json.dumps(content, ensure_ascii=False),
        author=author_name or payload.author.strip(),
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


@router.post("/import-url")
def import_from_url(payload: ImportUrlPayload, user=Depends(require_user)):
    """从外部链接抓取一份 JSON 模板，校验后导入本地（已有同 ID 则覆盖）。"""
    import httpx
    try:
        response = httpx.get(
            payload.url.strip(), timeout=20, follow_redirects=True, trust_env=False
        )
        response.raise_for_status()
        doc = response.json()
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"无法读取链接内容：{error}")
    if not isinstance(doc, dict):
        raise HTTPException(status_code=400, detail="链接内容必须是 JSON 对象")
    content = doc.get("content") if isinstance(doc.get("content"), dict) else doc
    kind = str(doc.get("kind") or "").strip()
    if not kind:
        if "reagent_prep_id" in content:
            kind = "reagent_prep"
        elif "protocol_id" in content and "steps" in content:
            kind = "protocol"
    if kind not in ("reagent_prep", "protocol"):
        raise HTTPException(status_code=400, detail="无法识别模板类型，需为 reagent_prep 或 protocol")
    try:
        _validate_template(kind, content)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=f"模板不满足标准：{error}")
    try:
        if kind == "reagent_prep":
            prep_id = content.get("reagent_prep_id", "")
            if prep_id and domain.reagent_preps().get_by_id(prep_id) is not None:
                saved = domain.update_reagent_prep(prep_id, content)
            else:
                saved = domain.add_reagent_prep(content)
        else:
            saved = domain.upsert_protocol(content)
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"导入失败：{error}")
    return {
        "ok": True,
        "saved": saved,
        "kind": kind,
        "title": doc.get("title") or content.get("name_zh") or content.get("title") or "",
    }


@router.delete("/{entry_id}")
def delete_entry(entry_id: int):
    # 目前先允许直接删除；后续可加作者/管理员鉴权
    ok = crud.delete_community_entry(entry_id)
    if not ok:
        raise HTTPException(status_code=404, detail="社区条目不存在")
    return {"ok": True}


@router.post("/{entry_id}/like")
def like_entry(entry_id: int, user=Depends(require_user)):
    row = crud.get_community_entry(entry_id)
    if not row:
        raise HTTPException(status_code=404, detail="社区条目不存在")
    result = crud.toggle_community_like(entry_id, user["id"])
    return {"ok": True, **result}


@router.get("/{entry_id}/comments")
def list_comments(entry_id: int):
    row = crud.get_community_entry(entry_id)
    if not row:
        raise HTTPException(status_code=404, detail="社区条目不存在")
    return {"items": crud.list_community_comments(entry_id)}


@router.post("/{entry_id}/comments")
def add_comment(entry_id: int, payload: CommentPayload, user=Depends(require_user)):
    row = crud.get_community_entry(entry_id)
    if not row:
        raise HTTPException(status_code=404, detail="社区条目不存在")
    try:
        comment = crud.add_community_comment(
            entry_id, user["id"], user.get("display_name") or user.get("username") or "", payload.content
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return {"ok": True, "comment": comment}


@router.delete("/comments/{comment_id}")
def delete_comment(comment_id: int, user=Depends(require_user)):
    is_admin = bool(user.get("is_admin"))
    if not crud.delete_community_comment(comment_id, user["id"], is_admin=is_admin):
        raise HTTPException(status_code=403, detail="没有权限删除该评论。")
    return {"ok": True}
