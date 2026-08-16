# -*- coding: utf-8 -*-
r"""一键安装 / 首次运行准备。

这个脚本把“下载依赖 + 下载模型 + 生成配置”收拢成一条命令，最终用户不需要
手动去装 Python 包，也不需要去 ModelScope 找模型。

用法（仓库根目录）：
  .\python.exe scripts\setup.py            # 已有 Python 时
  .\.venv\Scripts\python.exe scripts\setup.py  # 已有 venv 时也能跑

可选参数：
  --mirror pip镜像URL    例如 https://pypi.tuna.tsinghua.edu.cn/simple
  --skip-models          跳过模型下载（已经下好时用）
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

# 重定向到日志文件时也逐行刷新，方便用户和调试脚本实时看到进度。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = REPO_ROOT / "web"
VENV_DIR = REPO_ROOT / ".venv"
MODELS_DIR = REPO_ROOT / "models"
MODELSCOPE_CACHE_DIR = MODELS_DIR / "modelscope_cache"
ENV_FILE = REPO_ROOT / ".env"
SETTINGS_FILE = WEB_DIR / "settings.json"

ASR_MODEL_ID = "iic/SenseVoiceSmall"

# 国内站点直连往往比绕代理更快，也避免代理对 SSL 做拦截导致 EOF。
DOMESTIC_NO_PROXY = "modelscope.cn,.modelscope.cn,pypi.tuna.tsinghua.edu.cn"
BIN_DIR = REPO_ROOT / "bin"
CLOUDFLARED_EXE = BIN_DIR / "cloudflared.exe"
CLOUDFLARED_URL = (
    "https://github.com/cloudflare/cloudflared/releases/latest/download/"
    "cloudflared-windows-amd64.exe"
)


def step(title: str) -> None:
    print(f"\n=== {title} ===")


def no_proxy_env() -> dict:
    """在当前环境变量基础上，对 ModelScope / 清华 PyPI 关闭代理。"""
    env = os.environ.copy()
    for key in ("NO_PROXY", "no_proxy"):
        old = env.get(key, "")
        if old:
            env[key] = old + "," + DOMESTIC_NO_PROXY
        else:
            env[key] = DOMESTIC_NO_PROXY
    return env


def venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def ensure_venv() -> Path:
    python = venv_python()
    if python.exists():
        print(f"[OK] 虚拟环境已存在：{python}")
        return python

    step("创建 Python 虚拟环境")
    if not shutil.which("python") and sys.executable is None:
        raise RuntimeError("找不到 Python。请先安装 Python 3.10+。")

    base_python = sys.executable
    print(f"[*] 使用 {base_python} 创建 .venv ...")
    subprocess.check_call([base_python, "-m", "venv", str(VENV_DIR)])
    print("[OK] 虚拟环境创建完成")
    return venv_python()


def install_dependencies(python: Path, mirror: str | None) -> None:
    step("安装 Python 依赖（可能需要几分钟）")
    index_args = ["--index-url", mirror] if mirror else []
    env = no_proxy_env()
    subprocess.check_call([str(python), "-m", "pip", "install", "--upgrade", "pip", *index_args], env=env)

    requirements = [REPO_ROOT / "requirements.txt", WEB_DIR / "requirements.txt"]
    for req in requirements:
        print(f"[*] 安装 {req.name} ...")
        subprocess.check_call(
            [str(python), "-m", "pip", "install", "-r", str(req), *index_args], env=env
        )
    print("[OK] 依赖安装完成")


def env_defaults() -> dict:
    return {
        "MODELSCOPE_CACHE": MODELSCOPE_CACHE_DIR.as_posix(),
        "ASR_SENSEVOICE_MODEL": ASR_MODEL_ID,
        "ASR_BACKEND": "sensevoice",
        "DEVICE": "cpu",
    }


def ensure_env_file() -> None:
    step("生成本地配置 .env")
    defaults = env_defaults()
    if ENV_FILE.exists():
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
        updated = set()
        for index, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key = stripped.split("=", 1)[0].strip()
            if key in defaults:
                lines[index] = f"{key}={defaults[key]}"
                updated.add(key)
        for key, value in defaults.items():
            if key not in updated:
                lines.append(f"{key}={value}")
        ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"[OK] .env 已更新（模型缓存目录：{MODELSCOPE_CACHE_DIR.as_posix()}）")
        return

    lines = ["# 首次运行由 scripts/setup.py 生成"]
    lines += [f"{key}={value}" for key, value in defaults.items()]
    lines.append("TTS_ENABLED=false")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[OK] 已写入 {ENV_FILE}")


def download_asr_model(python: Path) -> None:
    step("下载 SenseVoiceSmall 语音识别模型（仅首次）")
    MODELSCOPE_CACHE_DIR.mkdir(exist_ok=True)
    env = no_proxy_env()
    env["MODELSCOPE_CACHE"] = str(MODELSCOPE_CACHE_DIR)
    snippet = (
        "from modelscope import snapshot_download\n"
        f"print(snapshot_download('{ASR_MODEL_ID}'))\n"
    )
    subprocess.check_call([str(python), "-c", snippet], env=env)
    print("[OK] ASR 模型已就绪")


def ensure_settings_json() -> None:
    step("生成网页端配置文件 web/settings.json")
    if SETTINGS_FILE.exists():
        print("[OK] settings.json 已存在，保留用户配置")
        return
    default_settings = {
        "api_key": "",
        "base_url": "https://api.llm.ustc.edu.cn/v1",
        "model_name": "deepseek-v4-pro",
        "tts_enabled": False,
        "tts_url": "http://127.0.0.1:8001/tts",
        "tts_provider": "browser",
        "tts_api_key": "",
        "tts_base_url": "",
        "tts_model": "",
        "tts_voice": "",
        "tts_speed": 1.0,
    }
    SETTINGS_FILE.write_text(
        json.dumps(default_settings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("[OK] 已生成 settings.json（用户可在网页里填写模型密钥）")


def ensure_cloudflared() -> None:
    """把 cloudflared 放进项目 bin 目录，用户无需安装、无需配置。"""
    step("准备手机公网访问组件 cloudflared")
    if shutil.which("cloudflared") is not None:
        print("[OK] 系统已有 cloudflared")
        return
    if CLOUDFLARED_EXE.exists():
        print(f"[OK] 项目内已有 cloudflared：{CLOUDFLARED_EXE}")
        return

    print("[*] 正在自动下载 cloudflared 到项目 bin 目录...")
    BIN_DIR.mkdir(exist_ok=True)
    tmp = CLOUDFLARED_EXE.with_suffix(".exe.download")
    try:
        with urllib.request.urlopen(CLOUDFLARED_URL, timeout=120) as response, open(tmp, "wb") as fh:
            shutil.copyfileobj(response, fh)
        tmp.replace(CLOUDFLARED_EXE)
        print(f"[OK] cloudflared 已就绪：{CLOUDFLARED_EXE}")
    except Exception as error:
        print(f"[!] cloudflared 自动下载失败（{error}）。")
        print("    本次将回退局域网模式；你什么都不用做，下次启动会继续自动尝试。")


def main() -> None:
    parser = argparse.ArgumentParser(description="实验助手一键安装")
    parser.add_argument("--mirror", default=None, help="pip 镜像 URL，例如 https://pypi.tuna.tsinghua.edu.cn/simple")
    parser.add_argument("--skip-models", action="store_true", help="跳过模型下载")
    args = parser.parse_args()

    print(f"仓库路径：{REPO_ROOT}")
    python = ensure_venv()
    install_dependencies(python, args.mirror)
    ensure_env_file()
    if not args.skip_models:
        download_asr_model(python)
    ensure_settings_json()
    ensure_cloudflared()

    marker = MODELS_DIR / ".setup_done"
    marker.write_text(
        "setup completed at " + __import__("datetime").datetime.now().isoformat(timespec="seconds") + "\n",
        encoding="utf-8",
    )

    print("\n" + "=" * 56)
    print("安装完成。以后只需双击：start.bat")
    print("=" * 56)


if __name__ == "__main__":
    main()
