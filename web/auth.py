# -*- coding: utf-8 -*-
"""认证内核：口令散列、会话令牌、用户名规范化。

只做纯计算，不碰数据库、不碰 HTTP。这样它可以被完整测试，
而且日后换存储或换 Web 框架都不影响这里。

口令散列选型
------------
PBKDF2-HMAC-SHA256，600000 轮（OWASP 2023 对该算法的推荐值）。
选它是因为 Python 标准库自带，无需引入 bcrypt/argon2 依赖——
这个项目跑在实验室的本机上，少一个二进制依赖就少一次装不上的风险。
散列串自带算法名与轮数，将来提高轮数或换算法可以平滑迁移（见 needs_rehash）。

会话令牌
--------
明文令牌只发给浏览器，**数据库里只存它的 SHA-256**。
这样即使 lab_agent.db 被人拷走，也无法拿里面的值直接冒充登录态。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass

ALGORITHM = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 600_000
SALT_BYTES = 16
TOKEN_BYTES = 32

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.\-]{1,31}$")
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 1024  # 挡住超长口令导致的 CPU 拒绝服务


class AuthError(ValueError):
    """认证输入不合法。消息面向用户，不含内部细节。"""


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def normalize_username(raw: str) -> str:
    """统一小写去空白，避免 Alice 和 alice 变成两个账号。"""
    name = (raw or "").strip().lower()
    if not USERNAME_RE.match(name):
        raise AuthError(
            "用户名需为 2-32 位，以字母或数字开头，只能包含字母、数字、下划线、点、连字符。"
        )
    return name


def validate_password(raw: str) -> str:
    """只拦真正危险的：太短、超长、纯空白。不强制大小写符号混合。

    强制复杂度规则会把人逼去写便签贴屏幕上，在共用实验室里反而更不安全。
    """
    if not isinstance(raw, str):
        raise AuthError("口令必须是文本。")
    if len(raw) < MIN_PASSWORD_LENGTH:
        raise AuthError(f"口令至少 {MIN_PASSWORD_LENGTH} 位。")
    if len(raw) > MAX_PASSWORD_LENGTH:
        raise AuthError("口令过长。")
    if not raw.strip():
        raise AuthError("口令不能全是空白。")
    return raw


def hash_password(password: str, *, iterations: int | None = None) -> str:
    """产出自描述散列串：algorithm$iterations$salt$hash。

    轮数在调用时读取模块常量（而非绑定为默认参数），
    这样测试可以临时调低轮数，生产强度不受影响。
    """
    validate_password(password)
    if iterations is None:
        iterations = DEFAULT_ITERATIONS
    if iterations < 1:
        raise AuthError("迭代轮数必须为正。")
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{ALGORITHM}${iterations}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    """恒定时间比对。任何解析失败都返回 False，不抛异常、不泄露原因。"""
    if not isinstance(password, str) or not isinstance(encoded, str):
        return False
    try:
        algorithm, iterations_text, salt_text, hash_text = encoded.split("$")
        if algorithm != ALGORITHM:
            return False
        iterations = int(iterations_text)
        if iterations < 1:
            return False
        salt, expected = _unb64(salt_text), _unb64(hash_text)
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def needs_rehash(encoded: str, *, iterations: int | None = None) -> bool:
    """散列是否落后于当前强度；登录成功时可据此就地升级。"""
    if iterations is None:
        iterations = DEFAULT_ITERATIONS
    try:
        algorithm, iterations_text, _, _ = encoded.split("$")
    except (ValueError, AttributeError):
        return True
    if algorithm != ALGORITHM:
        return True
    try:
        return int(iterations_text) < iterations
    except ValueError:
        return True


# ---------- 会话令牌 ----------

@dataclass(frozen=True)
class IssuedToken:
    """新令牌：明文只回给浏览器，库里存 token_hash。"""

    token: str
    token_hash: str


def issue_session_token() -> IssuedToken:
    token = secrets.token_urlsafe(TOKEN_BYTES)
    return IssuedToken(token=token, token_hash=hash_session_token(token))


def hash_session_token(token: str) -> str:
    """令牌本身是高熵随机串，不需要加盐慢散列，单次 SHA-256 足够。"""
    if not isinstance(token, str) or not token.strip():
        raise AuthError("会话令牌不能为空。")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def dummy_verify() -> None:
    """用户不存在时也走一遍散列，抹平登录耗时差异。

    否则"用户名不存在"会比"口令错误"快一个数量级，
    攻击者据此可以枚举出哪些账号真实存在。
    """
    hashlib.pbkdf2_hmac("sha256", b"dummy", b"dummy-salt-16byt", DEFAULT_ITERATIONS)

