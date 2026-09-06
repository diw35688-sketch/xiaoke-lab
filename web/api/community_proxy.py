# -*- coding: utf-8 -*-
"""远程社区 API 代理：前端只访问本地 /community-proxy/*，远程地址不出现在浏览器。

远程优先：把全局登录身份透传给远程社区（X-Lab-User-*）。
如果远程旧版本不支持新接口或不可用，自动回退到本地社区库，保证功能不中断。
"""
import json
import logging
import re

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import Response

import settings_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/community-proxy", tags=["社区代理"])


def _query_map(request: Request) -> dict:
    from urllib.parse import parse_qs
    parsed = parse_qs(request.url.query)
    return {key: values[0] for key, values in parsed.items() if values}


def _json_response(data, status_code: int = 200) -> Response:
    return Response(
        json.dumps(data, ensure_ascii=False),
        status_code=status_code,
        media_type="application/json",
    )


def _fallback_local(request: Request, path: str, method: str, body: dict | None) -> Response | None:
    """把远程社区路径映射到本地 /community 路由。"""
    from api.community import (
        CommentPayload,
        PublishPayload,
        add_comment,
        delete_comment,
        delete_entry,
        import_entry,
        like_entry,
        list_community,
        list_comments,
        publish,
    )

    user = getattr(request.state, "user", None)
    path = path.strip("/")
    parts = [p for p in path.split("/") if p]
    q = _query_map(request)

    # GET /community
    if parts == ["community"] and method == "GET":
        try:
            return _json_response(list_community(
                q=q.get("q", ""), kind=q.get("kind", ""), limit=int(q.get("limit", 200) or 200)
            ))
        except Exception as error:
            return _json_response({"detail": str(error)}, 500)

    # POST /community
    if parts == ["community"] and method == "POST":
        if not user:
            return _json_response({"detail": "请先登录"}, 401)
        try:
            payload = PublishPayload(**body or {})
            return _json_response(publish(payload, user))
        except Exception as error:
            return _json_response({"detail": str(error)}, 400)

    # GET /community/{id}/download
    if len(parts) == 3 and parts[:2] == ["community"] and parts[2] == "download" and method == "GET":
        if not user:
            return _json_response({"detail": "请先登录"}, 401)
        try:
            return _json_response(import_entry(int(parts[1])))
        except Exception as error:
            return _json_response({"detail": str(error)}, 404)

    # POST /community/{id}/like
    if len(parts) == 3 and parts[:2] == ["community"] and parts[2] == "like" and method == "POST":
        if not user:
            return _json_response({"detail": "请先登录"}, 401)
        try:
            return _json_response(like_entry(int(parts[1]), user))
        except Exception as error:
            return _json_response({"detail": str(error)}, 404)

    # GET/POST /community/{id}/comments
    if len(parts) == 3 and parts[:2] == ["community"] and parts[2] == "comments":
        entry_id = int(parts[1])
        if method == "GET":
            try:
                return _json_response(list_comments(entry_id))
            except Exception as error:
                return _json_response({"detail": str(error)}, 404)
        if method == "POST":
            if not user:
                return _json_response({"detail": "请先登录"}, 401)
            try:
                payload = CommentPayload(**body or {})
                return _json_response(add_comment(entry_id, payload, user))
            except Exception as error:
                return _json_response({"detail": str(error)}, 400)

    # DELETE /community/comments/{comment_id}
    if len(parts) == 3 and parts[:2] == ["community", "comments"] and method == "DELETE":
        if not user:
            return _json_response({"detail": "请先登录"}, 401)
        try:
            return _json_response(delete_comment(int(parts[2]), user))
        except Exception as error:
            return _json_response({"detail": str(error)}, 403)

    # DELETE /community/{id}
    if len(parts) == 2 and parts[0] == "community" and method == "DELETE":
        try:
            return _json_response(delete_entry(int(parts[1])))
        except Exception as error:
            return _json_response({"detail": str(error)}, 404)

    return None


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def community_proxy(path: str, request: Request):
    remote_base = settings_store.current().community_base_url.rstrip("/")
    if not remote_base:
        return _json_response({"detail": "未配置远程社区服务"}, 400)
    url = remote_base + "/" + path
    if request.url.query:
        url += "?" + request.url.query

    headers = {}
    for key in ("authorization", "content-type"):
        if key in request.headers:
            headers[key] = request.headers[key]

    # 全局登录桥接：本地已登录的用户身份透传给远程社区，远程无需再登录。
    user = getattr(request.state, "user", None)
    if user:
        headers["X-Lab-User-Id"] = str(user.get("id") or "")
        headers["X-Lab-User-Name"] = str(user.get("username") or "")
        headers["X-Lab-User-Is-Admin"] = "1" if user.get("is_admin") else "0"

    body = await request.body()
    body_json = None
    if body:
        try:
            body_json = json.loads(body)
        except json.JSONDecodeError:
            body_json = None

    # 发布模板时在本地先按正式合同校验，防止无效模板进入远程/本地社区库。
    if request.method == "POST" and path.strip("/") == "community":
        from api.community import _validate_template
        try:
            _validate_template((body_json or {}).get("kind", ""), (body_json or {}).get("content") or {})
        except ValueError as error:
            return _json_response({"detail": str(error)}, 400)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            remote = await client.request(request.method, url, headers=headers, content=body)
    except Exception as error:
        logger.warning("community proxy remote error: %s", error)
        fallback = _fallback_local(request, path, request.method, body_json)
        if fallback is not None:
            return fallback
        return _json_response({"detail": "远程社区连接失败"}, 502)

    # 远程旧版/未部署新接口时回退本地，避免社区功能直接不可用。
    if remote.status_code in (401, 404, 405, 501):
        fallback = _fallback_local(request, path, request.method, body_json)
        if fallback is not None:
            return fallback

    media_type = remote.headers.get("content-type", "application/json")
    return Response(remote.content, status_code=remote.status_code, media_type=media_type)
