# -*- coding: utf-8 -*-
"""网络模式管理：在网页 UI 里切换「局域网」或「公网隧道」。

所有操作都通过接口完成，不需要用户去碰启动脚本。
"""

from __future__ import annotations

import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

import phone_access

REPO_ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = REPO_ROOT / "bin"
CLOUDFLARED_EXE = BIN_DIR / "cloudflared.exe"

_lock = threading.RLock()
_mode = "lan"
_tunnel_process = None
_public_url = None
_stop_event = threading.Event()
_tunnel_log: list[str] = []
_tunnel_error: str | None = None


def lan_url() -> str:
    ip = phone_access.lan_ip()
    cert = REPO_ROOT / "web" / "certs" / "cert.pem"
    scheme = "https" if cert.exists() else "http"
    return f"{scheme}://{ip}:8000"


def _cloudflared_path() -> str | None:
    if CLOUDFLARED_EXE.exists():
        return str(CLOUDFLARED_EXE)
    found = shutil.which("cloudflared")
    return found


def _read_tunnel_output(process: subprocess.Popen) -> None:
    global _public_url, _tunnel_log, _tunnel_error
    pattern = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
    try:
        for line in process.stdout:
            if _stop_event.is_set():
                break
            line = line.strip()
            if line:
                _tunnel_log.append(line)
                if len(_tunnel_log) > 30:
                    _tunnel_log = _tunnel_log[-30:]
                if "failed" in line.lower() or "error" in line.lower() or "x509" in line.lower():
                    _tunnel_error = line
            match = pattern.search(line)
            if match:
                _public_url = match.group(0)
                _tunnel_error = None
    except Exception as error:
        _tunnel_error = str(error)


def stop_tunnel() -> None:
    """停掉隧道，回到局域网模式。"""
    global _mode, _tunnel_process, _public_url, _stop_event
    with _lock:
        _mode = "lan"
        _public_url = None
        _tunnel_error = None
        if _tunnel_process is not None:
            try:
                _tunnel_process.terminate()
                _tunnel_process.wait(timeout=5)
            except Exception:
                try:
                    _tunnel_process.kill()
                except Exception:
                    pass
        _tunnel_process = None


def start_tunnel() -> dict:
    """启动 cloudflared 隧道；不阻塞请求，立即返回，由状态接口轮询公网地址。"""
    global _mode, _tunnel_process, _public_url, _stop_event, _tunnel_error
    with _lock:
        if _mode == "tunnel" and _tunnel_process is not None and _tunnel_process.poll() is None:
            return status()

        stop_tunnel()

        binary = _cloudflared_path()
        if binary is None:
            _tunnel_error = "cloudflared 未就绪，请先确认项目 bin/cloudflared.exe 存在"
            return {"ok": False, "error": _tunnel_error}

        _stop_event = threading.Event()
        _public_url = None
        _tunnel_error = None
        _tunnel_process = subprocess.Popen(
            [binary, "tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:8000"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        threading.Thread(target=_read_tunnel_output, args=(_tunnel_process,), daemon=True).start()
        _mode = "tunnel"
        return status()


def set_mode(mode: str) -> dict:
    if mode == "lan":
        stop_tunnel()
        return status()
    if mode == "tunnel":
        result = start_tunnel()
        if not result.get("ok"):
            return result
        return status()
    raise ValueError("mode 必须是 lan 或 tunnel")


def status() -> dict:
    with _lock:
        running = bool(
            _tunnel_process is not None and _tunnel_process.poll() is None
        )
        mode = _mode
        if mode == "tunnel" and running and not _public_url and not _tunnel_error:
            state = "starting"
        elif mode == "tunnel" and _public_url:
            state = "running"
        elif mode == "tunnel" and _tunnel_error:
            state = "error"
        else:
            state = "lan"
        return {
            "mode": mode,
            "state": state,
            "lan_url": lan_url(),
            "public_url": _public_url,
            "error": _tunnel_error,
            "cloudflared_ready": _cloudflared_path() is not None,
            "tunnel_running": running,
        }
