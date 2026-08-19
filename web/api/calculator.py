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


class SolutionPrepRequest(BaseModel):
    reagent: str = Field(..., min_length=1, max_length=120)
    molarity: float = Field(..., gt=0)
    volume: float = Field(..., gt=0)
    volume_unit: str = Field(default="L", pattern="^(L|mL)$")
    purity: float = Field(default=100.0, gt=0, le=100)


@router.post("/solution-prep")
def solution_prep(payload: SolutionPrepRequest):
    handler = lab_tools._REGISTRY["calculate_solution_prep"]["handler"]
    try:
        return handler(
            payload.reagent,
            payload.molarity,
            payload.volume,
            payload.volume_unit,
            payload.purity,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class DilutionRequest(BaseModel):
    stock_concentration: float = Field(..., gt=0)
    final_concentration: float = Field(..., gt=0)
    final_volume: float = Field(..., gt=0)
    volume_unit: str = Field(default="mL", pattern="^(L|mL)$")


@router.post("/dilution")
def dilution(payload: DilutionRequest):
    handler = lab_tools._REGISTRY["calculate_dilution"]["handler"]
    try:
        return handler(
            payload.stock_concentration,
            payload.final_concentration,
            payload.final_volume,
            payload.volume_unit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
