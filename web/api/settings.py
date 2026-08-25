# -*- coding: utf-8 -*-
"""模型设置接口：任何人都能在网页里配置模型，无需接触服务器文件。"""

from fastapi import APIRouter
from pydantic import BaseModel

import settings_store

router = APIRouter(prefix="/settings", tags=["设置"])


class SettingsPayload(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    model_name: str | None = None
    tts_enabled: bool | None = None
    speak_record_ack: bool | None = None
    tts_url: str | None = None
    tts_provider: str | None = None
    tts_api_key: str | None = None
    tts_base_url: str | None = None
    tts_model: str | None = None
    tts_voice: str | None = None
    tts_speed: float | None = None


@router.get("")
def read_settings():
    """返回当前设置（密钥掩码）与可选预设。"""
    current = settings_store.current()
    return {
        "settings": current.masked(),
        "presets": settings_store.PRESETS,
        "ready": current.is_ready(),
        "missing": current.missing(),
    }


@router.put("")
def save_settings(payload: SettingsPayload):
    """保存设置并立即生效。api_key 留空表示保持原值。"""
    updated = settings_store.update(**payload.model_dump())
    return {
        "settings": updated.masked(),
        "ready": updated.is_ready(),
        "missing": updated.missing(),
        "message": "设置已保存，立即生效",
    }


@router.post("/test")
def test_settings(payload: SettingsPayload | None = None):
    """真实调用一次接口，验证配置是否可用。"""
    if payload and (payload.api_key or payload.base_url or payload.model_name):
        candidate = settings_store.ModelSettings(
            api_key=payload.api_key or settings_store.current().api_key,
            base_url=payload.base_url or settings_store.current().base_url,
            model_name=payload.model_name or settings_store.current().model_name,
        )
        ok, message = settings_store.test_connection(candidate)
    else:
        ok, message = settings_store.test_connection()
    return {"ok": ok, "message": message}


@router.delete("/api-key")
def delete_api_key():
    """清除密钥，用于更换账号。"""
    updated = settings_store.clear_api_key()
    return {"settings": updated.masked(), "message": "密钥已清除"}
