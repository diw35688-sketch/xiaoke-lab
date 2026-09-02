# -*- coding: utf-8 -*-
"""手机扫码访问辅助：计算本机局域网地址，并尽量生成二维码。

本文件只做“网络地址 + 二维码展示”的装配，不参与业务判断。
qrcode 是可选依赖：装了会返回二维码 SVG；没装则返回 None，由调用方降级为纯文本。
"""

from __future__ import annotations

import socket
import ipaddress
import re
import subprocess


def _usable_lan_ip(value: str) -> bool:
    """Return whether *value* can reasonably be reached by another LAN device."""
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    # 198.18.0.0/15 is reserved for benchmarking and is commonly used by
    # proxy/TUN adapters (for example Mihomo).  It must never win over Wi-Fi.
    benchmark = ipaddress.ip_network("198.18.0.0/15")
    return (
        address.version == 4
        and address.is_private
        and not address.is_loopback
        and not address.is_link_local
        and address not in benchmark
    )


def _windows_default_route_ips() -> list[tuple[int, str]]:
    """Read interface IPs on IPv4 default routes, best metric first."""
    try:
        output = subprocess.check_output(
            ["route", "print", "-4"],
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    routes: list[tuple[int, str]] = []
    pattern = re.compile(
        r"^\s*0\.0\.0\.0\s+0\.0\.0\.0\s+\S+\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+)\s*$"
    )
    for line in output.splitlines():
        match = pattern.match(line)
        if match and _usable_lan_ip(match.group(1)):
            routes.append((int(match.group(2)), match.group(1)))
    return sorted(routes)


def lan_ip() -> str:
    """拿到本机在局域网里的 IP；拿不到时回退到 localhost。

    用 UDP connect 到公网地址不会真正发包，系统只是据此选一个出口网卡。
    """
    # On Windows a proxy/TUN may install a metric-0 default route.  Consult all
    # default routes and discard non-LAN ranges before using the socket trick.
    route_ips = _windows_default_route_ips()
    if route_ips:
        return route_ips[0][1]

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.settimeout(0.5)
        s.connect(("223.5.5.5", 80))
        candidate = s.getsockname()[0]
        if _usable_lan_ip(candidate):
            return candidate
    except Exception:
        pass
    finally:
        s.close()

    try:
        candidates = socket.gethostbyname_ex(socket.gethostname())[2]
        return next(ip for ip in candidates if _usable_lan_ip(ip))
    except (OSError, StopIteration):
        return "127.0.0.1"


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
