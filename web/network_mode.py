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
    global _public_url, _tunnel_log
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
            match = pattern.search(line)
            if match:
                _public_url = match.group(0)
    except Exception:
        pass


def stop_tunnel() -> None:
    """停掉隧道，回到局域网模式。"""
    global _mode, _tunnel_process, _public_url, _stop_event
    with _lock:
        _mode = "lan"
        _public_url = None
        _stop_event.set()
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
    """启动 cloudflared 隧道，并等待公网 URL。"""
    global _mode, _tunnel_process, _public_url, _stop_event
    with _lock:
        if _mode == "tunnel" and _tunnel_process is not None and _tunnel_process.poll() is None and _public_url:
            return {"ok": True, "mode": "tunnel", "public_url": _public_url}

        stop_tunnel()

        binary = _cloudflared_path()
        if binary is None:
            return {"ok": False, "error": "cloudflared 未就绪，请先确认项目 bin/cloudflared.exe 存在"}

        _stop_event = threading.Event()
        _public_url = None
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

        deadline = time.time() + 25
        while time.time() < deadline:
            if _public_url is not None:
                return {"ok": True, "mode": "tunnel", "public_url": _public_url}
            if _tunnel_process.poll() is not None:
                break
            time.sleep(0.2)

        log_tail = "\n".join(_tunnel_log[-15:]) if _tunnel_log else "（无输出）"
        stop_tunnel()
        return {"ok": False, "error": "隧道启动失败，没有获得公网地址\n" + log_tail}


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
        return {
            "mode": _mode,
            "lan_url": lan_url(),
            "public_url": _public_url,
            "cloudflared_ready": _cloudflared_path() is not None,
            "tunnel_running": bool(
                _tunnel_process is not None and _tunnel_process.poll() is None
            ),
        }
