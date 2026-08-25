# -*- coding: utf-8 -*-
"""语音识别接口：浏览器上传 WAV，服务端用 SenseVoice 转写。

比浏览器自带 Web Speech API 的优势：中文实验术语更准、不依赖浏览器厂商
的云服务、断网也能用。模型只在首次请求时加载一次。
"""

from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File

router = APIRouter(prefix="/asr", tags=["语音识别"])

_lock = threading.Lock()
_backend = None
_load_error: str | None = None
_load_ms: int | None = None


def _get_backend():
    """惰性加载 ASR 模型：首次调用才加载，避免拖慢服务启动。"""
    global _backend, _load_error, _load_ms
    with _lock:
        if _backend is not None:
            return _backend
        if _load_error is not None:
            raise RuntimeError(_load_error)
        try:
            started = time.perf_counter()
            import domain  # noqa: F401  确保仓库根目录已在 sys.path
            from src.asr.factory import create_asr_backend

            _backend = create_asr_backend()
            _load_ms = round((time.perf_counter() - started) * 1000)
            return _backend
        except Exception as error:
            _load_error = f"{type(error).__name__}: {error}"
            raise RuntimeError(_load_error) from error


@router.get("/status")
def status():
    """告诉前端 ASR 是否可用，未加载时不触发加载。"""
    return {
        "loaded": _backend is not None,
        "error": _load_error,
        "engine": "SenseVoiceSmall",
        "load_ms": _load_ms,
    }


@router.post("/warmup")
def warmup():
    """显式预热：把首次加载的等待放在用户点击时，而不是第一句话时。"""
    try:
        _get_backend()
    except Exception as error:
        raise HTTPException(status_code=503, detail=str(error))
    return {"loaded": True, "engine": "SenseVoiceSmall", "load_ms": _load_ms}


@router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """接收 16kHz 单声道 WAV，返回转写文本。"""
    payload = await audio.read()
    if not payload:
        raise HTTPException(status_code=400, detail="音频为空")

    try:
        backend = _get_backend()
    except Exception as error:
        raise HTTPException(status_code=503, detail="ASR 模型不可用：" + str(error))

    temp_dir = Path(tempfile.mkdtemp(prefix="asr_web_"))
    audio_path = temp_dir / "segment.wav"
    try:
        audio_path.write_bytes(payload)
        result = backend.recognize(audio_path)
        return {
            "transcript": result.asr_transcript,
            "raw_text": getattr(result, "model_raw_text", None),
            "duration_seconds": getattr(result, "audio_duration_seconds", None),
        }
    except Exception as error:
        raise HTTPException(status_code=500, detail="识别失败：" + str(error))
    finally:
        try:
            audio_path.unlink(missing_ok=True)
            temp_dir.rmdir()
        except OSError:
            pass
