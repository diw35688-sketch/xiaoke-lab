# -*- coding: utf-8 -*-
"""语音识别接口：浏览器上传 WAV，服务端用 SenseVoice 转写。

比浏览器自带 Web Speech API 的优势：中文实验术语更准、不依赖浏览器厂商
的云服务、断网也能用。模型只在首次请求时加载一次。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile, File

from asr_application_service import (
    AudioValidationError,
    get_asr_application_service,
)

router = APIRouter(prefix="/asr", tags=["语音识别"])

@router.get("/status")
def status():
    """告诉前端 ASR 是否可用，未加载时不触发加载。"""
    return get_asr_application_service().status()


@router.post("/warmup")
def warmup():
    """显式预热：把首次加载的等待放在用户点击时，而不是第一句话时。"""
    try:
        return get_asr_application_service().warmup()
    except Exception as error:
        raise HTTPException(status_code=503, detail=str(error))


@router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """接收 16kHz 单声道 WAV，返回转写文本。"""
    payload = await audio.read()
    if not payload:
        raise HTTPException(status_code=400, detail="音频为空")

    try:
        recognized = get_asr_application_service().recognize_upload(
            payload,
            conversation_id="legacy-asr",
            request_id=f"legacy-{id(audio)}",
            lab_session_id=None,
            retain=False,
        )
        result = recognized.result
        return {
            "transcript": result.asr_transcript,
            "raw_text": result.asr_model_raw_text,
            "duration_seconds": result.audio_duration_seconds,
        }
    except AudioValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail="识别失败：" + str(error))
