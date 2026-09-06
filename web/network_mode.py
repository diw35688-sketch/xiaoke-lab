# -*- coding: utf-8 -*-
"""网络模式管理：在网页 UI 里切换「局域网」或「公网隧道」。

所有操作都通过接口完成，不需要用户去碰启动脚本。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import phone_access

if getattr(sys, "frozen", False):
    # PyInstaller 冻结运行时：__file__ 是虚拟路径，必须用 _MEIPASS 定位真实资源。
    REPO_ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
else:
    REPO_ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = REPO_ROOT / "bin"
CLOUDFLARED_EXE = BIN_DIR / "cloudflared.exe"
STATE_FILE = REPO_ROOT / "data" / "network_mode.json"

_lock = threading.RLock()
_mode = "lan"
_tunnel_process = None
_public_url = None
_stop_event = threading.Event()
_tunnel_log: list[str] = []
_tunnel_error: str | None = None
_watchdog_started = False
_WATCHDOG_INTERVAL_SECONDS = 20


def _load_persisted_mode() -> str:
    """读取上次退出/重启前的网络模式；没有记录或损坏都回到 lan。"""
    try:
        raw = STATE_FILE.read_text(encoding="utf-8").strip()
        data = json.loads(raw) if raw else {}
        return "tunnel" if data.get("mode") == "tunnel" else "lan"
    except Exception:
        return "lan"


def _save_mode(mode: str) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(
            json.dumps({"mode": mode}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        # 持久化失败不影响本次运行，下次重启最多回到 lan。
        pass


def lan_url() -> str:
    ip = phone_access.lan_ip()
    # 当前服务用 HTTP 启动（restart_server.ps1 无 --ssl-keyfile）。
    # 不能因为存在 cert.pem 就返回 https，否则手机扫码会连不上。
    return f"http://{ip}:8000"


def _cloudflared_path() -> str | None:
    if CLOUDFLARED_EXE.exists():
        return str(CLOUDFLARED_EXE)
    found = shutil.which("cloudflared")
    return found


def _tunnel_origin() -> tuple[str, list[str]]:
    """返回 cloudflared 转发到本机的地址与附加参数。

    PyInstaller 冻结版用 start_best 启动，本地服务是 HTTPS 自签名；
    cloudflared 必须用 https:// 转发并跳过证书校验，否则公网访问 502。
    源码开发环境（restart_server.ps1）是 HTTP，保持原样。
    """
    if getattr(sys, "frozen", False):
        return "https://127.0.0.1:8000", ["--no-tls-verify"]
    return "http://127.0.0.1:8000", []


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
                lower = line.lower()
                # cloudflared 正常启动后会先做 UDP/QUIC precheck，常见“QUIC connection
                # failed”只是回退到 TCP，不代表隧道不可用。拿到 public_url 后只把真正的
                # 致命错误记进 _tunnel_error，避免状态字段一直挂着一行吓人的非致命日志。
                if _public_url is None:
                    if "failed" in lower or "error" in lower or "x509" in lower:
                        _tunnel_error = line
                else:
                    if (
                        "fatal" in lower
                        or "x509" in lower
                        or "unable to start" in lower
                        or "failed to connect to cloudflared" in lower
                        or "failed to register tunnel" in lower
                    ):
                        _tunnel_error = line
            match = pattern.search(line)
            if match:
                _public_url = match.group(0)
                _tunnel_error = None
    except Exception as error:
        _tunnel_error = str(error)


def _kill_matching_cloudflared() -> None:
    """清理所有指向本机 8000 的 cloudflared 进程。

    历史问题：服务被强杀/重启时，旧的 cloudflared 进程会变成孤儿继续跑，
    导致本机积累大量临时隧道进程，用户手上的旧二维码时好时坏。
    """
    import sys
    try:
        if sys.platform.startswith("win"):
            # Windows 用 PowerShell 按命令行精确匹配，避免误杀别的 cloudflared。
            script = (
                "Get-CimInstance Win32_Process | "
                "Where-Object { $_.Name -eq 'cloudflared.exe' -and "
                "($_.CommandLine -like '*--url http://127.0.0.1:8000*' -or "
                "$_.CommandLine -like '*--url https://127.0.0.1:8000*') } | "
                "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                timeout=15,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            subprocess.run(
                ["pkill", "-f", r"cloudflared.*--url (http|https)://127\.0\.0\.1:8000"],
                timeout=5,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
    except Exception:
        # 清理失败不能阻塞启停；保留后续 start_tunnel 自己的进程管理。
        pass


def stop_tunnel() -> None:
    """停掉隧道，回到局域网模式。"""
    global _mode, _tunnel_process, _public_url, _stop_event
    with _lock:
        _mode = "lan"
        _public_url = None
        _tunnel_error = None
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
        _save_mode("lan")
    # 离开锁再清理历史孤儿，避免在锁内执行外部命令。
    _kill_matching_cloudflared()


def _start_watchdog_once() -> None:
    """只启动一次看门狗；看门狗只在隧道模式开启时执行重启。"""
    global _watchdog_started
    with _lock:
        if _watchdog_started:
            return
        _watchdog_started = True
        threading.Thread(target=_tunnel_watchdog, daemon=True).start()


def start_tunnel() -> dict:
    """启动 cloudflared 隧道；不阻塞请求，立即返回，由状态接口轮询公网地址。"""
    global _mode, _tunnel_process, _public_url, _stop_event, _tunnel_error
    with _lock:
        if _mode == "tunnel" and _tunnel_process is not None and _tunnel_process.poll() is None:
            _start_watchdog_once()
            return status()

        stop_tunnel()

        binary = _cloudflared_path()
        if binary is None:
            _tunnel_error = "cloudflared 未就绪，请先确认项目 bin/cloudflared.exe 存在"
            return {"ok": False, "error": _tunnel_error}

        _stop_event = threading.Event()
        _public_url = None
        _tunnel_error = None
        origin, extra_args = _tunnel_origin()
        _tunnel_process = subprocess.Popen(
            [binary, "tunnel", "--no-autoupdate", *extra_args, "--url", origin],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        threading.Thread(target=_read_tunnel_output, args=(_tunnel_process,), daemon=True).start()
        _mode = "tunnel"
        _save_mode("tunnel")
        _start_watchdog_once()
        return status()


def _tunnel_watchdog() -> None:
    """公网隧道守护：进程退出/报错时自动重新拉起，保证稳定上线。"""
    global _watchdog_started
    while True:
        time.sleep(_WATCHDOG_INTERVAL_SECONDS)
        try:
            state = status()
            if state.get("mode") != "tunnel":
                continue
            should_restart = (
                state.get("state") == "error"
                or (not state.get("tunnel_running") and not state.get("public_url"))
                or (state.get("state") == "starting" and not state.get("public_url") and state.get("error"))
            )
            if should_restart:
                start_tunnel()
        except Exception:
            pass


def ensure_tunnel_started() -> dict:
    """启动时调用：如果公网隧道没在跑，就自动启动并开启守护线程。"""
    _start_watchdog_once()
    state = status()
    if state.get("state") in ("running", "starting"):
        return state
    return start_tunnel()


def restore_tunnel_mode() -> dict:
    """应用启动时恢复上次的模式。

    - 上次是公网隧道：自动拉起并启动看门狗，保证重启后手机入口仍可用。
    - 上次是局域网/无记录：不自动暴露公网，只清理可能残留的 cloudflared。
    """
    global _mode
    saved = _load_persisted_mode()
    if saved == "tunnel":
        _mode = "tunnel"
        return ensure_tunnel_started()

    _mode = "lan"
    _kill_matching_cloudflared()
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
    global _public_url, _tunnel_error
    with _lock:
        running = bool(
            _tunnel_process is not None and _tunnel_process.poll() is None
        )
        mode = _mode
        if mode == "tunnel" and not running:
            # 进程已死但 public_url 还留在内存里会让上层误以为隧道仍正常，
            # 必须清掉旧地址并进入 error，看门狗才会自动重启。
            _public_url = None
            if not _tunnel_error:
                _tunnel_error = "cloudflared 隧道进程已退出，等待自动重连"
            state = "error"
        elif mode == "tunnel" and _public_url:
            state = "running"
        elif mode == "tunnel":
            state = "starting"
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
