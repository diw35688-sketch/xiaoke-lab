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
        "note": "推荐：填豆包语音控制台的 API Key（一个 Key），走 x-api-key 即可；旧版也可填 appid:access_token。",
        "voices": [
            {"id": "zh_female_vv_uranus_bigtts", "label": "seed-tts · 晴川（官方示例）"},
            {"id": "zh_male_M392_conversation_wvae_bigtts", "label": "seed-tts · 深沉男声（官方示例）"},
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
    # 只接受 volcano_ 开头的旧版 cluster；seed-tts 的 ep- 不属于旧接口 cluster。
    raw_model = (settings.tts_model or "").strip()
    cluster = raw_model if raw_model.startswith("volcano_") else "volcano_tts"
    request = {
        "reqid": uuid.uuid4().hex,
        "text": text,
        "text_type": "plain",
        "operation": "query",
        "with_frontend": 1,
        "frontend_type": "unitTson",
    }
    # 官方大模型语音合成（seed-tts）在 request.model 里可选模型版本，
    # 例如 seed-tts-1.1 / seed-tts-2.0；旧接口不需要 Endpoint ID。
    raw_model = (settings.tts_model or "").strip()
    if raw_model and raw_model.startswith(("seed-tts", "volcano_")):
        request["model"] = raw_model
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
        "request": request,
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


def _volcano_maas(text: str, settings) -> bytes:
    """火山方舟 MaaS 大模型语音合成（seed-tts）。

    文档接口：POST /api/v2/endpoint/{endpoint_id}/audio/speech
    使用 AK/SK 签名，请求体为 input / voice / response_format / speed。
    这是 seed-tts 等大模型音色的正确入口；旧 /api/v1/tts 会报
    `resource_id=tts.sync.level1 requested resource not granted`。

    这里不用 MaaS SDK 的 requests 传输：当前 Python 环境 urllib3/requests
    版本不匹配会导致所有 HTTPS 出现 SSLEOFError；改用 httpx 直连并复用
    SDK 的 V4 签名，避免“connection pool max retries”的误报。
    """
    import copy
    import json
    import uuid

    import httpx
    from volcengine.auth.SignerV4 import SignerV4
    from volcengine.maas.v2 import MaasService

    if not settings.tts_model:
        raise RuntimeError("火山方舟 MaaS 语音合成需要填写 Endpoint ID（当前“合成模型”为空）")
    if not settings.tts_access_key or not settings.tts_secret_key:
        raise RuntimeError(
            "火山方舟 MaaS 语音合成需要填写 Access Key 和 Secret Key，"
            "在火山引擎「访问控制」或控制台 API 密钥页获取"
        )

    host = (settings.tts_base_url or "maas-api.ml-platform-cn-beijing.volces.com").strip()
    if host.startswith("https://"):
        host = host[len("https://"):]
    if host.endswith("/"):
        host = host.rstrip("/")
    region = "cn-beijing"

    maas = MaasService(host, region)
    maas.set_ak(settings.tts_access_key.strip())
    maas.set_sk(settings.tts_secret_key.strip())

    api_info = copy.deepcopy(MaasService.get_api_info()["audio.speech"])
    api_info.path = api_info.path.format(endpoint_id=settings.tts_model.strip())
    request = maas.prepare_request(api_info, {})
    request.headers["x-tt-logid"] = uuid.uuid4().hex
    request.headers["Content-Type"] = "application/json"

    payload = {
        "input": text,
        "voice": (settings.tts_voice or "BV001_streaming").strip(),
        "response_format": "mp3",
        "speed": float(settings.tts_speed or 1.0),
    }
    request.body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    SignerV4.sign(request, maas.service_info.credentials)
    url = request.build()

    try:
        response = httpx.post(
            url,
            content=request.body,
            headers=dict(request.headers),
            timeout=httpx.Timeout(60, connect=10),
            trust_env=False,
        )
    except Exception as error:
        raise RuntimeError(f"火山方舟语音合成连接失败：{type(error).__name__}: {error}") from error

    if response.status_code != 200:
        try:
            detail = response.json()
        except Exception:
            detail = response.text[:200]
        if response.status_code == 502:
            detail = (
                "火山网关返回 502（TLB）。请确认「合成模型」填的是火山方舟"
                "语音 Endpoint ID（ep- 开头），不是 seed-tts 模型名；"
                "并确认该 Endpoint 已开通音频合成能力。原始响应："
                + str(detail)
            )
        raise RuntimeError(
            f"火山方舟语音合成失败：HTTP {response.status_code}: {detail}"
        )
    if not response.content:
        raise RuntimeError("火山方舟语音合成返回了空音频。")
    return response.content


def _volcano_ark_v3(text: str, settings) -> bytes:
    """火山方舟 Agent Plan 语音模型（seed-tts）HTTP 接口。

    官方推荐：只要「专属 API Key」一个密钥，不需要 AK/SK、不需要 Endpoint ID。
    接口：POST https://openspeech.bytedance.com/api/v3/plan/tts/unidirectional
    头：X-Api-Key / X-Api-Resource-Id（seed-tts-2.0）
    返回：NDJSON，每行 JSON 的 data 字段是 base64 音频分片。
    """
    import base64
    import json

    api_key = (settings.tts_ark_api_key or "").strip()
    if not api_key:
        raise RuntimeError("火山方舟 seed-tts 需要填写「专属 API Key」")
    resource_id = (settings.tts_model or "seed-tts-2.0").strip() or "seed-tts-2.0"
    speaker = (settings.tts_voice or "zh_female_vv_uranus_bigtts").strip()

    url = "https://openspeech.bytedance.com/api/v3/plan/tts/unidirectional"
    headers = {
        "X-Api-Key": api_key,
        "X-Api-Resource-Id": resource_id,
        "Content-Type": "application/json",
        "Connection": "keep-alive",
        "X-Control-Require-Usage-Tokens-Return": "*",
    }
    payload = {
        "req_params": {
            "text": text,
            "speaker": speaker,
            "audio_params": {"format": "mp3", "sample_rate": 24000},
        }
    }

    try:
        response = httpx.post(
            url, headers=headers, json=payload,
            timeout=httpx.Timeout(60, connect=10), trust_env=False,
        )
    except Exception as error:
        raise RuntimeError(
            f"火山方舟 seed-tts 连接失败：{type(error).__name__}: {error}"
        ) from error

    if response.status_code != 200:
        raise RuntimeError(
            f"火山方舟 seed-tts 失败：HTTP {response.status_code}: {response.text[:200]}"
        )

    audio = bytearray()
    for line in response.text.splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        code = int(data.get("code", 0) or 0)
        if code == 20000000:
            break
        if code > 0:
            raise RuntimeError(
                f"火山方舟 seed-tts 返回错误：code={code} message={data.get('message')}"
            )
        chunk = data.get("data")
        if chunk:
            audio.extend(base64.b64decode(chunk))
    if not audio:
        raise RuntimeError("火山方舟 seed-tts 未返回音频数据。")
    return bytes(audio)


def _volcano_speech_key(text: str, settings) -> bytes:
    """豆包语音控制台 API Key（x-api-key）直接调旧版 /api/v1/tts。

    官方文档「API Key使用」说明：在任意接口 Header 填：
        x-api-key: ${your-api-key}
    即可，不需要填 appid。旧接口请求体仍要求 app.appid，传占位 "0"
    即可，鉴权完全由 x-api-key 承担。
    """
    import base64
    import uuid

    api_key = (settings.tts_ark_api_key or "").strip()
    if not api_key:
        raise RuntimeError("需要填写豆包语音控制台的 API Key")
    url = "https://openspeech.bytedance.com/api/v1/tts"
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
    }
    raw_model = (settings.tts_model or "").strip()
    cluster = raw_model if raw_model.startswith("volcano_") else "volcano_tts"
    request = {
        "reqid": uuid.uuid4().hex,
        "text": text,
        "text_type": "plain",
        "operation": "query",
        "with_frontend": 1,
        "frontend_type": "unitTson",
    }
    if raw_model and raw_model.startswith(("seed-tts", "volcano_")):
        request["model"] = raw_model
    payload = {
        "app": {"appid": "0", "token": "0", "cluster": cluster},
        "user": {"uid": "web_lab_assistant"},
        "audio": {
            "voice_type": settings.tts_voice or "BV001_streaming",
            "encoding": "mp3",
            "speed_ratio": float(settings.tts_speed or 1.0),
            "volume_ratio": 1.0,
            "pitch_ratio": 1.0,
        },
        "request": request,
    }
    try:
        response = httpx.post(
            url, headers=headers, json=payload,
            timeout=httpx.Timeout(60, connect=10), trust_env=False,
        )
    except Exception as error:
        raise RuntimeError(
            f"豆包语音 API Key 连接失败：{type(error).__name__}: {error}"
        ) from error
    if response.status_code != 200:
        raise RuntimeError(
            f"豆包语音 API Key 失败：HTTP {response.status_code}: {response.text[:200]}"
        )
    data = response.json()
    code = int(data.get("code", -1))
    if code != 3000:
        raise RuntimeError(
            f"豆包语音 API Key 返回错误：code={code} message={data.get('message')}"
        )
    audio_b64 = data.get("data", "")
    if not audio_b64:
        raise RuntimeError("豆包语音 API Key 响应中没有音频数据。")
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
        model = (settings.tts_model or "").strip()
        access_key = getattr(settings, "tts_access_key", "") or ""
        secret_key = getattr(settings, "tts_secret_key", "") or ""
        ark_api_key = getattr(settings, "tts_ark_api_key", "") or ""
        # 1) 有「豆包语音 API Key」 -> 官方最简方式：一个 Key + x-api-key header。
        if ark_api_key:
            try:
                return _volcano_speech_key(text, settings), "audio/mpeg"
            except RuntimeError as error:
                # Key 无效时退回 AppID/Access Token 旧接口，避免卡配置。
                if ":" in (settings.tts_api_key or ""):
                    return _volcano(text, settings), "audio/mpeg"
                raise
        # 2) AK/SK + ep- Endpoint ID -> 方舟 MaaS 大模型接口。
        if access_key and secret_key and model.startswith("ep-"):
            return _volcano_maas(text, settings), "audio/mpeg"
        # 3) 默认：AppID + Access Token 旧版接口，自动使用 cluster volcano_tts。
        return _volcano(text, settings), "audio/mpeg"
    raise RuntimeError("未知的语音合成供应商：" + str(provider))
