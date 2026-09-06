# -*- coding: utf-8 -*-
"""用户与登录会话的持久层。

设计取舍
--------
1. 用户 id 用 uuid 而非自增整数：日后多台机器间同步数据时不会撞号。
2. 登录会话表只存令牌的 SHA-256，明文令牌不落库（见 auth.py 说明）。
3. 会话过期采用滑动续期：每次访问顺延，长期不用自然失效。
4. 首个注册用户自动成为管理员——实验室里没有运维，得有人能建账号。
"""

from __future__ import annotations

import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone

import auth
from database.db import get_connection

SESSION_TTL_DAYS = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def ensure_schema(connection) -> None:
    """建表；由 initialize_database 调用，可重复执行。"""
    connection.execute("""CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        display_name TEXT NOT NULL DEFAULT '',
        password_hash TEXT NOT NULL,
        is_admin INTEGER NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_login_at TEXT)""")
    connection.execute("""CREATE TABLE IF NOT EXISTS user_sessions (
        token_hash TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        expires_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE)""")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_sessions_user ON user_sessions(user_id)")


def _row_to_user(row):
    if row is None:
        return None
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"] or row["username"],
        "is_admin": bool(row["is_admin"]),
        "is_active": bool(row["is_active"]),
        "created_at": row["created_at"],
        "last_login_at": row["last_login_at"],
    }


def count_users() -> int:
    with closing(get_connection()) as connection:
        return int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])


def list_users() -> list:
    with closing(get_connection()) as connection:
        rows = connection.execute(
            "SELECT * FROM users ORDER BY created_at, username").fetchall()
    return [_row_to_user(row) for row in rows]


def find_by_username(username: str):
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return _row_to_user(row)


def find_by_id(user_id: str):
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_user(row)


def create_user(username: str, password: str, display_name: str = "",
                *, is_admin=None):
    """建账号。is_admin 缺省时，首个用户自动为管理员。"""
    name = auth.normalize_username(username)
    auth.validate_password(password)
    password_hash = auth.hash_password(password)
    user_id = str(uuid.uuid4())
    with closing(get_connection()) as connection, connection:
        existing = connection.execute(
            "SELECT 1 FROM users WHERE username = ?", (name,)).fetchone()
        if existing:
            raise auth.AuthError("该用户名已被占用。")
        if is_admin is None:
            total = int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])
            admin_flag = 1 if total == 0 else 0
        else:
            admin_flag = 1 if is_admin else 0
        connection.execute(
            "INSERT INTO users (id, username, display_name, password_hash, is_admin)"
            " VALUES (?, ?, ?, ?, ?)",
            (user_id, name, (display_name or "").strip() or name,
             password_hash, admin_flag),
        )
        first_user = admin_flag == 1 and is_admin is None
    if first_user:
        # 首个账号继承升级前的既有数据，否则历史会话会集体变成「无主」而消失。
        claim_orphaned_data(user_id)
    return find_by_id(user_id)


def verify_login(username: str, password: str):
    """口令正确且账号启用才返回用户；其余一律 None，不区分原因。

    不区分是刻意的：把「用户名不存在」和「口令错误」分开回报，
    等于送给攻击者一个账号枚举接口。
    """
    try:
        name = auth.normalize_username(username)
    except auth.AuthError:
        auth.dummy_verify()
        return None
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE username = ?", (name,)).fetchone()
    if row is None:
        auth.dummy_verify()
        return None
    if not auth.verify_password(password, row["password_hash"]):
        return None
    if not bool(row["is_active"]):
        return None
    if auth.needs_rehash(row["password_hash"]):
        _upgrade_hash(row["id"], password)
    with closing(get_connection()) as connection, connection:
        connection.execute(
            "UPDATE users SET last_login_at = ? WHERE id = ?",
            (_stamp(_now()), row["id"]))
    return find_by_id(row["id"])


def _upgrade_hash(user_id: str, password: str) -> None:
    with closing(get_connection()) as connection, connection:
        connection.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                           (auth.hash_password(password), user_id))


def set_password(user_id: str, password: str, *, revoke_sessions: bool = True) -> None:
    """改密默认踢掉全部登录态：改密的动机通常正是怀疑别人在用这个账号。"""
    auth.validate_password(password)
    with closing(get_connection()) as connection, connection:
        cursor = connection.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                                    (auth.hash_password(password), user_id))
        if cursor.rowcount == 0:
            raise auth.AuthError("用户不存在。")
        if revoke_sessions:
            connection.execute("DELETE FROM user_sessions WHERE user_id = ?", (user_id,))


def update_display_name(user_id: str, display_name: str) -> dict | None:
    """修改用户的显示名/昵称；空字符串表示恢复为用户名。"""
    name = (display_name or "").strip()
    normalized_max = 64
    if len(name) > normalized_max:
        name = name[:normalized_max]
    with closing(get_connection()) as connection, connection:
        if name:
            connection.execute(
                "UPDATE users SET display_name = ? WHERE id = ?",
                (name, user_id),
            )
        else:
            connection.execute(
                "UPDATE users SET display_name = '' WHERE id = ?",
                (user_id,),
            )
    return find_by_id(user_id)


def set_active(user_id: str, active: bool) -> None:
    with closing(get_connection()) as connection, connection:
        connection.execute("UPDATE users SET is_active = ? WHERE id = ?",
                           (1 if active else 0, user_id))
        if not active:
            connection.execute("DELETE FROM user_sessions WHERE user_id = ?", (user_id,))


def create_session(user_id: str, *, ttl_days: int = SESSION_TTL_DAYS) -> str:
    """返回明文令牌（只此一次）；库里只留散列。"""
    issued = auth.issue_session_token()
    expires = _now() + timedelta(days=ttl_days)
    with closing(get_connection()) as connection, connection:
        connection.execute(
            "INSERT INTO user_sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (issued.token_hash, user_id, _stamp(expires)),
        )
    return issued.token


def resolve_session(token: str, *, ttl_days: int = SESSION_TTL_DAYS):
    """令牌换用户；顺带滑动续期。过期或账号停用一律 None。"""
    if not token:
        return None
    try:
        token_hash = auth.hash_session_token(token)
    except auth.AuthError:
        return None
    now = _now()
    with closing(get_connection()) as connection, connection:
        row = connection.execute(
            "SELECT s.expires_at AS s_expires, u.* FROM user_sessions s"
            " JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?",
            (token_hash,),
        ).fetchone()
        if row is None:
            return None
        if _stamp(now) >= row["s_expires"]:
            connection.execute(
                "DELETE FROM user_sessions WHERE token_hash = ?", (token_hash,))
            return None
        if not bool(row["is_active"]):
            return None
        connection.execute(
            "UPDATE user_sessions SET last_seen_at = ?, expires_at = ? WHERE token_hash = ?",
            (_stamp(now), _stamp(now + timedelta(days=ttl_days)), token_hash),
        )
    return _row_to_user(row)


def delete_session(token: str) -> None:
    if not token:
        return
    try:
        token_hash = auth.hash_session_token(token)
    except auth.AuthError:
        return
    with closing(get_connection()) as connection, connection:
        connection.execute("DELETE FROM user_sessions WHERE token_hash = ?", (token_hash,))


def list_sessions(user_id: str, limit: int = 50) -> list[dict]:
    """列出该用户的登录设备/会话（不暴露令牌散列）。"""
    with closing(get_connection()) as connection:
        rows = connection.execute(
            """SELECT created_at, expires_at, last_seen_at
               FROM user_sessions WHERE user_id=?
               ORDER BY created_at DESC LIMIT ?""",
            (user_id, int(limit)),
        ).fetchall()
    return [dict(row) for row in rows]


def revoke_all_sessions(user_id: str) -> int:
    with closing(get_connection()) as connection, connection:
        cursor = connection.execute(
            "DELETE FROM user_sessions WHERE user_id = ?", (user_id,))
        return cursor.rowcount or 0


def purge_expired_sessions() -> int:
    with closing(get_connection()) as connection, connection:
        cursor = connection.execute(
            "DELETE FROM user_sessions WHERE expires_at <= ?", (_stamp(_now()),))
        return cursor.rowcount or 0


OWNED_TABLES = ("conversations", "memories", "notifications", "experiments")


def claim_orphaned_data(user_id: str) -> dict:
    """把升级前遗留的无主数据划归指定账号。

    为什么需要这一步：登录功能是后加的，库里已经有会话、记录和提醒。
    如果不认领，这些数据会因为 user_id IS NULL 而对所有人不可见——
    表现为「升级完历史全没了」，比报错更吓人。

    只认领 user_id IS NULL 的行，因此重复调用是安全的，
    也绝不会把别人的数据划走。
    """
    claimed = {}
    with closing(get_connection()) as connection, connection:
        for table in OWNED_TABLES:
            cursor = connection.execute(
                f"UPDATE {table} SET user_id = ? WHERE user_id IS NULL", (user_id,))
            if cursor.rowcount:
                claimed[table] = cursor.rowcount
    return claimed


def count_orphaned_data() -> dict:
    """统计尚无归属的数据，供诊断与迁移前确认。"""
    counts = {}
    with closing(get_connection()) as connection:
        for table in OWNED_TABLES:
            value = connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE user_id IS NULL").fetchone()[0]
            if value:
                counts[table] = int(value)
    return counts
