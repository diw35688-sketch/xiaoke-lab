# -*- coding: utf-8 -*-
"""实验前准备清单接口：生成清单并与储存库同步。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from checklist_service import generate_protocol_checklist

router = APIRouter(prefix="/checklists", tags=["准备清单"])


class ChecklistGeneratePayload(BaseModel):
    protocol_id: str


@router.post("/generate")
def generate_checklist(payload: ChecklistGeneratePayload):
    try:
        return generate_protocol_checklist(payload.protocol_id)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.get("/{protocol_id}")
def get_checklist(protocol_id: str):
    try:
        return generate_protocol_checklist(protocol_id)
    except Exception as error:
        raise HTTPException(status_code=404, detail=str(error))
