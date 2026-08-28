"""局域网/公网访问令牌。

本机访问不需要令牌；从其他设备访问时，入口 URL 必须携带令牌。
令牌首次校验成功后写入 HttpOnly cookie，后续 fetch 请求会自动携带。
"""

from __future__ import annotations

import secrets
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ACCESS_TOKEN_PARAM = "access_token"
ACCESS_TOKEN_COOKIE = "ai107_access_token"

_access_token = secrets.token_urlsafe(24)


def current_token() -> str:
    return _access_token


def is_valid(candidate: str | None) -> bool:
    return bool(candidate) and secrets.compare_digest(str(candidate), _access_token)


def add_token(url: str) -> str:
    """给手机/公网入口 URL 添加访问令牌，保留原查询参数。"""
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query[ACCESS_TOKEN_PARAM] = _access_token
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def without_token(url: str) -> str:
    """从已验证的入口 URL 中删除令牌，避免它长期留在地址栏。"""
    parts = urlsplit(url)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key != ACCESS_TOKEN_PARAM
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
