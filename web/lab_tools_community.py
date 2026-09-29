# -*- coding: utf-8 -*-
from __future__ import annotations

"""社区工具（由 lab_tools.py 拆分生成）。"""

import json
import re
import uuid
import threading
from datetime import datetime, timedelta
from pathlib import Path

from lab_tools_registry import (
    _REGISTRY, tool, PresentedToolResult, _attach_artifact,
    present_call, present_result,
    REPO_ROOT, RESULTS_DIR, STEP_IMPROVEMENTS_FILE,
    _timers, _timers_lock, _record_lock,
    domain, llm_bridge, settings_store,
    RecordCommand, SharedRecordService,
    generate_schedule, format_schedule_brief,
    get_remaining_schedule, format_remaining_brief,
    get_step_profile, get_next_passive_window,
    plan_multi_protocols, format_multi_protocol_brief,
    plan_clock_schedule,
    PresentationDeliveryPlan, build_delivery_plan,
    extract_entities,
    current_session_id, list_records, next_segment_id, save_record,
    save_protocol_preference, get_protocol_preference,
)

# ---------- 社区工具 ----------

def _community_summary(item):
    """把社区条目转成模型可读的简洁摘要。"""
    try:
        content = json.loads(item.get("content_json") or "{}")
    except Exception:
        content = {}
    if item.get("kind") == "protocol":
        steps = content.get("steps") or []
        first_step = steps[0] if steps else {}
        return {
            "community_entry_id": item.get("id"),
            "kind": "protocol",
            "title": item.get("title"),
            "protocol_id": content.get("protocol_id"),
            "source": content.get("source"),
            "total_steps": len(steps),
            "tags": item.get("tags") or "",
            "author": item.get("author") or "",
            "downloads": item.get("downloads") or 0,
            "first_step": first_step.get("title") or "",
            "first_instruction": (first_step.get("instruction") or "")[:300],
        }
    if item.get("kind") == "reagent_prep":
        name = content.get("name_zh") or item.get("title")
        return {
            "community_entry_id": item.get("id"),
            "kind": "reagent_prep",
            "title": item.get("title"),
            "name_zh": name,
            "purpose": (content.get("purpose") or "")[:300],
            "tags": item.get("tags") or "",
            "author": item.get("author") or "",
            "downloads": item.get("downloads") or 0,
        }
    return {
        "community_entry_id": item.get("id"),
        "kind": item.get("kind"),
        "title": item.get("title"),
        "tags": item.get("tags") or "",
        "author": item.get("author") or "",
        "downloads": item.get("downloads") or 0,
    }


@tool(
    "search_community",
    "在社区模板库中搜索实验方案或试剂配方。用户希望找现成的实验方案、社区方案、模板、试剂配方时调用；"
    "可按关键词 search 标题/标签/作者。只读，不会导入。",
    {
        "type": "object",
        "properties": {
            "q": {"type": "string", "description": "搜索关键词，如 RNA、ELISA、PBS、细胞培养"},
            "kind": {"type": "string", "enum": ["protocol", "reagent_prep"], "description": "只搜方案或只搜试剂配方，默认全部"},
            "limit": {"type": "integer", "description": "最多返回条数，默认 20"},
        },
        "required": [],
        "additionalProperties": False,
    },
    kind="search", title="搜索社区模板：{q}",
    present=lambda a, r: [
        f"找到 {len(r)} 条",
        *[f"{x.get('title')} · {x.get('kind')} · {x.get('total_steps') or ''}步" for x in r[:5]],
    ],
)
def _search_community(q="", kind="", limit=20):
    items = _storage_crud.list_community_entries(
        q=q or "", kind=kind or "", limit=max(1, min(int(limit or 20), 50))
    )
    return [_community_summary(item) for item in items]


@tool(
    "import_community_entry",
    "把社区中的一条方案或试剂配方导入本地方案库/试剂配置库。用户看到搜索结果后明确说“用这个/导入这个/保存这个”时调用。"
    "必须先先用 search_community 搜索并拿到 community_entry_id，不要猜测编号。",
    {
        "type": "object",
        "properties": {
            "community_entry_id": {"type": "integer", "description": "社区条目 id，来自 search_community 返回的 community_entry_id"},
        },
        "required": ["community_entry_id"],
        "additionalProperties": False,
    },
    kind="execute", title="导入社区模板：{community_entry_id}",
    present=lambda a, r: [
        f"已导入：{r.get('title')}",
        f"类型：{r.get('kind')}",
    ],
)
def _import_community_entry(community_entry_id):
    row = _storage_crud.get_community_entry(int(community_entry_id))
    if not row:
        raise ValueError("找不到该社区条目，请先用 search_community 搜索。")
    content = json.loads(row.get("content_json") or "{}")
    kind = row.get("kind")
    if kind == "protocol":
        # 复制一份并给新 id，避免覆盖本地已有方案
        content["protocol_id"] = _community_new_id(content.get("protocol_id", ""), "protocol")
        saved = domain.add_protocol(content)
    elif kind == "reagent_prep":
        content["reagent_prep_id"] = _community_new_id(content.get("reagent_prep_id", ""), "reagent_prep")
        saved = domain.add_reagent_prep(content)
    else:
        raise ValueError("未知社区类型：" + str(kind))
    _storage_crud.increment_community_downloads(row["id"])
    return {
        "ok": True,
        "kind": kind,
        "title": row.get("title"),
        "saved": saved,
        "community_entry_id": row["id"],
    }


@tool(
    "web_search",
    "在公开互联网上搜索实验方案/试剂配方信息。仅当本地方案库、本地试剂配置库、社区模板库、知识库都找不到，"
    "用户又确实需要某个配方/方法时调用。优先用 search_knowledge_base 查本地知识库（引物表等），"
    "只有本地查不到才用本工具联网搜。只读，不会自动保存。返回搜索结果（标题/网址/摘要）。"
    "\n\n搜索技巧：缩写词（如 SOB、LB、TB）要加上完整英文名或中文用途说明，"
    "例如 'SOB medium Super Optimal Broth recipe' 或 'LB 培养基配方 tryptone'，"
    "避免被搜索引擎当成普通英文单词。",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词。缩写要加全称，如 'SOB medium Super Optimal Broth composition per liter'、'LB 培养基配方 tryptone yeast extract'"},
            "limit": {"type": "integer", "description": "最多返回几条，默认5"}
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    kind="search", title="联网搜索：{query}",
    present=lambda a, r: [f"联网找到 {len(r)} 条结果："] + [
        f"{i}. {x.get('title','')}（{x.get('url','')}）" for i, x in enumerate(r[:5], start=1)
    ],
)
def _web_search(query, limit=5):
    from web_search_service import web_search
    try:
        return web_search(query, limit=max(1, min(int(limit or 5), 10)))
    except RuntimeError as error:
        raise ValueError(str(error))


@tool(
    "web_search_and_save_recipe",
    "当本地和社区都没有某个试剂/缓冲液配方，用户又需要时，联网搜索网页并保存为一条「网络检索（临时）」配方。"
    "会真实抓取网页、把内容整理成配方落库，并保留来源网址。用户说'网上查一下这个配方''联网找找XX怎么配''本地没有，上网搜一个保存'时调用。"
    "成功后可直接用于配制流程。"
    "\n\n搜索技巧：缩写词（如 SOB、LB、TB）要加上完整英文名或用途说明，"
    "否则搜索引擎可能返回无关结果（如 SOB 被当成英文单词'啜泣'）。",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "要查的配方关键词。缩写要加全称，如 'SOB medium Super Optimal Broth recipe'、'10x TBE buffer composition'"},
            "url": {"type": "string", "description": "可选：如果用户已给出具体网址，直接抓这个网址；不填就自动搜索"},
            "description": {"type": "string", "description": "可选：用户补充的要求，如 '要500mL、不含EDTA'，会帮助挑选网页"},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    kind="execute", title="联网查配方：{query}",
    present=lambda a, r: [
        f"已保存：{r.get('name_zh') or '未知'}",
        f"来源：{r.get('source') or '未知'}",
        f"网页：{r.get('source_url') or '无'}",
        f"共 {len(r.get('steps') or [])} 个配制步骤",
    ],
)
def _web_search_and_save_recipe(query, url="", description=""):
    from web_search_service import save_web_reagent_prep
    try:
        return save_web_reagent_prep(
            query=query,
            url=url or "",
            description=description or "",
        )
    except RuntimeError as error:
        raise ValueError(str(error))
    except Exception as error:
        raise ValueError(f"联网保存配方失败：{error}")


def _community_new_id(base_id: str, kind: str) -> str:
    """生成不会与本地现有方案/配方冲突的新 id。"""
    import re as _re
    try:
        existing = (
            {p.protocol_id for p in domain.protocols().list_all()}
            if kind == "protocol"
            else {p.reagent_prep_id for p in domain.reagent_preps().list_all()}
        )
    except Exception:
        existing = set()
    slug = _re.sub(r"[^A-Za-z0-9_.-]+", "-", str(base_id or "")).strip("-") or ("community-protocol" if kind == "protocol" else "community-prep")
    if slug not in existing:
        return slug
    index = 2
    while f"{slug}-community-{index}" in existing:
        index += 1
    return f"{slug}-community-{index}"

