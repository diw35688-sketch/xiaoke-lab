# -*- coding: utf-8 -*-
"""QwenAudio 实时语音桥接。

启动 QwenAudio 的 DashScope Realtime 前台时，直接复用本项目
settings_store 里保存的 DASHSCOPE_API_KEY，不再让用户单独维护
QwenAudio 的 config.env。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import settings_store

QWEN_AUDIO_ROOT = Path(__file__).resolve().parent.parent / "_qwen-audio-agent"
SERVER_ENTRY = QWEN_AUDIO_ROOT / "lab" / "start-lab-gateway.mjs"
DEFAULT_PORT = 3101
DEFAULT_MODEL = "qwen-audio-3.0-realtime-plus"


def qwen_env() -> dict:
    """把本项目设置转成 QwenAudio 需要的环境变量。"""
    env = os.environ.copy()
    settings = settings_store.current()
    env["DASHSCOPE_API_KEY"] = settings.realtime_dashscope_key() or ""
    env["QWEN_AUDIO_REALTIME_PROVIDER"] = "dashscope"
    env["QWEN_AUDIO_REALTIME_MODEL"] = settings.dashscope_realtime_model or DEFAULT_MODEL
    env["AGENT_PROTOCOL"] = "none"
    env["LAB_ASSISTANT_BASE_URL"] = os.getenv("LAB_ASSISTANT_BASE_URL", "http://127.0.0.1:8000")
    env.setdefault(
        "QWEN_AUDIO_AGENT_ALLOWED_ORIGINS",
        os.getenv(
            "QWEN_AUDIO_AGENT_ALLOWED_ORIGINS",
            "http://127.0.0.1:8000,http://localhost:8000",
        ),
    )
    env["QWEN_AUDIO_AGENT_ASSISTANT_PROFILE_PATH"] = str(
        QWEN_AUDIO_ROOT / "lab" / "ASSISTANT.md"
    )
    env["QWEN_AUDIO_ROOT"] = str(QWEN_AUDIO_ROOT)
    env["QWEN_AUDIO_FRONTEND_MCP_CONFIG"] = str(
        QWEN_AUDIO_ROOT / "lab" / "frontend-mcp.json"
    )
    env.setdefault("HOST", "0.0.0.0")
    env.setdefault("PORT", str(DEFAULT_PORT))
    return env


def is_running(port: int = DEFAULT_PORT) -> bool:
    """通过 /api/health 判断 QwenAudio 是否已在运行。"""
    import urllib.request

    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/health", timeout=1.5
        ) as response:
            return response.status == 200
    except Exception:
        return False


def start(port: int = DEFAULT_PORT, wait: bool = True) -> dict:
    """启动 QwenAudio Gateway（仅前台实时语音，无后台 Agent）。"""
    if is_running(port):
        return {"ok": True, "message": "QwenAudio 已在运行", "pid": None, "port": port}

    env = qwen_env()
    if not env["DASHSCOPE_API_KEY"]:
        return {
            "ok": False,
            "message": "请先在 设置 → 语音模型 → DashScope API Key 里填写密钥",
            "pid": None,
            "port": port,
        }

    log_dir = QWEN_AUDIO_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "qwen-audio-agent.out.log"

    with log_path.open("a", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            ["node", str(SERVER_ENTRY)],
            cwd=str(QWEN_AUDIO_ROOT),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
        )

    if wait:
        import time

        for _ in range(40):
            if process.poll() is not None:
                return {
                    "ok": False,
                    "message": f"QwenAudio 启动失败，退出码 {process.returncode}，"
                               f"日志见 {log_path}",
                    "pid": process.pid,
                    "port": port,
                }
            if is_running(port):
                return {"ok": True, "message": "QwenAudio 已启动", "pid": process.pid, "port": port}
            time.sleep(0.5)

    return {"ok": False, "message": "QwenAudio 启动超时", "pid": process.pid, "port": port}


def status(port: int = DEFAULT_PORT) -> dict:
    return {
        "ok": is_running(port),
        "port": port,
        "url": f"http://127.0.0.1:{port}",
        "dashscope_key_set": bool(settings_store.current().realtime_dashscope_key()),
    }


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        print(status())
    else:
        print(start())
