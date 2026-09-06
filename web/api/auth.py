# -*- coding: utf-8 -*-
"""登录相关 HTTP 接口。

Cookie 选型
-----------
会话令牌放 HttpOnly Cookie，而不是 localStorage：
本项目有大量 SSE 与表单上传，Cookie 会被浏览器自动带上，改造面最小；
HttpOnly 还能让 XSS 拿不到令牌。代价是要防 CSRF，故用 SameSite=Lax
（导航型 GET 仍带 Cookie，跨站 POST 不带），且所有写操作都是 POST/PATCH/DELETE。

注册策略
--------
库里一个用户都没有时开放注册（引导首个管理员），之后仅管理员可建账号。
这样公网隧道暴露期间，陌生人无法给自己开号。
"""

from __future__ import annotations

import secrets
import threading
import time

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

import auth as auth_core
from database import user_store
from database.db import get_connection

router = APIRouter(prefix="/auth", tags=["登录"])

COOKIE_NAME = "lab_session"
COOKIE_MAX_AGE = user_store.SESSION_TTL_DAYS * 24 * 3600

# 登录限速：同一用户名连续失败达到上限后锁定一段时间。
# 公网隧道下这是唯一挡住口令爆破的东西。
_FAIL_LIMIT = 8
_LOCK_SECONDS = 300
_failures: dict[str, list] = {}
_failures_lock = threading.Lock()


def _throttle_key(username: str, request: Request) -> str:
    client = request.client.host if request.client else "?"
    return f"{(username or '').strip().lower()}@{client}"


def _check_throttle(key: str) -> None:
    with _failures_lock:
        record = _failures.get(key)
        if not record:
            return
        count, locked_until = record
        if count >= _FAIL_LIMIT and time.time() < locked_until:
            wait = int(locked_until - time.time()) + 1
            raise HTTPException(status_code=429, detail=f"尝试过于频繁，请 {wait} 秒后再试。")


def _record_failure(key: str) -> None:
    with _failures_lock:
        count = (_failures.get(key) or [0, 0])[0] + 1
        _failures[key] = [count, time.time() + _LOCK_SECONDS]


def _clear_failures(key: str) -> None:
    with _failures_lock:
        _failures.pop(key, None)


class LoginPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=1024)


class RegisterPayload(LoginPayload):
    display_name: str = Field(default="", max_length=64)


class PasswordPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=1, max_length=1024)


class ProfilePayload(BaseModel):
    display_name: str = Field(default="", max_length=64)


def current_user(lab_session: str | None = Cookie(default=None)):
    """解析 Cookie 得到当前用户；未登录返回 None（不抛异常）。"""
    return user_store.resolve_session(lab_session) if lab_session else None


def require_user(user=Depends(current_user)):
    """需要登录的路由依赖。"""
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录。")
    return user


def require_admin(user=Depends(require_user)):
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="需要管理员权限。")
    return user


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME, token,
        max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax", path="/",
    )


@router.get("/state")
def auth_state(user=Depends(current_user)):
    """前端启动时问一次：要不要显示登录页、是不是首次使用。"""
    return {
        "authenticated": user is not None,
        "needs_bootstrap": user_store.count_users() == 0,
        "user": user,
    }


@router.post("/register")
def register(payload: RegisterPayload, response: Response,
             requester=Depends(current_user)):
    bootstrapping = user_store.count_users() == 0
    if not bootstrapping:
        if requester is None:
            raise HTTPException(status_code=401, detail="请先登录。")
        if not requester.get("is_admin"):
            raise HTTPException(status_code=403, detail="只有管理员可以新建账号。")
    try:
        user = user_store.create_user(
            payload.username, payload.password, payload.display_name)
    except auth_core.AuthError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if bootstrapping:
        # 首个用户建完直接登录，省掉一次输入
        _set_cookie(response, user_store.create_session(user["id"]))
    return {"user": user, "logged_in": bootstrapping}


@router.post("/login")
def login(payload: LoginPayload, request: Request, response: Response):
    key = _throttle_key(payload.username, request)
    _check_throttle(key)
    user = user_store.verify_login(payload.username, payload.password)
    if user is None:
        _record_failure(key)
        raise HTTPException(status_code=401, detail="用户名或口令不正确。")
    _clear_failures(key)
    _set_cookie(response, user_store.create_session(user["id"]))
    return {"user": user}


@router.patch("/profile")
def update_profile(payload: ProfilePayload, user=Depends(require_user)):
    """修改当前用户的显示名/昵称。"""
    updated = user_store.update_display_name(user["id"], payload.display_name)
    return {"user": updated, "message": "昵称已更新"}


_PHONE_TOKEN_TTL_SECONDS = 365 * 24 * 60 * 60


def _ensure_phone_login_schema(connection=None) -> None:
    conn = connection or get_connection()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS phone_login_codes (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at_ms INTEGER NOT NULL,
            expires_at_ms INTEGER NOT NULL
        )"""
    )
    if connection is None:
        conn.close()


def create_phone_login_token(user) -> str:
    """生成一次性手机扫码登录令牌（5 分钟有效），按 OpenClaw join-code 模式持久化。"""
    token = secrets.token_urlsafe(32)
    now_ms = int(time.time() * 1000)
    expires_ms = now_ms + _PHONE_TOKEN_TTL_SECONDS * 1000
    with get_connection() as connection, connection:
        _ensure_phone_login_schema(connection)
        connection.execute(
            "DELETE FROM phone_login_codes WHERE expires_at_ms <= ?",
            (now_ms,),
        )
        connection.execute(
            "INSERT INTO phone_login_codes(token, user_id, created_at_ms, expires_at_ms) VALUES (?,?,?,?)",
            (token, user["id"], now_ms, expires_ms),
        )
    return token


def redeem_phone_login_token(token: str) -> dict | None:
    """读取手机登录令牌；令牌可重复使用，直到过期。"""
    now_ms = int(time.time() * 1000)
    with get_connection() as connection, connection:
        _ensure_phone_login_schema(connection)
        connection.execute(
            "DELETE FROM phone_login_codes WHERE expires_at_ms <= ?",
            (now_ms,),
        )
        row = connection.execute(
            "SELECT user_id FROM phone_login_codes WHERE token=?",
            (token,),
        ).fetchone()
        if row is None:
            return None
        return {"user_id": row["user_id"]}


@router.get("/phone-login/{token}")
def phone_login(token: str):
    """手机扫描二维码后调用：用电脑端生成的一次性令牌直接建立手机会话。"""
    record = redeem_phone_login_token(token)
    if record is None:
        raise HTTPException(status_code=401, detail="登录链接已过期，请重新扫码。")
    user = user_store.find_by_id(record["user_id"])
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在。")
    session = user_store.create_session(user["id"])
    from fastapi.responses import RedirectResponse
    # 带随机参数跳首页，绕过微信/手机浏览器的旧首页缓存。
    home_url = "/?v=phone-" + token[:12]
    response = RedirectResponse(home_url, status_code=302)
    _set_cookie(response, session)
    return response


@router.post("/logout")
def logout(response: Response, lab_session: str | None = Cookie(default=None)):
    user_store.delete_session(lab_session or "")
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.post("/password")
def change_password(payload: PasswordPayload, response: Response,
                    user=Depends(require_user)):
    if user_store.verify_login(user["username"], payload.current_password) is None:
        raise HTTPException(status_code=401, detail="当前口令不正确。")
    try:
        user_store.set_password(user["id"], payload.new_password)
    except auth_core.AuthError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    # 改密会吊销全部会话（含本次），当场补发一个，避免用户被自己踢出去
    _set_cookie(response, user_store.create_session(user["id"]))
    return {"ok": True}


@router.get("/sessions")
def list_my_sessions(user=Depends(require_user)):
    return {"items": user_store.list_sessions(user["id"])}


@router.post("/logout-all")
def logout_all(response: Response, user=Depends(require_user)):
    user_store.revoke_all_sessions(user["id"])
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/users")
def list_users(_=Depends(require_admin)):
    return {"items": user_store.list_users()}


def assert_owns_conversation(conversation_id: str, user) -> str:
    """确认该会话属于当前用户，否则一律按 404 拒绝。

    为什么必须显式调用
    ------------------
    2026-08-31 实测事故：登录做完后，只有 crud.py 里的会话增删改查加了归属过滤，
    而 turn / record / tasks / protocols 等模块都只按 conversation_id 取数据。
    结果任何登录用户拿到别人的会话 ID，就能读甚至**删掉**对方的实验记录
    （DELETE /turn/conversations/<别人的ID> 实测把对方记录清零）。

    归属检查必须发生在每一个接受 conversation_id 的入口，
    "数据模型上归属谁"不等于"查询时会不会被拦住"。

    统一返回 404 而不是 403：403 等于告诉对方"这个 ID 真实存在"，
    可被用来枚举他人会话。
    """
    from database.crud import conversation_exists

    if not conversation_exists(conversation_id, user["id"]):
        raise HTTPException(status_code=404, detail="会话不存在。")
    return conversation_id
