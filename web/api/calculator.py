# -*- coding: utf-8 -*-
"""分子量计算接口：基于开源库 molmass，失败回退内置解析器。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import lab_tools

router = APIRouter(prefix="/calculator", tags=["calculator"])


class MolecularWeightRequest(BaseModel):
    reagent: str = Field(..., min_length=1, max_length=120, description="试剂名或化学式")


class MolecularWeightResponse(BaseModel):
    found: bool
    name: str | None = None
    formula: str | None = None
    molecular_weight: float | None = None
    unit: str = "g/mol"
    source: str = ""


@router.post("/molecular-weight", response_model=MolecularWeightResponse)
def molecular_weight(payload: MolecularWeightRequest):
    handler = lab_tools._REGISTRY["calculate_molecular_weight"]["handler"]
    try:
        result = handler(payload.reagent)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return MolecularWeightResponse(**result)
