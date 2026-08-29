# -*- coding: utf-8 -*-
"""远程社区 API 代理：前端只访问本地 /community-proxy/*，远程地址不出现在浏览器。"""
import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import Response

import settings_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/community-proxy", tags=["社区代理"])


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def community_proxy(path: str, request: Request):
    remote_base = settings_store.current().community_base_url.rstrip("/")
    if not remote_base:
        return Response('{"detail":"未配置远程社区服务"}', status_code=400, media_type="application/json")
    url = remote_base + "/" + path
    if request.url.query:
        url += "?" + request.url.query

    headers = {}
    for key in ("authorization", "content-type"):
        if key in request.headers:
            headers[key] = request.headers[key]

    body = await request.body()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            remote = await client.request(request.method, url, headers=headers, content=body)
    except httpx.TimeoutException:
        return Response('{"detail":"远程社区请求超时"}', status_code=504, media_type="application/json")
    except Exception as error:  # noqa: BLE001
        logger.warning("community proxy error: %s", error)
        return Response('{"detail":"远程社区连接失败"}', status_code=502, media_type="application/json")

    media_type = remote.headers.get("content-type", "application/json")
    return Response(remote.content, status_code=remote.status_code, media_type=media_type)
