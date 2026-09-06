# -*- coding: utf-8 -*-
"""实验准备台接口：生成准备单、更新单项状态、设置整体状态。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import prep_bench_service

router = APIRouter(prefix="/prep-bench", tags=["准备台"])


class GeneratePayload(BaseModel):
    protocol_id: str
    scale_input: str | None = None


class UpdateItemPayload(BaseModel):
    manual_state: str  # have / missing / ""


class SetStatusPayload(BaseModel):
    status: str  # ready / skipped / preparing


class RescalePayload(BaseModel):
    user_scale: str  # 新规模，如 "20 个样本"


@router.post("/generate")
def generate_bench(payload: GeneratePayload):
    """从方案生成准备台草稿并落库。"""
    try:
        return prep_bench_service.generate_prep_bench(
            protocol_id=payload.protocol_id,
            scale_input=payload.scale_input,
        )
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.get("")
def get_bench():
    """读取当前会话最新的准备台。不存在返回 404。"""
    bench = prep_bench_service.get_prep_bench(None)
    if bench is None:
        raise HTTPException(status_code=404, detail="当前没有准备台。")
    return bench


@router.patch("/items/{prep_run_item_id}")
def update_item(prep_run_item_id: str, payload: UpdateItemPayload):
    """用户覆盖某一项的状态。"""
    try:
        return prep_bench_service.update_prep_item(
            prep_run_item_id, payload.manual_state
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.post("/status")
def set_status(payload: SetStatusPayload):
    """标记准备台整体状态。"""
    try:
        bench = prep_bench_service.get_prep_bench(None)
        if bench is None:
            raise HTTPException(status_code=404, detail="当前没有准备台。")
        return prep_bench_service.set_prep_run_status(
            bench["prep_run_id"], payload.status
        )
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.patch("/scale")
def rescale_bench(payload: RescalePayload):
    """用户改规模（如"做 20 个样本"），AI 按新规模重算每项用量。"""
    try:
        bench = prep_bench_service.get_prep_bench(None)
        if bench is None:
            raise HTTPException(status_code=404, detail="当前没有准备台。")
        return prep_bench_service.rescale_prep_bench(
            bench["prep_run_id"], payload.user_scale
        )
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))
