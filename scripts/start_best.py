# -*- coding: utf-8 -*-
"""唯一启动器：自动检查安装状态 → 启动 HTTPS 局域网服务 → 打印手机二维码。

用户只需要双击仓库根目录的 start.bat，其他都不需要管。
"""

from __future__ import annotations

import argparse
import datetime
import ipaddress
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

if getattr(sys, "frozen", False):
    REPO_ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
else:
    REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = REPO_ROOT / "web"
CERTS_DIR = WEB_DIR / "certs"
CERT_FILE = CERTS_DIR / "cert.pem"
KEY_FILE = CERTS_DIR / "key.pem"
SETUP_MARKER = REPO_ROOT / "models" / ".setup_done"
MODEL_FILE = (
    REPO_ROOT
    / "models"
    / "modelscope_cache"
    / "models"
    / "iic--SenseVoiceSmall"
    / "snapshots"
    / "master"
    / "model.pt"
)
MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"
BIN_DIR = REPO_ROOT / "bin"
CLOUDFLARED_EXE = BIN_DIR / "cloudflared.exe"
CLOUDFLARED_URL = (
    "https://github.com/cloudflare/cloudflared/releases/latest/download/"
    "cloudflared-windows-amd64.exe"
)

# The Web app imports both top-level modules from ``web`` (for example
# ``phone_access``) and shared application/domain modules from ``src``.
# Running this file as ``python scripts/start_best.py`` only puts ``scripts``
# on sys.path, so changing cwd to ``web`` is not enough for ``import src``.
# Keep both roots explicit; this also makes startup independent of the shell's
# original working directory.
for import_root in (str(REPO_ROOT), str(WEB_DIR)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)
os.chdir(WEB_DIR)

import phone_access  # noqa: E402


def find_cloudflared() -> str | None:
    found = shutil.which("cloudflared")
    if found:
        return found
    if CLOUDFLARED_EXE.exists():
        return str(CLOUDFLARED_EXE)
    return None


def download_cloudflared() -> str:
    BIN_DIR.mkdir(exist_ok=True)
    tmp = CLOUDFLARED_EXE.with_suffix(".exe.download")
    print("正在自动下载 cloudflared，请稍候...")
    with urllib.request.urlopen(CLOUDFLARED_URL, timeout=90) as response, open(tmp, "wb") as fh:
        shutil.copyfileobj(response, fh)
    tmp.replace(CLOUDFLARED_EXE)
    return str(CLOUDFLARED_EXE)


def run_tunnel_mode(cloudflared: str) -> None:
    """公网模式：手机在任何网络都能访问，不需要局域网。"""
    import uvicorn

    server = uvicorn.Server(
        uvicorn.Config("app:app", host="127.0.0.1", port=8000, log_level="warning")
    )
    threading.Thread(target=server.run, daemon=True).start()

    command = [cloudflared, "tunnel", "--url", "http://127.0.0.1:8000"]
    print("[*] 正在启动 cloudflared 隧道...")
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    pattern = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
    public_url = None
    try:
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            match = pattern.search(line)
            if match:
                public_url = match.group(0)
                print("=" * 58)
                print("实验助手已通过公网隧道启动（手机无需同一 WiFi）")
                print(f"  电脑访问: http://127.0.0.1:8000")
                print(f"  手机访问: {public_url}")
                print(f"  二维码页: {public_url}/phone")
                print("=" * 58)
                print_ascii_qr(public_url)

        if public_url is None:
            print("[!] 隧道启动失败：没有读取到公网地址。")
            print("    你可以稍后重试，或安装 cloudflared 后再次运行。")
    except KeyboardInterrupt:
        pass
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        server.should_exit = True


def run_lan_mode() -> None:
    """局域网模式：同 WiFi 下延迟最低。"""
    ip = phone_access.lan_ip()
    scheme = "http"
    ssl_kwargs: dict = {}
    cert_pair = ensure_self_signed_cert(ip)
    if cert_pair is not None:
        scheme = "https"
        ssl_kwargs = {"ssl_keyfile": cert_pair[1], "ssl_certfile": cert_pair[0]}

    url = f"{scheme}://{ip}:8000"
    print("=" * 58)
    print("实验助手已启动（局域网模式）")
    print(f"  电脑访问: {scheme}://127.0.0.1:8000")
    print(f"  手机访问: {url}")
    print(f"  二维码页: {scheme}://127.0.0.1:8000/phone")
    if scheme == "https":
        print("  已启用 HTTPS 自签名证书；手机首次打开需信任证书")
    else:
        print("  未启用 HTTPS；手机麦克风可能被浏览器禁用")
    print("=" * 58)
    print_ascii_qr(url)

    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, **ssl_kwargs)



def ensure_ready() -> None:
    # 模型文件已在项目内就认为安装完成；这样已装好的老用户不会被要求重复 setup。
    if MODEL_FILE.exists():
        return
    print("首次运行或模型缺失，正在自动安装/下载（仅首次需要）...")
    subprocess.check_call(
        [sys.executable, str(REPO_ROOT / "scripts" / "setup.py"), "--mirror", MIRROR]
    )


def ensure_self_signed_cert(ip: str) -> tuple[str, str] | None:
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError:
        return None

    if CERT_FILE.exists() and KEY_FILE.exists():
        try:
            current = x509.load_pem_x509_certificate(CERT_FILE.read_bytes())
            san = current.extensions.get_extension_for_class(
                x509.SubjectAlternativeName
            ).value
            if ipaddress.ip_address(ip) in san.get_values_for_type(x509.IPAddress):
                return str(CERT_FILE), str(KEY_FILE)
        except (ValueError, x509.ExtensionNotFound):
            pass
        # The active Wi-Fi address changed, or the old certificate was made for
        # a proxy/TUN adapter.  Replace it so the QR URL and certificate agree.

    CERTS_DIR.mkdir(exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "AI107-Lab-Assistant")])
    san = x509.SubjectAlternativeName(
        [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address(ip))]
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(san, critical=False)
        .sign(key, hashes.SHA256())
    )
    KEY_FILE.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))
    CERT_FILE.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return str(CERT_FILE), str(KEY_FILE)


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
    parser = argparse.ArgumentParser(description="实验助手启动器")
    parser.add_argument(
        "--mode",
        choices=["auto", "lan", "tunnel"],
        default="lan",
        help="auto=有隧道用隧道，否则局域网；lan=只局域网；tunnel=只公网隧道",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="只检查路径与启动条件，不下载模型、不启动服务",
    )
    args = parser.parse_args()

    if args.doctor:
        checks = {
            "仓库目录": REPO_ROOT.is_dir(),
            "启动脚本": (REPO_ROOT / "start.bat").is_file(),
            "虚拟环境": Path(sys.executable).resolve().parent.name.lower() == "scripts",
            "Web 入口": (WEB_DIR / "app.py").is_file(),
            "ASR 模型": MODEL_FILE.is_file(),
            "本地配置": (REPO_ROOT / ".env").is_file() or (WEB_DIR / "settings.json").is_file(),
        }
        print(f"仓库目录：{REPO_ROOT}")
        print(f"Python：{Path(sys.executable).resolve()}")
        for name, ready in checks.items():
            print(f"[{'OK' if ready else '--'}] {name}")
        print("体检完成：-- 表示首次启动时仍需自动准备，不代表程序损坏。")
        return

    ensure_ready()

    if args.mode == "lan":
        run_lan_mode()
        return

    if args.mode == "tunnel":
        cloudflared = find_cloudflared()
        if cloudflared is None:
            print("[*] 未检测到 cloudflared，尝试自动下载到项目 bin 目录...")
            cloudflared = download_cloudflared()
        run_tunnel_mode(cloudflared)
        return

    # auto：优先公网隧道，下载失败再回退局域网
    cloudflared = find_cloudflared()
    if cloudflared is None:
        print("[*] 未检测到 cloudflared，尝试自动下载到项目 bin 目录...")
        try:
            cloudflared = download_cloudflared()
        except Exception as error:
            print(f"[!] cloudflared 自动下载失败（{error}），本次先回退到局域网模式。")

    if cloudflared is not None:
        run_tunnel_mode(cloudflared)
        return

    run_lan_mode()


if __name__ == "__main__":
    main()
