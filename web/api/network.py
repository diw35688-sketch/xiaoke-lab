# -*- coding: utf-8 -*-
"""网络模式接口：UI 里切换局域网 / 公网隧道。所有操作立即返回，状态用 /network/status 轮询。"""

from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

import network_mode

router = APIRouter(prefix="/network", tags=["网络"])


class ModePayload(BaseModel):
    mode: str


@router.get("/status")
def get_status():
    return network_mode.status()


@router.post("/mode")
def set_mode(payload: ModePayload):
    if payload.mode not in {"lan", "tunnel"}:
        raise HTTPException(status_code=400, detail="mode 必须是 lan 或 tunnel")
    try:
        result = network_mode.set_mode(payload.mode)
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    return result


@router.get("/set")
def set_mode_get(mode: str):
    if mode not in {"lan", "tunnel"}:
        raise HTTPException(status_code=400, detail="mode 必须是 lan 或 tunnel")
    try:
        result = network_mode.set_mode(mode)
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    if mode == "tunnel" and result.get("error"):
        return RedirectResponse(f"/phone?error={quote(result['error'])}", status_code=303)
    return RedirectResponse("/phone", status_code=303)
