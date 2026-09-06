# -*- coding: utf-8 -*-
"""把远程社区里的官方/已有模板同步到本地社区库，保证切换到全局登录后旧模板还在。"""

from __future__ import annotations

import json

import httpx
import settings_store
from database import crud


def sync_remote_to_local() -> dict:
    base = settings_store.current().community_base_url.rstrip("/")
    if not base:
        return {"ok": False, "added": 0, "error": "未配置远程社区服务"}
    try:
        response = httpx.get(
            base + "/community?q=&kind=&limit=500",
            timeout=20,
            trust_env=False,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as error:
        return {"ok": False, "added": 0, "error": f"远程社区同步失败：{error}"}

    existing = crud.list_community_entries()
    existing_keys = {(item["kind"], item["title"]) for item in existing}
    added = 0
    skipped = 0
    for item in data.get("items") or []:
        kind = str(item.get("kind") or "")
        title = str(item.get("title") or "").strip()
        if not title or not kind:
            continue
        key = (kind, title)
        if key in existing_keys:
            skipped += 1
            continue
        try:
            content_json = json.dumps(item.get("content") or {}, ensure_ascii=False)
            crud.create_community_entry(
                kind=kind,
                title=title,
                content_json=content_json,
                author=str(item.get("author") or ""),
                tags=str(item.get("tags") or ""),
            )
            added += 1
            existing_keys.add(key)
        except Exception:
            # 单条失败不影响其余模板同步
            continue
    return {"ok": True, "added": added, "skipped": skipped}
