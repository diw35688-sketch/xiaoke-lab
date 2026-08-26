# -*- coding: utf-8 -*-
"""语音合成接口：供应商可在界面里配置，和配置对话模型同一种方式。"""

from __future__ import annotations

import time
from dataclasses import replace

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

import settings_store
import tts_providers
from volcano_streaming_tts import (
    PCM_CHANNELS,
    PCM_SAMPLE_RATE,
    PCM_SAMPLE_WIDTH,
    VolcanoStreamConfig,
    VolcanoStreamingTTSError,
    volcano_streaming_tts,
)

router = APIRouter(prefix="/tts", tags=["语音合成"])


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    speed: float | None = Field(default=None, ge=0.5, le=2.0)


class TTSModelsPayload(BaseModel):
    provider: str | None = None
    base_url: str | None = None
    api_key: str | None = None


@router.get("/providers")
def providers():
    """可选供应商、音色与当前配置。"""
    current = settings_store.current()
    return {
        "providers": tts_providers.PROVIDERS,
        "current": {
            "provider": current.tts_provider,
            "voice": current.tts_voice,
            "speed": current.tts_speed,
            "enabled": current.tts_enabled,
            "speak_record_ack": current.speak_record_ack,
            "base_url": current.tts_base_url,
            "model": current.tts_model,
            "api_key_set": bool(current.tts_api_key),
        },
    }


@router.post("/models")
def models(payload: TTSModelsPayload | None = None):
    """拉取当前语音供应商可用的合成模型。"""
    settings = settings_store.current()
    provider = (payload.provider if payload else None) or settings.tts_provider or "browser"
    base_url = (payload.base_url if payload else None) or settings.tts_base_url
    api_key = (payload.api_key if payload else None) or settings.tts_api_key
    try:
        models = tts_providers.fetch_models(provider, base_url, api_key)
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error))
    return {"provider": provider, "models": models}


@router.post("")
def synthesize(request: TTSRequest):
    """合成一段语音；浏览器内置模式由前端处理，服务端明确告知。"""
    settings = settings_store.current()
    if (settings.tts_provider or "browser") == "browser":
        raise HTTPException(status_code=409, detail="当前使用浏览器内置合成")
    try:
        audio, mime = tts_providers.synthesize(request.text, settings)
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"{type(error).__name__}: {error}")
    return Response(content=audio, media_type=mime)


@router.post("/stream")
async def synthesize_stream(request: TTSRequest):
    """Stream the configured Volcengine voice as raw PCM chunks."""
    settings = settings_store.current()
    if settings.tts_provider != "volcano":
        raise HTTPException(
            status_code=409,
            detail="正式语音播放链路只支持已配置的火山流式 TTS",
        )
    try:
        config = VolcanoStreamConfig.from_settings(settings)
        if request.speed is not None:
            config = replace(config, speed=request.speed)
    except VolcanoStreamingTTSError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    print(f"[TTS-STREAM] request.speed={request.speed} config.speed={config.speed}", flush=True)

    async def audio_chunks():
        async for chunk in volcano_streaming_tts.stream(request.text, config):
            yield chunk

    return StreamingResponse(
        audio_chunks(),
        media_type="application/octet-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Audio-Format": "pcm_s16le",
            "X-Audio-Sample-Rate": str(PCM_SAMPLE_RATE),
            "X-Audio-Channels": str(PCM_CHANNELS),
            "X-Audio-Sample-Width": str(PCM_SAMPLE_WIDTH),
        },
    )


@router.post("/warmup")
async def warmup_stream():
    """Open the one production WebSocket before the first spoken turn."""
    settings = settings_store.current()
    if settings.tts_provider != "volcano":
        raise HTTPException(status_code=409, detail="当前未启用火山流式 TTS")
    try:
        config = VolcanoStreamConfig.from_settings(settings)
        await volcano_streaming_tts.warmup(config)
    except VolcanoStreamingTTSError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return {"ok": True, "provider": "volcano", "transport": "websocket"}


@router.post("/test")
def test():
    """真实合成一句话，返回是否成功与实测耗时。"""
    settings = settings_store.current()
    provider = settings.tts_provider or "browser"
    if provider == "browser":
        return {"ok": True, "message": "浏览器内置合成，无需服务端配置，零延迟",
                "seconds": 0.0}
    meta = tts_providers.provider_meta(provider)
    if meta["needs_key"] and not settings.tts_api_key:
        return {"ok": False, "message": "该供应商需要密钥，尚未填写", "seconds": 0.0}

    started = time.monotonic()
    try:
        audio, _ = tts_providers.synthesize("语音合成测试，实验记录已保存。", settings)
    except Exception as error:
        return {"ok": False,
                "message": f"{type(error).__name__}: {str(error)[:160]}",
                "seconds": round(time.monotonic() - started, 2)}
    seconds = round(time.monotonic() - started, 2)
    return {"ok": True,
            "message": f"合成成功，音频 {len(audio) // 1024} KB，耗时 {seconds} 秒",
            "seconds": seconds}
