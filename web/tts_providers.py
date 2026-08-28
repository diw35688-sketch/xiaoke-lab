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
        "api_url": "https://platform.openai.com/api_keys",
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
        "api_url": "https://bailian.console.aliyun.com/?tab=apiKey",
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
    {
        "id": "volcano", "label": "火山引擎豆包语音",
        "needs_key": True, "server_side": True,
        "default_base_url": "https://openspeech.bytedance.com/api/v1/tts",
        "default_model": "volcano_tts",
        "api_url": "https://console.volcengine.com/speech/app",
        "note": "密钥填 appid:access_token（冒号分隔）。「合成模型」框填控制台 cluster（默认 volcano_tts）。音色为火山官方中文女声/童声（免费21款内为主），可自由切换试听。",
        "voices": [
            {"id": "BV001_streaming", "label": "通用女声（亲切，12种情感）"},
            {"id": "BV001_V2_streaming", "label": "通用女声 2.0"},
            {"id": "BV700_streaming", "label": "灿灿（22种情感）"},
            {"id": "BV700_V2_streaming", "label": "灿灿 2.0（22种情感）"},
            {"id": "BV705_streaming", "label": "炀炀"},
            {"id": "BV405_streaming", "label": "甜美小源（智能助手）"},
            {"id": "BV007_streaming", "label": "亲切女声"},
            {"id": "BV009_streaming", "label": "知性女声"},
            {"id": "BV005_streaming", "label": "活泼女声"},
            {"id": "BV406_streaming", "label": "超自然音色-梓梓"},
            {"id": "BV406_V2_streaming", "label": "超自然音色-梓梓 2.0"},
            {"id": "BV428_streaming", "label": "清新文艺女声"},
            {"id": "BV104_streaming", "label": "温柔淑女"},
            {"id": "BV113_streaming", "label": "甜宠少御"},
            {"id": "BV115_streaming", "label": "古风少御"},
            {"id": "BV011_streaming", "label": "新闻女声"},
            {"id": "BV402_streaming", "label": "促销女声"},
            {"id": "BV403_streaming", "label": "鸡汤女声"},
            {"id": "BV412_streaming", "label": "影视解说小美"},
            {"id": "BV418_streaming", "label": "直播一姐"},
            {"id": "BV034_streaming", "label": "知性姐姐-双语"},
            {"id": "BV064_streaming", "label": "小萝莉"},
            {"id": "BV061_streaming", "label": "天才童声"},
        ],
    },
]


def provider_meta(provider_id: str) -> dict:
    for item in PROVIDERS:
        if item["id"] == provider_id:
            return item
    return PROVIDERS[0]


# 百炼等供应商没有稳定的 /models 列表，提供经过验证的常用模型。
_STATIC_TTS_MODELS = {
    "dashscope": ["cosyvoice-v2", "cosyvoice-v1", "sambert-zhichu-v1"],
    "openai": ["tts-1", "tts-1-hd"],
    "local_qwen": ["qwen3-tts-flash", "qwen3-tts-12hz"],
    "edge": [],
    "browser": [],
}


def fetch_models(
    provider_id: str,
    base_url: str | None = None,
    api_key: str | None = None,
) -> list[str]:
    """拉取语音合成模型。

    OpenAI 兼容供应商会真实请求 /models 并优先返回 tts 前缀模型；
    其他供应商返回已验证的静态模型列表。
    """

    if provider_id in {"browser", "edge"}:
        return []

    static_models = _STATIC_TTS_MODELS.get(provider_id, [])
    if provider_id != "openai":
        return static_models

    url = (base_url or "https://api.openai.com/v1").rstrip("/")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    try:
        response = httpx.get(
            url + "/models",
            headers=headers,
            timeout=httpx.Timeout(20, connect=8),
            trust_env=False,
        )
    except Exception as error:
        # 拉不到时回退到静态已知模型，不阻塞用户保存。
        return static_models
    if response.status_code != 200:
        return static_models
    try:
        data = response.json()
        items = data.get("data", data)
        models = [
            item.get("id", "")
            for item in items
            if isinstance(item, dict)
        ]
        models = [m for m in models if m]
    except Exception:
        return static_models
    tts_models = [m for m in models if m.startswith("tts")]
    if tts_models:
        return sorted(set(tts_models))
    return sorted(set(models)) if models else static_models


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


def _volcano(text: str, settings) -> bytes:
    """火山引擎豆包语音（小模型 HTTP 非流式接口）。

    密钥格式：appid:access_token（填在 tts_api_key，冒号分隔）。
    参考：https://docs.volcengine.com/docs/6561/79820（请求参数）
         https://docs.volcengine.com/docs/6561/1105162（鉴权方法）
    """
    import base64
    import uuid

    raw_key = settings.tts_api_key or ""
    if ":" not in raw_key:
        raise RuntimeError("火山引擎密钥格式应为 appid:access_token（中间用冒号）")
    appid, token = raw_key.split(":", 1)
    appid = appid.strip()
    token = token.strip()
    if not appid or not token:
        raise RuntimeError("火山引擎 appid 或 access_token 为空")

    base = (settings.tts_base_url or "https://openspeech.bytedance.com/api/v1/tts").rstrip("/")
    # cluster 是控制台申请分配的（官方 FAQ Q1 可查），不是写死的；
    # 用 tts_model 字段承载（火山接口没有 model 概念），默认 volcano_tts。
    cluster = (settings.tts_model or "volcano_tts").strip() or "volcano_tts"
    payload = {
        "app": {"appid": appid, "token": token, "cluster": cluster},
        "user": {"uid": "web_lab_assistant"},
        "audio": {
            "voice_type": settings.tts_voice or "BV001_streaming",
            "encoding": "mp3",
            "speed_ratio": float(settings.tts_speed or 1.0),
            "volume_ratio": 1.0,
            "pitch_ratio": 1.0,
        },
        "request": {
            "reqid": uuid.uuid4().hex,
            "text": text,
            "text_type": "plain",
            "operation": "query",
            "with_frontend": 1,
            "frontend_type": "unitTson",
        },
    }
    response = httpx.post(
        base,
        headers={"Authorization": f"Bearer;{token}"},
        json=payload,
        timeout=httpx.Timeout(60, connect=10),
    )
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        # 透传火山响应体（code/message），失败要能定位而不是只看到 401
        body_text = ""
        try:
            body_text = response.text[:200]
        except Exception:
            pass
        raise RuntimeError(
            f"火山引擎 HTTP {response.status_code}：{body_text}"
        ) from error
    data = response.json()
    code = data.get("code", -1)
    if code != 3000:
        raise RuntimeError(
            "火山引擎返回错误：code=" + str(code) + " " + str(data.get("message", ""))[:120]
        )
    audio_b64 = data.get("data", "")
    if not audio_b64:
        raise RuntimeError("火山引擎响应中没有音频数据：" + str(data)[:200])
    return base64.b64decode(audio_b64)


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
    if provider == "volcano":
        return _volcano(text, settings), "audio/mpeg"
    raise RuntimeError("未知的语音合成供应商：" + str(provider))
