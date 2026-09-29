# -*- coding: utf-8 -*-
from __future__ import annotations

"""储存库工具（由 lab_tools.py 拆分生成）。"""

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

# ---------- 储存库工具 ----------
from database import crud as _storage_crud  # noqa: E402


@tool(
    "list_storage_items",
    "查看/搜索储存库物品。用户问“我存了什么/种子在哪/冰箱里有什么/查储存库”时调用。只读；不要用于修改/删除物品。",
    {
        "type": "object",
        "properties": {
            "q": {"type": "string", "description": "按名称/位置/备注搜索，可留空"},
            "item_type": {"type": "string", "description": "物品类型：溶液/种子/DNA/菌液/试剂/耗材/产物"},
        },
        "required": [],
        "additionalProperties": False,
    },
    kind="search", title="查询储存库",
    present=lambda a, r: [
        f"共 {len(r)} 项",
        *[f"{x.get('name')} · {x.get('location_name') or '未分配'}" for x in r[:5]],
    ],
)
def _list_storage_items(q="", item_type=""):
    return _storage_crud.list_storage_items(q=q, item_type=item_type)


@tool(
    "add_storage_item",
    "向储存库新增一个存储物品（溶液/种子/DNA/试剂等）。用户说“储存一个种子/入库/放到储存库”时调用。仅创建；不要用于修改/删除已有物品。",
    {
        "type": "object",
        "properties": {
            "item_type": {"type": "string", "description": "物品类型，默认溶液"},
            "name": {"type": "string", "description": "物品名称，如 ACS 种子、质粒 pUC19"},
            "quantity": {"type": "string", "description": "数量，如 一罐/1 罐/300"},
            "unit": {"type": "string", "description": "单位，如 罐/mL/管"},
            "concentration": {"type": "string", "description": "浓度，如 100 ng/μL"},
            "location_id": {"type": "integer", "description": "存储位置 id，可先 list_storage_locations 查询"},
            "position": {"type": "string", "description": "格子/标签，如 2层 A-03"},
            "storage_condition": {"type": "string", "description": "存放条件，如 4℃ / -20℃ / 室温"},
            "expires_at": {"type": "string", "description": "到期日期，YYYY-MM-DD"},
            "notes": {"type": "string", "description": "备注，如来源实验"},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
    kind="execute", title="入库：{name}",
    present=lambda a, r: [
        f"已入库 {r.get('name')}",
        f"存放：{r.get('storage_condition') or '未指定'}",
    ],
)
def _add_storage_item(item_type="其他", name="", quantity="", unit="", concentration="",
                      location_id=None, position="", storage_condition="", expires_at="", notes=""):
    return _storage_crud.create_storage_item({
        "item_type": item_type, "name": name, "quantity": quantity, "unit": unit,
        "concentration": concentration, "location_id": location_id, "position": position,
        "storage_condition": storage_condition, "expires_at": expires_at, "notes": notes,
    })


@tool(
    "update_storage_item",
    "修改储存库中某个物品的信息（数量、位置、状态、备注等）。用户说“改一下/移到/取用/丢弃”时调用。仅修改；不要用于新增/删除物品。",
    {
        "type": "object",
        "properties": {
            "item_id": {"type": "integer", "description": "物品 id，先 list_storage_items 查询"},
            "name": {"type": "string"},
            "quantity": {"type": "string"},
            "unit": {"type": "string"},
            "concentration": {"type": "string"},
            "location_id": {"type": "integer"},
            "position": {"type": "string"},
            "storage_condition": {"type": "string"},
            "status": {"type": "string", "enum": ["in_storage", "taken", "discarded", "expired"]},
            "notes": {"type": "string"},
        },
        "required": ["item_id"],
        "additionalProperties": False,
    },
    kind="execute", title="修改储存物品：{item_id}",
    present=lambda a, r: [f"已更新：{r.get('name')}", f"状态：{r.get('status')}"],
)
def _update_storage_item(item_id, **kwargs):
    return _storage_crud.update_storage_item(item_id, kwargs)


@tool(
    "delete_storage_item",
    "从储存库删除一个物品。用户说“删掉/丢弃这个”时调用。仅当用户明确要求删除时调用；不要用于查询/修改。",
    {
        "type": "object",
        "properties": {"item_id": {"type": "integer", "description": "物品 id"}},
        "required": ["item_id"],
        "additionalProperties": False,
    },
    kind="execute", title="删除储存物品：{item_id}",
    present=lambda a, r: ["已删除"],
)
def _delete_storage_item(item_id):
    return _storage_crud.delete_storage_item(item_id)


@tool(
    "list_storage_locations",
    "查看储存库所有存储位置（冰箱、冰柜、试剂柜、样品柜等）。只读；不要用于修改/新增位置。",
    {"type": "object", "properties": {}, "additionalProperties": False},
    kind="search", title="查看存储位置",
    present=lambda a, r: [
        f"共 {len(r)} 个位置",
        *[f"{x.get('name')} · {x.get('type')} · {x.get('temperature')}" for x in r[:8]],
    ],
)
def _list_storage_locations():
    return _storage_crud.list_storage_locations()


@tool(
    "add_storage_location",
    "新增一个存储位置（如冰箱2层、4℃试剂柜）。仅当用户明确要求新增位置时调用；不要用于修改/删除位置。",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "type": {"type": "string", "description": "冰箱/冰柜/试剂柜/样品柜/其他"},
            "temperature": {"type": "string"},
            "capacity": {"type": "string"},
            "notes": {"type": "string"},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
    kind="execute", title="新增存储位置：{name}",
    present=lambda a, r: [f"已新增位置：{r.get('name')}"],
)
def _add_storage_location(name, type="其他", temperature="", capacity="", notes=""):
    return _storage_crud.create_storage_location({
        "name": name, "type": type, "temperature": temperature,
        "capacity": capacity, "notes": notes,
    })


@tool(
    "storage_stats",
    "查看储存库统计（总数、7天内到期、已过期）。只读；不要用于修改/删除物品。",
    {"type": "object", "properties": {}, "additionalProperties": False},
    kind="read", title="储存库统计",
    present=lambda a, r: [
        f"总数 {r.get('total')}",
        f"7天内到期 {r.get('expiring')}",
        f"已过期 {r.get('expired')}",
    ],
)
def _storage_stats():
    return _storage_crud.storage_stats()

