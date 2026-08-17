# -*- coding: utf-8 -*-
"""试剂配置库接口：查询与上传。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import domain
import llm_bridge

router = APIRouter(prefix="/reagent-prep", tags=["试剂配置库"])


class UploadPayload(BaseModel):
    reagent_preps: list


class AiDraftPayload(BaseModel):
    text: str


class SaveDraftPayload(BaseModel):
    reagent_prep: dict


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


@router.post("/upload")
def upload_reagent_preps(payload: UploadPayload):
    """用户上传试剂配置 JSON 数组，严格校验后写库。"""
    try:
        return domain.add_reagent_preps(payload.reagent_preps)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))
