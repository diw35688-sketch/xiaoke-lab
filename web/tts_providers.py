# -*- coding: utf-8 -*-
"""多供应商语音合成：像调模型一样调 TTS，不在本机扛神经网络模型。

支持四类：
- browser      浏览器内置，离线、零配置、零延迟（由前端直接合成）
- edge         Edge TTS，免费、无需密钥、音质好，需联网
- openai       OpenAI 兼容 /audio/speech，适用于 OpenAI 及各类兼容网关
- dashscope    阿里云百炼 CosyVoice，国内访问快
- local_qwen   本机 Qwen3-TTS，音色可克隆，但需要显卡
"""

from __future__ import annotations

import asyncio
import io

import httpx

PROVIDERS = [
    {
        "id": "browser", "label": "浏览器内置（离线，免配置）",
        "needs_key": False, "server_side": False,
        "note": "零延迟、不联网、任何机器都能用；音色一般。",
        "voices": [],
    },
    {
        "id": "edge", "label": "Edge TTS（免费，需联网）",
        "needs_key": False, "server_side": True,
        "note": "微软在线合成，免费无需密钥，中文音色自然。实测首包约 2.3 秒。",
        "voices": [
            {"id": "zh-CN-XiaoxiaoNeural", "label": "晓晓（女，亲和）"},
            {"id": "zh-CN-YunxiNeural", "label": "云希（男，沉稳）"},
            {"id": "zh-CN-XiaoyiNeural", "label": "晓伊（女，活泼）"},
            {"id": "zh-CN-YunjianNeural", "label": "云健（男，浑厚）"},
            {"id": "zh-CN-liaoning-XiaobeiNeural", "label": "晓北（女，东北）"},
        ],
    },
    {
        "id": "openai", "label": "OpenAI 兼容 TTS（/audio/speech）",
        "needs_key": True, "server_side": True,
        "default_base_url": "https://api.openai.com/v1",
        "default_model": "tts-1",
        "note": "填入任何兼容 OpenAI 的网关地址即可，和配置对话模型同一种方式。",
        "voices": [
            {"id": "alloy", "label": "alloy"}, {"id": "nova", "label": "nova"},
            {"id": "shimmer", "label": "shimmer"}, {"id": "echo", "label": "echo"},
            {"id": "fable", "label": "fable"}, {"id": "onyx", "label": "onyx"},
        ],
    },
    {
        "id": "dashscope", "label": "阿里云百炼 CosyVoice",
        "needs_key": True, "server_side": True,
        "default_base_url": "https://dashscope.aliyuncs.com/api/v1",
        "default_model": "cosyvoice-v2",
        "note": "国内访问快；密钥在阿里云百炼控制台获取。",
        "voices": [
            {"id": "longxiaochun_v2", "label": "龙小淳（女）"},
            {"id": "longxiaoxia_v2", "label": "龙小夏（女）"},
            {"id": "longwan_v2", "label": "龙婉（女）"},
            {"id": "longcheng_v2", "label": "龙橙（男）"},
        ],
    },
    {
        "id": "local_qwen", "label": "本机 Qwen3-TTS（需显卡）",
        "needs_key": False, "server_side": True,
        "note": "音色可克隆，但需要 NVIDIA 显卡并单独启动 tts_server。无显卡时不要选。",
        "voices": [],
    },
]


def provider_meta(provider_id: str) -> dict:
    for item in PROVIDERS:
        if item["id"] == provider_id:
            return item
    return PROVIDERS[0]


async def _edge(text: str, voice: str, speed: float) -> bytes:
    import edge_tts

    rate = int(round((speed - 1.0) * 100))
    rate_text = ("+" if rate >= 0 else "") + str(rate) + "%"
    buffer = io.BytesIO()
    communicate = edge_tts.Communicate(
        text, voice or "zh-CN-XiaoxiaoNeural", rate=rate_text
    )
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buffer.write(chunk["data"])
    return buffer.getvalue()


def _openai(text: str, settings) -> bytes:
    base = (settings.tts_base_url or "https://api.openai.com/v1").rstrip("/")
    response = httpx.post(
        base + "/audio/speech",
        headers={
            "Authorization": "Bearer " + settings.tts_api_key,
            "Content-Type": "application/json",
        },
        json={
            "model": settings.tts_model or "tts-1",
            "input": text,
            "voice": settings.tts_voice or "alloy",
            "speed": settings.tts_speed,
        },
        timeout=httpx.Timeout(60, connect=10),
    )
    response.raise_for_status()
    return response.content


def _dashscope(text: str, settings) -> bytes:
    """阿里云百炼语音合成（HTTP 方式）。"""
    base = (settings.tts_base_url or "https://dashscope.aliyuncs.com/api/v1").rstrip("/")
    response = httpx.post(
        base + "/services/aigc/multimodal-generation/generation",
        headers={
            "Authorization": "Bearer " + settings.tts_api_key,
            "Content-Type": "application/json",
        },
        json={
            "model": settings.tts_model or "cosyvoice-v2",
            "input": {"text": text, "voice": settings.tts_voice or "longxiaochun_v2"},
            "parameters": {"text_type": "PlainText"},
        },
        timeout=httpx.Timeout(60, connect=10),
    )
    response.raise_for_status()
    data = response.json()
    audio_url = (
        data.get("output", {}).get("audio", {}).get("url")
        or data.get("output", {}).get("url")
    )
    if not audio_url:
        raise RuntimeError("百炼返回中没有音频地址：" + str(data)[:200])
    audio = httpx.get(audio_url, timeout=httpx.Timeout(60, connect=10))
    audio.raise_for_status()
    return audio.content


def _local_qwen(text: str, settings) -> bytes:
    response = httpx.post(
        settings.tts_url,
        json={"text": text},
        timeout=httpx.Timeout(300, connect=5),
        trust_env=False,
    )
    response.raise_for_status()
    return response.content


def synthesize(text: str, settings) -> tuple[bytes, str]:
    """按当前配置合成语音，返回 (音频字节, MIME)。"""
    provider = settings.tts_provider or "browser"
    if provider == "browser":
        raise RuntimeError("浏览器内置合成由前端直接完成，服务端不产出音频。")
    if provider == "edge":
        return asyncio.run(_edge(text, settings.tts_voice, settings.tts_speed)), "audio/mpeg"
    if provider == "openai":
        return _openai(text, settings), "audio/mpeg"
    if provider == "dashscope":
        return _dashscope(text, settings), "audio/mpeg"
    if provider == "local_qwen":
        return _local_qwen(text, settings), "audio/wav"
    raise RuntimeError("未知的语音合成供应商：" + str(provider))
