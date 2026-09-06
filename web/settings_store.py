# -*- coding: utf-8 -*-
"""运行时可修改的模型设置：支持在网页里配置，保存后立即生效，无需重启。

设计要点：
- 设置持久化到 settings.json（已忽略提交），密钥不进版本库。
- 对外读取一律走 current()，不要在模块顶层固化常量，
  否则网页改了设置也不会生效。
- 返回给前端的密钥始终掩码，接口不回传明文。
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = BASE_DIR / "settings.json"

# 常见服务商预设，方便用户一键填好地址和模型名
USTC_MODEL_CATALOG = [
    {"id": "mineru", "label": "MinerU 文档解析", "category": "文档解析", "context": "-"},
    {"id": "unlimited-ocr", "label": "Unlimited OCR", "category": "文档解析", "context": "32,000"},
    {"id": "qwen-chat", "label": "Qwen Chat", "category": "高效通用层", "context": "262,000"},
    {"id": "qwen-reasoner", "label": "Qwen Reasoner", "category": "高效通用层", "context": "262,000"},
    {"id": "qwen3.8-chat", "label": "Qwen3.8 Chat", "category": "能力增强层", "context": "262,144"},
    {"id": "qwen3.8-reasoner", "label": "Qwen3.8 Reasoner", "category": "能力增强层", "context": "262,144"},
    {"id": "qwen3-embedding", "label": "Qwen3 Embedding", "category": "向量", "context": "40,000"},
    {"id": "qwen3-reranker", "label": "Qwen3 Reranker", "category": "排序", "context": "40,000"},
    {"id": "smart/default", "label": "Smart Default", "category": "高效通用层", "context": "262,000"},
    {"id": "smart/reasoning", "label": "Smart Reasoning", "category": "高效通用层", "context": "262,000"},
    {"id": "deepseek-chat", "label": "DeepSeek Chat", "category": "DeepSeek", "context": "-"},
    {"id": "deepseek-reasoner", "label": "DeepSeek Reasoner", "category": "DeepSeek", "context": "-"},
    {"id": "deepseek-v4-pro", "label": "DeepSeek V4 Pro", "category": "DeepSeek", "context": "-"},
    {"id": "deepseek-v4-flash", "label": "DeepSeek V4 Flash", "category": "DeepSeek", "context": "-"},
    {"id": "deepseek-v4-flash-ascend", "label": "DeepSeek V4 Flash Ascend", "category": "DeepSeek", "context": "-"},
    {"id": "glm-chat", "label": "GLM Chat", "category": "GLM", "context": "-"},
    {"id": "glm-reasoner", "label": "GLM Reasoner", "category": "GLM", "context": "-"},
    {"id": "claude-opus-4-8", "label": "Claude Opus 4.8", "category": "Claude", "context": "-"},
    {"id": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6", "category": "Claude", "context": "-"},
    {"id": "k3", "label": "K3", "category": "其他", "context": "-"},
]


def catalog_for_models(models: list[str]) -> list[dict]:
    """把模型 id 列表映射为带分类和上下文的目录。"""

    by_id = {item["id"]: item for item in USTC_MODEL_CATALOG}
    return [
        by_id.get(model, {"id": model, "label": model, "category": "其他", "context": "-"})
        for model in models
    ]


PRESETS = [
    {"id": "ustc", "label": "中科大 LLM",
     "base_url": "https://api.llm.ustc.edu.cn/v1", "model": "deepseek-v4-pro",
     "api_url": "https://api.llm.ustc.edu.cn"},
    {"id": "deepseek", "label": "DeepSeek 官方",
     "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat",
     "api_url": "https://platform.deepseek.com/api_keys"},
    {"id": "openai", "label": "OpenAI",
     "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini",
     "api_url": "https://platform.openai.com/api-keys"},
    {"id": "dashscope", "label": "阿里百炼（通义）",
     "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus",
     "api_url": "https://bailian.console.aliyun.com/?tab=apiKey"},
    {"id": "custom", "label": "自定义", "base_url": "", "model": "",
     "api_url": ""},
]


@dataclass
class ModelSettings:
    """一份完整的模型与语音配置。"""

    api_key: str = ""
    base_url: str = "https://api.llm.ustc.edu.cn/v1"
    model_name: str = "deepseek-v4-pro"
    thinking_level: str = "auto"
    dashscope_api_key: str = ""
    dashscope_realtime_model: str = "qwen-audio-3.0-realtime-plus"
    tts_enabled: bool = False
    speak_record_ack: bool = True
    tts_url: str = "http://127.0.0.1:8001/tts"
    tts_provider: str = "browser"
    tts_api_key: str = ""
    tts_base_url: str = ""
    tts_model: str = ""
    tts_voice: str = ""
    tts_speed: float = 1.0
    # 火山方舟 MaaS 大模型语音合成（seed-tts）使用 AK/SK + endpoint_id。
    tts_access_key: str = ""
    tts_secret_key: str = ""
    # 火山方舟 Agent Plan 语音模型（seed-tts）推荐直接用「专属 API Key」，
    # 只需一个 Key + X-Api-Resource-Id，不需要 AK/SK 或 Endpoint。
    tts_ark_api_key: str = ""
    voice_short_reply: bool = True
    voice_disable_thinking: bool = True
    api_keys: dict = field(default_factory=dict)
    provider_profiles: dict = field(default_factory=dict)
    mineru_file_parse_url: str = "https://api.llm.ustc.edu.cn/mineru/file_parse"
    mineru_api_key: str = ""
    ocr_base_url: str = "https://api.llm.ustc.edu.cn/v1"
    ocr_api_key: str = ""
    ocr_model: str = "unlimited-ocr"
    community_base_url: str = "http://124.221.234.222:3000/api"
    # 主动智能体：每日心跳时间可配置；主人画像由用户在设置中心补充。
    heartbeat_enabled: bool = True
    heartbeat_time: str = "08:00"
    owner_profile: dict = field(default_factory=dict)

    def realtime_dashscope_key(self) -> str:
        """Qwen Audio 实时语音与阿里百炼文本模型共用同一 DashScope Key。"""
        return self.dashscope_api_key or self.api_keys.get("dashscope", "")

    def masked(self) -> dict:
        """给前端看的版本：密钥掩码，永不回传明文。"""
        data = asdict(self)
        data["provider_profiles"] = dict(self.provider_profiles)
        data["mineru_api_key_set"] = bool(self.mineru_api_key)
        data["mineru_api_key"] = _mask_key(self.mineru_api_key) if self.mineru_api_key else ""
        data["ocr_api_key_set"] = bool(self.ocr_api_key)
        data["ocr_api_key"] = _mask_key(self.ocr_api_key) if self.ocr_api_key else ""
        data["provider_keys"] = {
            provider_id: _mask_key(key)
            for provider_id, key in self.api_keys.items()
            if key
        }
        tts_key = self.tts_api_key
        if not tts_key:
            data["tts_api_key"] = ""
            data["tts_api_key_set"] = False
        else:
            data["tts_api_key"] = (
                tts_key[:4] + "*" * 8 + tts_key[-4:] if len(tts_key) > 8 else "*" * len(tts_key)
            )
            data["tts_api_key_set"] = True
        data["tts_access_key_set"] = bool(self.tts_access_key)
        data["tts_access_key"] = _mask_key(self.tts_access_key) if self.tts_access_key else ""
        data["tts_secret_key_set"] = bool(self.tts_secret_key)
        data["tts_secret_key"] = _mask_key(self.tts_secret_key) if self.tts_secret_key else ""
        data["tts_ark_api_key_set"] = bool(self.tts_ark_api_key)
        data["tts_ark_api_key"] = _mask_key(self.tts_ark_api_key) if self.tts_ark_api_key else ""
        key = self.api_key
        if not key:
            data["api_key"] = ""
            data["api_key_set"] = False
        else:
            data["api_key"] = _mask_key(key)
            data["api_key_set"] = True
        realtime_dashscope_key = self.realtime_dashscope_key()
        data["dashscope_api_key_set"] = bool(realtime_dashscope_key)
        data["dashscope_api_key"] = (
            _mask_key(realtime_dashscope_key) if realtime_dashscope_key else ""
        )
        # 服务器/远程地址仅由后端代理使用，不暴露给浏览器，防止被攻击。
        for name in (
            "community_base_url",
            "mineru_file_parse_url",
            "ocr_base_url",
            "tts_base_url",
            "tts_url",
        ):
            data.pop(name, None)
        return data

    def key_for(self, provider_id: str | None) -> str:
        """按供应商取密钥；未单独保存时回退到当前主密钥。"""

        if provider_id and self.api_keys.get(provider_id):
            return self.api_keys[provider_id]
        return self.api_key

    def is_ready(self) -> bool:
        return bool(self.api_key and self.base_url and self.model_name)

    def missing(self) -> list:
        problems = []
        if not self.api_key:
            problems.append("尚未填写 API 密钥")
        if not self.base_url:
            problems.append("尚未填写接口地址")
        if not self.model_name:
            problems.append("尚未填写模型名称")
        return problems


# 可重入锁：update()/clear_api_key() 会在持锁期间调用 current()，
# 用普通 Lock 会自死锁。
_lock = threading.RLock()
_cache: ModelSettings | None = None


def _mask_key(key: str) -> str:
    return key[:4] + "*" * 8 + key[-4:] if len(key) > 8 else "*" * len(key)


def _from_env() -> ModelSettings:
    """首次运行时，从环境变量继承已有配置，避免老用户重填。"""
    return ModelSettings(
        api_key=os.getenv("OPENAI_API_KEY", "") or os.getenv("LLM_API_KEY", ""),
        base_url=os.getenv("OPENAI_BASE_URL", "")
        or os.getenv("LLM_BASE_URL", "")
        or "https://api.llm.ustc.edu.cn/v1",
        model_name=os.getenv("MODEL_NAME", "")
        or os.getenv("LLM_MODEL", "")
        or "deepseek-v4-pro",
        dashscope_api_key=os.getenv("DASHSCOPE_API_KEY", ""),
        dashscope_realtime_model=os.getenv(
            "QWEN_AUDIO_REALTIME_MODEL", "qwen-audio-3.0-realtime-plus"
        ),
        tts_enabled=os.getenv("TTS_ENABLED", "false").strip().lower()
        in {"1", "true", "yes", "on"},
        speak_record_ack=os.getenv("SPEAK_RECORD_ACK", "true").strip().lower()
        in {"1", "true", "yes", "on"},
        tts_url=os.getenv("LOCAL_QWEN_TTS_URL", "http://127.0.0.1:8001/tts"),
    )


def current() -> ModelSettings:
    """读取当前设置；业务代码必须每次调用，不要缓存成模块常量。"""
    global _cache
    with _lock:
        if _cache is not None:
            return _cache
        if SETTINGS_FILE.is_file():
            try:
                raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                _cache = ModelSettings(
                    api_key=raw.get("api_key", ""),
                    base_url=raw.get("base_url", ""),
                    model_name=raw.get("model_name", ""),
                    thinking_level=raw.get("thinking_level", "auto"),
                    dashscope_api_key=raw.get("dashscope_api_key", ""),
                    dashscope_realtime_model=raw.get(
                        "dashscope_realtime_model", "qwen-audio-3.0-realtime-plus"
                    ),
                    tts_enabled=bool(raw.get("tts_enabled", False)),
                    speak_record_ack=bool(raw.get("speak_record_ack", True)),
                    tts_url=raw.get("tts_url", "http://127.0.0.1:8001/tts"),
                    tts_provider=raw.get("tts_provider", "browser"),
                    tts_api_key=raw.get("tts_api_key", ""),
                    tts_base_url=raw.get("tts_base_url", ""),
                    tts_model=raw.get("tts_model", ""),
                    tts_voice=raw.get("tts_voice", ""),
                    tts_speed=float(raw.get("tts_speed", 1.0) or 1.0),
                    tts_access_key=raw.get("tts_access_key", ""),
                    tts_secret_key=raw.get("tts_secret_key", ""),
                    tts_ark_api_key=raw.get("tts_ark_api_key", ""),
                    voice_short_reply=bool(raw.get("voice_short_reply", True)),
                    voice_disable_thinking=bool(raw.get("voice_disable_thinking", True)),
                    api_keys=raw.get("api_keys", {}) or {},
                    provider_profiles=raw.get("provider_profiles", {}) or {},
                    mineru_file_parse_url=raw.get("mineru_file_parse_url", "https://api.llm.ustc.edu.cn/mineru/file_parse"),
                    mineru_api_key=raw.get("mineru_api_key", ""),
                    ocr_base_url=raw.get("ocr_base_url", "https://api.llm.ustc.edu.cn/v1"),
                    ocr_api_key=raw.get("ocr_api_key", ""),
                    ocr_model=raw.get("ocr_model", "unlimited-ocr"),
                    community_base_url=raw.get("community_base_url", "http://124.221.234.222:3000/api"),
                    heartbeat_enabled=bool(raw.get("heartbeat_enabled", True)),
                    heartbeat_time=str(raw.get("heartbeat_time", "08:00") or "08:00"),
                    owner_profile=raw.get("owner_profile", {}) or {},
                )
            except (json.JSONDecodeError, OSError):
                _cache = _from_env()
        else:
            _cache = _from_env()
        return _cache


def update(**changes) -> ModelSettings:
    """更新并落盘。api_key 传空字符串表示保持原值，避免掩码回写覆盖真实密钥。"""
    global _cache
    with _lock:
        settings = current()
        for name in ("base_url", "model_name", "thinking_level", "tts_url",
                     "tts_provider", "tts_base_url", "tts_model", "tts_voice",
                     "mineru_file_parse_url", "ocr_base_url", "ocr_model",
                     "community_base_url", "dashscope_realtime_model"):
            if name in changes and changes[name] is not None:
                setattr(settings, name, str(changes[name]).strip())
        if "tts_enabled" in changes and changes["tts_enabled"] is not None:
            settings.tts_enabled = bool(changes["tts_enabled"])
        if "speak_record_ack" in changes and changes["speak_record_ack"] is not None:
            settings.speak_record_ack = bool(changes["speak_record_ack"])
        if "voice_short_reply" in changes and changes["voice_short_reply"] is not None:
            settings.voice_short_reply = bool(changes["voice_short_reply"])
        if "voice_disable_thinking" in changes and changes["voice_disable_thinking"] is not None:
            settings.voice_disable_thinking = bool(changes["voice_disable_thinking"])
        if "tts_speed" in changes and changes["tts_speed"] is not None:
            try:
                settings.tts_speed = max(0.5, min(2.0, float(changes["tts_speed"])))
            except (TypeError, ValueError):
                pass
        provider_id = changes.get("provider_id")
        new_key = changes.get("api_key")
        if new_key:
            key = str(new_key).strip()
            settings.api_key = key
            if provider_id:
                settings.api_keys = dict(settings.api_keys)
                settings.api_keys[provider_id] = key
        if provider_id and (changes.get("base_url") or changes.get("model_name")):
            settings.provider_profiles = dict(settings.provider_profiles)
            settings.provider_profiles[provider_id] = {
                "label": str(changes.get("provider_label") or provider_id),
                "base_url": settings.base_url,
                "model": settings.model_name,
            }
        new_tts_key = changes.get("tts_api_key")
        if new_tts_key:
            settings.tts_api_key = str(new_tts_key).strip()
        new_tts_ak = changes.get("tts_access_key")
        if new_tts_ak:
            settings.tts_access_key = str(new_tts_ak).strip()
        new_tts_sk = changes.get("tts_secret_key")
        if new_tts_sk:
            settings.tts_secret_key = str(new_tts_sk).strip()
        new_tts_ark_key = changes.get("tts_ark_api_key")
        if new_tts_ark_key:
            settings.tts_ark_api_key = str(new_tts_ark_key).strip()
        new_dashscope_key = changes.get("dashscope_api_key")
        if new_dashscope_key:
            settings.dashscope_api_key = str(new_dashscope_key).strip()
        new_mineru_key = changes.get("mineru_api_key")
        if new_mineru_key:
            settings.mineru_api_key = str(new_mineru_key).strip()
        new_ocr_key = changes.get("ocr_api_key")
        if new_ocr_key:
            settings.ocr_api_key = str(new_ocr_key).strip()
        if "heartbeat_enabled" in changes and changes["heartbeat_enabled"] is not None:
            settings.heartbeat_enabled = bool(changes["heartbeat_enabled"])
        if changes.get("heartbeat_time") is not None:
            raw_time = str(changes["heartbeat_time"]).strip()
            if ":" in raw_time:
                hour_str, minute_str = raw_time.split(":", 1)
                try:
                    hour = int(hour_str)
                    minute = int(minute_str.split(".")[0].split("+")[0].strip())
                    if 0 <= hour <= 23 and 0 <= minute <= 59:
                        settings.heartbeat_time = f"{hour:02d}:{minute:02d}"
                except (TypeError, ValueError):
                    pass
        if "owner_profile" in changes and isinstance(changes["owner_profile"], dict):
            settings.owner_profile = dict(changes["owner_profile"])
        SETTINGS_FILE.write_text(
            json.dumps(asdict(settings), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _cache = settings
        return settings


def clear_api_key() -> ModelSettings:
    """显式清除密钥，用于换账号。"""
    global _cache
    with _lock:
        settings = current()
        settings.api_key = ""
        SETTINGS_FILE.write_text(
            json.dumps(asdict(settings), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _cache = settings
        return settings


def list_providers() -> list[dict]:
    """返回全部供应商（内置预设 + 自定义），适合做模型管理列表。

    同一 id 同时存在于内置预设和 provider_profiles 时按同一个提供方合并，
    不再把 DeepSeek 官方显示成两行或降级成“自定义”。
    """
    settings = current()
    preset_by_id = {preset["id"]: preset for preset in PRESETS}
    items: dict[str, dict] = {}
    for preset in PRESETS:
        items[preset["id"]] = {
            "id": preset["id"],
            "label": preset["label"],
            "base_url": preset["base_url"],
            "model": preset["model"],
            "kind": "preset",
            "key_set": bool(settings.api_keys.get(preset["id"])) or (
                preset["id"] == "custom" and bool(settings.api_key)
            ),
            "active": False,
            "api_url": preset.get("api_url", ""),
        }
    for provider_id, profile in settings.provider_profiles.items():
        preset = preset_by_id.get(provider_id)
        if preset is not None:
            # 内置提供方：保留官方名称/类型，只覆盖用户保存过的地址和模型。
            item = items[provider_id]
            item["base_url"] = profile.get("base_url") or item["base_url"]
            item["model"] = profile.get("model") or item["model"]
            item["key_set"] = bool(settings.api_keys.get(provider_id)) or (
                provider_id == "custom" and bool(settings.api_key)
            )
            continue
        items[provider_id] = {
            "id": provider_id,
            "label": profile.get("label") or provider_id,
            "base_url": profile.get("base_url", ""),
            "model": profile.get("model", ""),
            "kind": "custom",
            "key_set": bool(settings.api_keys.get(provider_id)),
            "active": False,
            "api_url": "",
        }
    # 当前激活的供应商：按 base_url + model_name 匹配
    for item in items.values():
        model = item.get("model", "").lower()
        item["supports_thinking"] = any(token in model for token in (
            "reason", "reasoning", "think", "r1", "o1", "o3", "glm", "max"
        ))
        if item["base_url"] == settings.base_url and item["model"] == settings.model_name:
            item["active"] = True
    return [item for item in items.values()]


def add_provider(
    provider_id: str,
    label: str,
    base_url: str,
    model: str,
    api_key: str = "",
) -> ModelSettings:
    """新增/更新一个自定义供应商（同时可保存该供应商的 API 密钥）。"""
    provider_id = provider_id.strip()
    label = label.strip() or provider_id
    base_url = base_url.strip()
    model = model.strip()
    if not provider_id or not base_url or not model:
        raise ValueError("provider_id、接口地址和模型名都不能为空。")
    settings = current()
    settings.provider_profiles = dict(settings.provider_profiles)
    settings.provider_profiles[provider_id] = {
        "label": label,
        "base_url": base_url,
        "model": model,
    }
    if api_key.strip():
        settings.api_keys = dict(settings.api_keys)
        settings.api_keys[provider_id] = api_key.strip()
    SETTINGS_FILE.write_text(
        json.dumps(asdict(settings), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _cache = settings
    return settings


def delete_provider(provider_id: str) -> ModelSettings:
    """删除自定义供应商；内置预设不会被删掉。"""
    settings = current()
    settings.provider_profiles = dict(settings.provider_profiles)
    settings.api_keys = dict(settings.api_keys)
    settings.provider_profiles.pop(provider_id, None)
    settings.api_keys.pop(provider_id, None)
    if settings.base_url == (settings.provider_profiles.get(provider_id, {}) or {}).get("base_url"):
        pass  # 不自动切走当前配置，由前端在删除后主动保存新的当前供应商
    SETTINGS_FILE.write_text(
        json.dumps(asdict(settings), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _cache = settings
    return settings


def fetch_models(
    base_url: str | None = None,
    api_key: str | None = None,
    provider_id: str | None = None,
) -> list[str]:
    """从兼容 OpenAI 的 /models 接口拉取可用模型名。"""

    settings = current()
    base_url = (base_url or settings.base_url).strip()
    api_key = api_key or settings.key_for(provider_id)
    if not base_url:
        raise ValueError("请先填写接口地址 Base URL。")

    import httpx

    url = base_url.rstrip("/") + "/models"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    try:
        response = httpx.get(
            url,
            headers=headers,
            timeout=httpx.Timeout(20, connect=8),
            trust_env=False,
        )
    except httpx.ConnectError:
        raise ValueError("连不上接口地址，请检查网络或 base_url 是否正确")
    except httpx.TimeoutException:
        raise ValueError("请求超时，接口地址可能不可达")
    except Exception as error:
        raise ValueError(type(error).__name__ + ": " + str(error)[:140])

    if response.status_code != 200:
        raise ValueError(
            "HTTP " + str(response.status_code) + "：" + response.text[:140]
        )
    try:
        data = response.json()
        models = data.get("data", data)
        names = [item.get("id", "") for item in models if isinstance(item, dict)]
        names = [name for name in names if name]
    except Exception as error:
        raise ValueError("返回结果不是预期 JSON：" + str(error))
    if not names:
        raise ValueError("没有拉到模型，请检查接口地址和权限。")
    return sorted(set(names))


def test_connection(settings: ModelSettings | None = None) -> tuple[bool, str]:
    """用最小请求验证密钥、地址和模型名是否真的能用。"""
    settings = settings or current()
    problems = settings.missing()
    if problems:
        return False, "；".join(problems)

    import httpx

    url = settings.base_url.rstrip("/") + "/chat/completions"
    try:
        response = httpx.post(
            url,
            headers={
                "Authorization": "Bearer " + settings.api_key,
                "Content-Type": "application/json",
            },
            json={
                "model": settings.model_name,
                "thinking": {"type": "disabled"},
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
            },
            timeout=httpx.Timeout(20, connect=8),
            trust_env=False,
        )
    except httpx.ConnectError:
        return False, "连不上接口地址，请检查网络或 base_url 是否正确"
    except httpx.TimeoutException:
        return False, "请求超时，接口地址可能不可达"
    except Exception as error:
        return False, type(error).__name__ + ": " + str(error)[:120]

    if response.status_code == 200:
        return True, "连接成功，密钥、地址和模型名均可用"
    if response.status_code == 401:
        return False, "密钥无效或已过期（HTTP 401）"
    if response.status_code == 403:
        return False, "密钥没有该模型的权限（HTTP 403）"
    if response.status_code == 404:
        return False, "接口地址或模型名不存在（HTTP 404）"
    return False, "HTTP " + str(response.status_code) + "：" + response.text[:140]
