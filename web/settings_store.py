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
PRESETS = [
    {"id": "ustc", "label": "中科大校内 LLM",
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
    tts_enabled: bool = False
    tts_url: str = "http://127.0.0.1:8001/tts"
    tts_provider: str = "browser"
    tts_api_key: str = ""
    tts_base_url: str = ""
    tts_model: str = ""
    tts_voice: str = ""
    tts_speed: float = 1.0

    def masked(self) -> dict:
        """给前端看的版本：密钥掩码，永不回传明文。"""
        data = asdict(self)
        tts_key = self.tts_api_key
        if not tts_key:
            data["tts_api_key"] = ""
            data["tts_api_key_set"] = False
        else:
            data["tts_api_key"] = (
                tts_key[:4] + "*" * 8 + tts_key[-4:] if len(tts_key) > 8 else "*" * len(tts_key)
            )
            data["tts_api_key_set"] = True
        key = self.api_key
        if not key:
            data["api_key"] = ""
            data["api_key_set"] = False
        else:
            data["api_key"] = (
                key[:4] + "*" * 8 + key[-4:] if len(key) > 8 else "*" * len(key)
            )
            data["api_key_set"] = True
        return data

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
        tts_enabled=os.getenv("TTS_ENABLED", "false").strip().lower()
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
                    tts_enabled=bool(raw.get("tts_enabled", False)),
                    tts_url=raw.get("tts_url", "http://127.0.0.1:8001/tts"),
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
        for name in ("base_url", "model_name", "tts_url",
                     "tts_provider", "tts_base_url", "tts_model", "tts_voice"):
            if name in changes and changes[name] is not None:
                setattr(settings, name, str(changes[name]).strip())
        if "tts_enabled" in changes and changes["tts_enabled"] is not None:
            settings.tts_enabled = bool(changes["tts_enabled"])
        if "tts_speed" in changes and changes["tts_speed"] is not None:
            try:
                settings.tts_speed = max(0.5, min(2.0, float(changes["tts_speed"])))
            except (TypeError, ValueError):
                pass
        new_key = changes.get("api_key")
        if new_key:
            settings.api_key = str(new_key).strip()
        new_tts_key = changes.get("tts_api_key")
        if new_tts_key:
            settings.tts_api_key = str(new_tts_key).strip()
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


def fetch_models(
    base_url: str | None = None,
    api_key: str | None = None,
) -> list[str]:
    """从兼容 OpenAI 的 /models 接口拉取可用模型名。"""

    settings = current()
    base_url = (base_url or settings.base_url).strip()
    api_key = api_key or settings.api_key
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
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
            },
            timeout=httpx.Timeout(20, connect=8),
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
