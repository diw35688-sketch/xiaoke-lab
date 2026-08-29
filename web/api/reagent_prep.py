# -*- coding: utf-8 -*-
"""试剂配置库接口：查询、上传与逐步配置流程。"""

from contextlib import closing

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import domain
import llm_bridge
from database.db import get_connection

router = APIRouter(prefix="/reagent-prep", tags=["试剂配置库"])


class UploadPayload(BaseModel):
    reagent_preps: list


class AiDraftPayload(BaseModel):
    text: str


class SaveDraftPayload(BaseModel):
    reagent_prep: dict


class UpdatePrepPayload(BaseModel):
    reagent_prep: dict


class FlowStartPayload(BaseModel):
    conversation_id: str
    reagent_prep_id: str


class FlowMovePayload(BaseModel):
    conversation_id: str
    action: str  # next / prev / complete / jump


def _flow_view(conversation_id: str, prep_id: str) -> dict:
    prep = domain.reagent_preps().get_by_id(prep_id)
    if prep is None:
        raise HTTPException(status_code=404, detail="没有这种试剂配置。")
    steps = list(prep.steps or [])
    prep_view = domain.reagent_prep_view(prep)
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT current_index, status FROM reagent_prep_flows WHERE conversation_id=?",
            (conversation_id,),
        ).fetchone()
    current_index = int(row["current_index"] or 0) if row else 0
    status = (row["status"] if row else "running")
    return {
        "conversation_id": conversation_id,
        "prep_id": prep_id,
        "current_index": current_index,
        "status": status,
        "total_steps": len(steps),
        "step": steps[current_index] if steps and current_index < len(steps) else None,
        "steps": steps,
        "safety": prep_view.get("safety", []),
    }


@router.post("/flow/start")
def start_flow(payload: FlowStartPayload):
    prep = domain.reagent_preps().get_by_id(payload.reagent_prep_id)
    if prep is None:
        raise HTTPException(status_code=404, detail="没有这种试剂配置。")
    with closing(get_connection()) as connection, connection:
        connection.execute(
            """INSERT INTO reagent_prep_flows(conversation_id, prep_id, current_index, status, updated_at)
               VALUES(?, ?, 0, 'running', CURRENT_TIMESTAMP)
               ON CONFLICT(conversation_id) DO UPDATE SET
                 prep_id=excluded.prep_id,
                 current_index=0,
                 status='running',
                 updated_at=CURRENT_TIMESTAMP""",
            (payload.conversation_id, payload.reagent_prep_id),
        )
    return _flow_view(payload.conversation_id, payload.reagent_prep_id)


@router.get("/flow/current")
def current_flow(conversation_id: str):
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT prep_id FROM reagent_prep_flows WHERE conversation_id=?",
            (conversation_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="当前没有进行中的配置流程。")
    return _flow_view(conversation_id, row["prep_id"])


@router.post("/flow/move")
def move_flow(payload: FlowMovePayload):
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT prep_id, current_index, status FROM reagent_prep_flows WHERE conversation_id=?",
            (payload.conversation_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="当前没有进行中的配置流程。")
    prep = domain.reagent_preps().get_by_id(row["prep_id"])
    if prep is None:
        raise HTTPException(status_code=404, detail="没有这种试剂配置。")
    steps = list(prep.steps or [])
    index = int(row["current_index"] or 0)
    status = row["status"]
    action = payload.action
    if action == "next":
        index = min(index + 1, len(steps) - 1) if steps else 0
    elif action == "prev":
        index = max(index - 1, 0)
    elif action == "complete":
        status = "completed"
    elif action == "jump":
        pass  # 不支持任意跳转，保持当前
    else:
        raise HTTPException(status_code=400, detail="不支持的配置流程动作。")
    with closing(get_connection()) as connection, connection:
        connection.execute(
            "UPDATE reagent_prep_flows SET current_index=?, status=?, updated_at=CURRENT_TIMESTAMP WHERE conversation_id=?",
            (index, status, payload.conversation_id),
        )
    return _flow_view(payload.conversation_id, row["prep_id"])


@router.get("")
def list_reagent_preps():
    """全部试剂配置方案。"""
    return {
        "items": [
            domain.reagent_prep_view(prep)
            for prep in domain.reagent_preps().list_all()
        ]
    }


@router.get("/{reagent_prep_id}")
def read_reagent_prep(reagent_prep_id: str):
    """单条试剂配置方案。"""
    prep = domain.reagent_preps().get_by_id(reagent_prep_id)
    if prep is None:
        raise HTTPException(status_code=404, detail="没有这种试剂配置。")
    return domain.reagent_prep_view(prep)


@router.post("/ai-draft")
def ai_draft(payload: AiDraftPayload):
    """用户粘贴/上传文字，AI 生成试剂配置草稿，不落盘。"""
    try:
        return llm_bridge.generate_reagent_prep_draft(payload.text)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.post("/save-draft")
def save_draft(payload: SaveDraftPayload):
    """确认保存 AI 生成的试剂配置草稿。"""
    try:
        return domain.add_reagent_prep(payload.reagent_prep)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.patch("/{reagent_prep_id}")
def update_reagent_prep(reagent_prep_id: str, payload: UpdatePrepPayload):
    """按ID更新一条试剂配置，严格校验。"""
    try:
        return domain.update_reagent_prep(reagent_prep_id, payload.reagent_prep)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.delete("/{reagent_prep_id}")
def delete_reagent_prep(reagent_prep_id: str):
    """删除一条试剂配置。"""
    try:
        return domain.delete_reagent_prep(reagent_prep_id)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.post("/upload")
def upload_reagent_preps(payload: UploadPayload):
    """用户上传试剂配置 JSON 数组，严格校验后写库。"""
    try:
        return domain.add_reagent_preps(payload.reagent_preps)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))
