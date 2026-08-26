# -*- coding: utf-8 -*-
"""手机扫码访问启动器：把实验助手发布到局域网，并在终端打印二维码。

为什么需要 HTTPS：
  手机浏览器（Chrome/Safari）只允许在 localhost 或 HTTPS 页面使用麦克风。
  同 WiFi 下用 HTTPS 自签名证书，手机信任一次证书即可获得最低延迟的语音链路。

用法（仓库根目录）：
  .\.venv\Scripts\python.exe scripts\start_phone_server.py [--port 8000] [--no-ssl]
"""

from __future__ import annotations

import argparse
import datetime
import ipaddress
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = REPO_ROOT / "web"
CERTS_DIR = WEB_DIR / "certs"
CERT_FILE = CERTS_DIR / "cert.pem"
KEY_FILE = CERTS_DIR / "key.pem"

sys.path.insert(0, str(WEB_DIR))
os.chdir(WEB_DIR)

import phone_access  # noqa: E402


def ensure_self_signed_cert(ip: str) -> tuple[str, str] | None:
    """没有现成证书时，尝试用 cryptography 生成一份自签名证书。

    生成后保存在 web/certs/，下次启动直接复用。
    """
    if CERT_FILE.exists() and KEY_FILE.exists():
        return str(CERT_FILE), str(KEY_FILE)

    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError:
        return None

    CERTS_DIR.mkdir(exist_ok=True)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "AI107-Lab-Assistant")])

    san = x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address(ip))])
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
    """装了 qrcode 就打印终端二维码；没装就只打印 URL。"""
    try:
        import qrcode

        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make(fit=True)
        qr.print_ascii(invert=False)
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="手机扫码访问实验助手")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--ip", type=str, default=None,
                        help="指定发布 IP（默认自动探测；多网卡时自动探测可能选错，"
                             "用 route print 找默认网关所在网卡的 IP 传入）")
    parser.add_argument("--no-ssl", action="store_true", help="强制使用 HTTP（手机麦克风会被浏览器禁用）")
    args = parser.parse_args()

    ip = args.ip or phone_access.lan_ip()
    scheme = "http"
    ssl_kwargs: dict = {}

    if not args.no_ssl:
        cert_pair = ensure_self_signed_cert(ip)
        if cert_pair is not None:
            scheme = "https"
            ssl_kwargs = {"ssl_keyfile": cert_pair[1], "ssl_certfile": cert_pair[0]}
        else:
            print("[!] 未安装 cryptography，无法自动生成 HTTPS 证书。")
            print("    手机访问麦克风必须 HTTPS。可任选其一：")
            print("    1) .\\.venv\\Scripts\\python.exe -m pip install cryptography qrcode")
            print("    2) 用 cloudflared tunnel --url http://localhost:8000 走临时公网 HTTPS")

    url = f"{scheme}://{ip}:{args.port}"
    print("=" * 56)
    print("实验助手已发布，手机和电脑连同一个 WiFi")
    print(f"  桌面访问: {scheme}://127.0.0.1:{args.port}")
    print(f"  手机访问: {url}")
    print(f"  二维码页: {scheme}://127.0.0.1:{args.port}/phone")
    if scheme == "https":
        print("  HTTPS 自签名证书已就绪；手机首次打开需信任证书")
    print("=" * 56)
    print_ascii_qr(url)

    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=args.port, **ssl_kwargs)


if __name__ == "__main__":
    main()
