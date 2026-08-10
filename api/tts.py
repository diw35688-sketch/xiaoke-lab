import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from config import LOCAL_QWEN_TTS_URL

router = APIRouter(prefix="/tts", tags=["语音"])


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@router.post("")
async def synthesize_speech(request: TTSRequest):
    """转发到本机 Qwen3-TTS，不再调用任何第三方 TTS。"""
    try:
        # 1.7B Base 首次生成较慢；禁用系统代理，始终直连 127.0.0.1。
        timeout = httpx.Timeout(300.0, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            upstream = await client.post(LOCAL_QWEN_TTS_URL, json={"text": request.text})
    except httpx.ConnectError as error:
        raise HTTPException(502, "无法连接本地 Qwen TTS。请确认 tts_server 已在 127.0.0.1:8001 运行。") from error
    except httpx.ReadTimeout as error:
        raise HTTPException(504, "本地 Qwen TTS 生成超时（超过 5 分钟）。请缩短回复内容，或检查显卡与模型加载状态。") from error
    except httpx.RequestError as error:
        raise HTTPException(502, f"本地 Qwen TTS 请求失败：{type(error).__name__}") from error
    if upstream.is_error:
        raise HTTPException(502, f"本地 Qwen TTS 生成失败（状态码 {upstream.status_code}）：{upstream.text[:200]}")
    return Response(content=upstream.content, media_type=upstream.headers.get("content-type", "audio/wav"))
