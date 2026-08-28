# -*- coding: utf-8 -*-
"""手机扫码访问（非局域网/隧道模式）：用 cloudflared / zrok / ngrok 临时公网 HTTPS。

用法（仓库根目录）：
  .\.venv\Scripts\python.exe scripts\start_phone_tunnel.py --tunnel cloudflared

会自动：
  1. 在本机 127.0.0.1:8000 启动实验助手（HTTP）；
  2. 启动隧道程序，把公网 HTTPS 转发到本机 8000；
  3. 从隧道输出里抓取公网 URL，打印二维码。

手机无需和电脑同一个 WiFi，打开扫码得到的 URL 即可使用麦克风（因为公网 HTTPS）。
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = REPO_ROOT / "web"

sys.path.insert(0, str(WEB_DIR))
os.chdir(WEB_DIR)

import app as app_module  # noqa: E402
import phone_access  # noqa: E402
import access_control  # noqa: E402

TUNNEL_CANDIDATES = {
    "cloudflared": {
        "bin": "cloudflared",
        "args": lambda port: ["tunnel", "--url", f"http://127.0.0.1:{port}"],
        "url_pattern": re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com"),
        "hint": "安装: winget install Cloudflare.cloudflared  或从 https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/ 下载",
    },
    "zrok": {
        "bin": "zrok",
        "args": lambda port: ["share", "public", f"http://127.0.0.1:{port}"],
        "url_pattern": re.compile(r"https://[a-z0-9.-]+\.share\.zrok\.io"),
        "hint": "安装: winget install zrok  或 https://zrok.io/ （首次需要 zrok enable）",
    },
    "ngrok": {
        "bin": "ngrok",
        "args": lambda port: ["http", f"http://127.0.0.1:{port}"],
        "url_pattern": re.compile(r"https://[a-z0-9-]+\.(ngrok-free\.app|ngrok\.io)"),
        "hint": "安装: winget install ngrok.ngrok  或 https://ngrok.com/ （首次需要 ngrok config add-authtoken）",
    },
}


def find_tunnel(tunnel: str) -> str | None:
    binary = TUNNEL_CANDIDATES[tunnel]["bin"]
    found = shutil.which(binary)
    if found:
        return found
    for root in (Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))),):
        # cloudflared 常见安装位置：%LOCALAPPDATA%\\cloudflared\\cloudflared.exe
        for candidate in (root / binary / f"{binary}.exe", root / "Microsoft" / "WinGet" / "Packages"):
            if candidate.is_file():
                return str(candidate)
    return None


def print_ascii_qr(url: str) -> None:
    try:
        import qrcode

        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make(fit=True)
        qr.print_ascii(invert=False)
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="手机扫码访问（隧道模式）")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--tunnel", choices=sorted(TUNNEL_CANDIDATES), default="cloudflared")
    args = parser.parse_args()

    tunnel = args.tunnel
    binary = find_tunnel(tunnel)
    if binary is None:
        print(f"[!] 找不到 {tunnel}。")
        print(f"    {TUNNEL_CANDIDATES[tunnel]['hint']}")
        print("    安装后重新运行本脚本。")
        sys.exit(1)

    import uvicorn

    server = uvicorn.Server(
        uvicorn.Config(app_module.app, host="127.0.0.1", port=args.port, log_level="warning")
    )

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    command = [binary] + TUNNEL_CANDIDATES[tunnel]["args"](args.port)
    print(f"[*] 正在启动隧道：{' '.join(command)}")
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    public_url = None
    try:
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            match = TUNNEL_CANDIDATES[tunnel]["url_pattern"].search(line)
            if match:
                public_url = match.group(0)
                protected_url = access_control.add_token(public_url)
                print("=" * 56)
                print(f"隧道已建立，手机浏览器直接打开：{protected_url}")
                print(f"桌面二维码页：{access_control.add_token(public_url + '/phone')}")
                print("=" * 56)
                print_ascii_qr(protected_url)
                # 打印后继续读输出，保持隧道存活；URL 一般只出现一次。
        if public_url is None:
            print("[!] 未从隧道输出中解析到公网 URL，请把上面的输出发给我。")
    except KeyboardInterrupt:
        pass
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        server.should_exit = True
        print("隧道已关闭。")


if __name__ == "__main__":
    main()
