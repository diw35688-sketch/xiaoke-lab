# -*- coding: utf-8 -*-
"""模型设置接口：任何人都能在网页里配置模型，无需接触服务器文件。"""

from fastapi import APIRouter
from pydantic import BaseModel

import settings_store
import qwen_audio_bridge

router = APIRouter(prefix="/settings", tags=["设置"])


class ModelsPayload(BaseModel):
    base_url: str | None = None
    api_key: str | None = None
    provider_id: str | None = None
    provider_label: str | None = None


class ProviderPayload(BaseModel):
    provider_id: str
    label: str = ""
    base_url: str = ""
    model: str = ""
    api_key: str = ""


class SettingsPayload(BaseModel):
    api_key: str | None = None
    provider_id: str | None = None
    base_url: str | None = None
    model_name: str | None = None
    thinking_level: str | None = None
    dashscope_api_key: str | None = None
    dashscope_realtime_model: str | None = None
    tts_enabled: bool | None = None
    speak_record_ack: bool | None = None
    tts_url: str | None = None
    tts_provider: str | None = None
    tts_api_key: str | None = None
    tts_base_url: str | None = None
    tts_model: str | None = None
    tts_voice: str | None = None
    tts_speed: float | None = None
    tts_access_key: str | None = None
    tts_secret_key: str | None = None
    tts_ark_api_key: str | None = None
    mineru_file_parse_url: str | None = None
    mineru_api_key: str | None = None
    ocr_base_url: str | None = None
    ocr_api_key: str | None = None
    ocr_model: str | None = None
    heartbeat_enabled: bool | None = None
    heartbeat_time: str | None = None
    owner_profile: dict | None = None


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


@router.get("/qwen-audio")
def qwen_audio_status():
    """查看 QwenAudio 实时语音服务状态。"""
    return qwen_audio_bridge.status()


@router.post("/qwen-audio/start")
def qwen_audio_start():
    """用本项目设置的 DashScope Key 启动 QwenAudio 实时语音。"""
    return qwen_audio_bridge.start()


@router.post("/test")
def test_settings(payload: SettingsPayload | None = None):
    """真实调用一次接口，验证配置是否可用。"""
    if payload and (payload.api_key or payload.base_url or payload.model_name):
        current = settings_store.current()
        candidate = settings_store.ModelSettings(
            api_key=payload.api_key or current.key_for(payload.provider_id),
            base_url=payload.base_url or current.base_url,
            model_name=payload.model_name or current.model_name,
        )
        ok, message = settings_store.test_connection(candidate)
    else:
        ok, message = settings_store.test_connection()
    return {"ok": ok, "message": message}


@router.get("/providers")
def read_providers():
    return {"items": settings_store.list_providers(), "settings": settings_store.current().masked()}


@router.post("/providers")
def add_provider(payload: ProviderPayload):
    try:
        updated = settings_store.add_provider(
            provider_id=payload.provider_id,
            label=payload.label,
            base_url=payload.base_url,
            model=payload.model,
            api_key=payload.api_key,
        )
    except ValueError as error:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(error))
    return {"items": settings_store.list_providers(), "settings": updated.masked()}


@router.delete("/providers/{provider_id}")
def delete_provider(provider_id: str):
    settings_store.delete_provider(provider_id)
    return {"items": settings_store.list_providers(), "settings": settings_store.current().masked()}


@router.post("/models")
def fetch_models(payload: ModelsPayload | None = None):
    """从当前/候选接口地址拉取可用模型列表。"""
    try:
        models = settings_store.fetch_models(
            base_url=payload.base_url if payload else None,
            api_key=payload.api_key if payload else None,
            provider_id=payload.provider_id if payload else None,
        )
        return {"models": models, "catalog": settings_store.catalog_for_models(models)}
    except Exception as error:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(error))


@router.delete("/api-key")
def delete_api_key():
    """清除密钥，用于更换账号。"""
    updated = settings_store.clear_api_key()
    return {"settings": updated.masked(), "message": "密钥已清除"}
