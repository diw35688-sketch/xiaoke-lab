# -*- coding: utf-8 -*-
"""手机扫码访问辅助：计算本机局域网地址，并尽量生成二维码。

本文件只做“网络地址 + 二维码展示”的装配，不参与业务判断。
qrcode 是可选依赖：装了会返回二维码 SVG；没装则返回 None，由调用方降级为纯文本。
"""

from __future__ import annotations

import socket


def lan_ip() -> str:
    """拿到本机在局域网里的 IP；拿不到时回退到 localhost。

    用 UDP connect 到公网地址不会真正发包，系统只是据此选一个出口网卡。
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.settimeout(0.5)
        s.connect(("223.5.5.5", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def phone_url(request, path: str = "/") -> str:
    """根据当前访问请求拼出手机应该打开的 URL。

    - 桌面端通过 localhost 打开时，把 host 换成本机局域网 IP（同 WiFi 延迟最低）。
    - 桌面端通过隧道域名打开时，保留隧道域名（公网访问，带 HTTPS）。
    """
    scheme = request.url.scheme if request else "http"
    raw_host = request.headers.get("host", "") if request else ""
    host = raw_host.split(":")[0] if raw_host else ""

    if host in {"", "127.0.0.1", "localhost"}:
        host = lan_ip()

    port = request.url.port if request and request.url.port else None
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        return f"{scheme}://{host}:{port}{path}"
    return f"{scheme}://{host}{path}"


def qr_svg(url: str) -> str | None:
    """生成二维码 SVG 字符串；qrcode 库未安装时返回 None。"""
    try:
        import qrcode
        import qrcode.image.svg

        qr = qrcode.QRCode(border=1, box_size=12)
        qr.add_data(url)
        qr.make(fit=True)
        image = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
        return image.to_string(encoding="unicode")
    except Exception:
        return None
