# -*- coding: utf-8 -*-
"""实验准备台服务：把试剂配置库、实验前准备清单、储存库粘成一张自适应准备单。

分工：
  - "要什么"（试剂/仪器/耗材）→ checklist_service 的规则层（已有，不重写）
  - "按什么计量、做多少、哪个先配" → AI 推理（llm_bridge.generate_prep_bench_draft）
  - 落库（prep_runs / prep_run_items）→ 本服务

准备单挂在本"次实验"上（conversation_id + protocol_id），不是方案上，
这样重开一次实验 = 一张新的准备单，不会和上次的准备状态混在一起。
"""

from __future__ import annotations

import uuid

from contextlib import closing
from database.db import get_connection


# ---------------------------------------------------------------------------
# 时效排序权重（数字越小越要先做）
# ---------------------------------------------------------------------------

_TIME_ORDER = {
    "overnight": 0,   # 需过夜，最先做
    "prechill": 1,    # 需预冷
    "fresh": 2,       # 现配现用
    "normal": 3,      # 普通顺序
}


def _time_sort_key(item: dict) -> tuple:
    """时效优先；同级别内 estimated_minutes 大的靠前（耗时长的先启动）。"""
    ts = item.get("time_sensitivity", "normal")
    mins = item.get("estimated_minutes") or 0
    return (_TIME_ORDER.get(ts, 3), -(mins if isinstance(mins, (int, float)) else 0))


# ---------------------------------------------------------------------------
# 会话键：与试剂配制流程保持一致——单用户助手只有一个活动会话。
# ---------------------------------------------------------------------------

def _conversation_key(conversation_id: str | None) -> str:
    return conversation_id or "lab-session"


# ---------------------------------------------------------------------------
# 三态自动分类（规则层，确定性，不依赖 AI）
# ---------------------------------------------------------------------------

def _auto_state(reagent_item: dict, required_qty: str = "") -> str:
    """从 checklist 的 reagent item 推断状态：ready / prep_now / missing / insufficient。

    当储存库有货但数量可能不够时，返回 insufficient 让用户确认。
    """
    if reagent_item.get("found_in_storage"):
        # 有库存——尝试对比用量
        if _storage_quantity_insufficient(reagent_item, required_qty):
            return "insufficient"
        return "ready"
    if reagent_item.get("available_prep"):
        return "prep_now"
    return "missing"


def _storage_quantity_insufficient(reagent_item: dict, required_qty: str) -> bool:
    """粗略判断库存是否不够：当库存数量为空或明显小于需求时返回 True。

    这是一个保守的启发式——只有库存没有写数量、或数字明显不够时才标 insufficient，
    避免误报。精确的单位换算交给用户确认。
    """
    storage = reagent_item.get("storage") or []
    if not storage:
        return False
    # 库存没写数量 → 无法确认够不够 → 提示用户确认
    first = storage[0]
    stock_qty = str(first.get("quantity", "")).strip()
    if not stock_qty:
        return True
    # 试着提取数字对比
    stock_num = _extract_number(stock_qty)
    req_num = _extract_number(required_qty)
    if stock_num is not None and req_num is not None and req_num > stock_num * 1.05:
        return True
    return False


def _extract_number(s: str) -> float | None:
    """从字符串里提取第一个数字。"""
    import re
    m = re.search(r"[\d.]+", str(s))
    if not m:
        return None
    try:
        return float(m.group())
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# 主入口：生成准备台
# ---------------------------------------------------------------------------

def generate_prep_bench(
    *,
    protocol_id: str,
    scale_input: str | None = None,
    conversation_id: str | None = None,
) -> dict:
    """从方案生成准备台草稿，落库后返回准备台视图。

    流程：
      1. checklist_service 抽取试剂/仪器/耗材 + 查储存库 + 匹配方
      2. 把试剂列表喂给 AI，让它推断计量方式 + 规模 + 用量 + 耗时 + 时效
      3. 合并两层结果，落库成 prep_run + prep_run_items
    """

    from checklist_service import generate_protocol_checklist
    import domain
    from checklist_service import _build_step_text

    detail = domain.protocol_detail(protocol_id)
    protocol_title = detail["protocol"]["title"]
    step_text = _build_step_text(detail)
    checklist = generate_protocol_checklist(protocol_id)

    # ---- 构建喂给 AI 的试剂列表（只含试剂和需配制项，仪器/耗材不需要缩放）----
    reagent_items_for_ai: list[dict] = []
    checklist_reagents: list[dict] = checklist.get("reagents", [])
    for index, reagent in enumerate(checklist_reagents):
        prep = reagent.get("available_prep") or {}
        reagent_items_for_ai.append({
            "id": index,
            "name": reagent.get("name", ""),
            "auto_state": "unknown",
            "prep_name": prep.get("name_zh", "") if prep else "",
        })
    prep_requirements = checklist.get("prep_requirements") or []
    for index, prep_req in enumerate(prep_requirements):
        name = prep_req.get("name_zh") or prep_req.get("name") or ""
        reagent_items_for_ai.append({
            "id": len(checklist_reagents) + index,
            "name": name,
            "auto_state": "prep_now",
            "prep_name": name,
        })

    # ---- AI 推理：计量方式 + 规模 + 逐项用量/耗时/时效 ----
    ai_draft = _safe_ai_draft(
        protocol_title=protocol_title,
        step_text=step_text,
        reagent_items=reagent_items_for_ai,
        scale_input=scale_input,
    )
    scale_unit = ai_draft.get("scale_unit", "")
    scale_basis = ai_draft.get("scale_basis", "")
    default_scale = ai_draft.get("default_scale", "")
    ai_items_by_id = {
        int(item.get("id", -1)): item
        for item in (ai_draft.get("items") or [])
        if isinstance(item, dict)
    }

    # ---- 合并：规则层三态 + AI 逐项注解 ----
    items = _build_items(
        checklist, checklist_reagents, prep_requirements, ai_items_by_id
    )

    # ---- 落库 ----
    prep_run_id = _save_prep_run(
        conversation_id=_conversation_key(conversation_id),
        protocol_id=protocol_id,
        protocol_title=protocol_title,
        scale_unit=scale_unit,
        scale_basis=scale_basis,
        default_scale=default_scale,
        items=items,
    )
    return get_prep_bench_view(prep_run_id)


def _safe_ai_draft(
    *,
    protocol_title: str,
    step_text: str,
    reagent_items: list[dict],
    scale_input: str | None,
) -> dict:
    """调 AI 推理，失败时降级为空注解（准备单仍可用，只是缺缩放/时效信息）。"""
    try:
        from llm_bridge import generate_prep_bench_draft
        return generate_prep_bench_draft(
            protocol_title=protocol_title,
            step_text=step_text,
            reagent_items=reagent_items,
            scale_input=scale_input,
        )
    except Exception:
        return {"scale_unit": "", "scale_basis": "", "default_scale": "", "items": []}


def _build_items(
    checklist: dict,
    checklist_reagents: list[dict],
    prep_requirements: list[dict],
    ai_items_by_id: dict[int, dict],
) -> list[dict]:
    """把规则层四态（ready/prep_now/missing/insufficient）和 AI 逐项注解合并，
    最后按时效排序。"""

    items: list[dict] = []

    # 试剂 / 缓冲液
    for index, reagent in enumerate(checklist_reagents):
        prep = reagent.get("available_prep") or {}
        storage = reagent.get("storage") or []
        ai_item = ai_items_by_id.get(index, {})
        required_qty = ai_item.get("quantity", "")
        state = _auto_state(reagent, required_qty)
        storage_hint = ""
        if storage:
            first = storage[0]
            storage_hint = (
                f"{first.get('quantity', '')} {first.get('unit', '')}".strip()
                + f" @ {first.get('location', '')}".rstrip()
            ).strip()
        items.append({
            "item_key": f"reagent:{reagent.get('name', '')}",
            "kind": "reagent",
            "name": reagent.get("name", ""),
            "auto_state": state,
            "reagent_prep_id": prep.get("reagent_prep_id", "") if prep else "",
            "storage_hint": storage_hint,
            "quantity": required_qty,
            "estimated_minutes": ai_item.get("estimated_minutes"),
            "time_sensitivity": ai_item.get("time_sensitivity", "normal"),
            "note": "",
        })

    # 仪器
    for name in checklist.get("equipment", []):
        items.append({
            "item_key": f"equipment:{name}",
            "kind": "equipment",
            "name": name,
            "auto_state": "ready",
            "quantity": "",
            "estimated_minutes": None,
            "time_sensitivity": "normal",
        })

    # 耗材
    for name in checklist.get("consumables", []):
        items.append({
            "item_key": f"consumable:{name}",
            "kind": "consumable",
            "name": name,
            "auto_state": "ready",
            "quantity": "",
            "estimated_minutes": None,
            "time_sensitivity": "normal",
        })

    # 方案里的"需提前配制"
    for index, prep_req in enumerate(prep_requirements):
        name = prep_req.get("name_zh") or prep_req.get("name") or ""
        ai_item = ai_items_by_id.get(len(checklist_reagents) + index, {})
        items.append({
            "item_key": f"prep:{name}",
            "kind": "prep",
            "name": name,
            "auto_state": "prep_now",
            "quantity": ai_item.get("quantity", ""),
            "estimated_minutes": ai_item.get("estimated_minutes"),
            "time_sensitivity": ai_item.get("time_sensitivity", "normal"),
        })

    # ---- 时效排序 ----
    items.sort(key=_time_sort_key)
    for i, item in enumerate(items):
        item["sort_order"] = i
    return items


# ---------------------------------------------------------------------------
# 落库
# ---------------------------------------------------------------------------

def _save_prep_run(
    *,
    conversation_id: str,
    protocol_id: str,
    protocol_title: str,
    scale_unit: str,
    scale_basis: str,
    default_scale: str,
    items: list[dict],
) -> str:
    """写入 prep_runs + prep_run_items，返回 prep_run_id。"""

    prep_run_id = str(uuid.uuid4())
    with closing(get_connection()) as conn, conn:
        conn.execute(
            """INSERT INTO prep_runs
               (prep_run_id, conversation_id, protocol_id, protocol_title,
                scale_unit, scale_basis, default_scale, user_scale, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, '', 'preparing')""",
            (
                prep_run_id, conversation_id, protocol_id, protocol_title,
                scale_unit, scale_basis, default_scale,
            ),
        )
        for item in items:
            minutes = item.get("estimated_minutes")
            minutes_int = int(minutes) if minutes and str(minutes).isdigit() else None
            conn.execute(
                """INSERT INTO prep_run_items
                   (prep_run_item_id, prep_run_id, item_key, kind, name,
                    auto_state, manual_state, reagent_prep_id, storage_hint,
                    quantity, estimated_minutes, time_sensitivity, note, sort_order)
                   VALUES (?, ?, ?, ?, ?, ?, '', ?, ?, ?, ?, ?, '', ?)""",
                (
                    str(uuid.uuid4()), prep_run_id,
                    item.get("item_key", ""), item.get("kind", "reagent"),
                    item.get("name", ""), item.get("auto_state", "missing"),
                    item.get("reagent_prep_id", ""), item.get("storage_hint", ""),
                    item.get("quantity", ""), minutes_int,
                    item.get("time_sensitivity", "normal"), item.get("sort_order", 0),
                ),
            )
    return prep_run_id


# ---------------------------------------------------------------------------
# 读取
# ---------------------------------------------------------------------------

def get_prep_bench(conversation_id: str | None) -> dict:
    """读取当前会话最新的准备台视图。不存在返回 None。"""

    cid = _conversation_key(conversation_id)
    with closing(get_connection()) as conn:
        row = conn.execute(
            "SELECT prep_run_id FROM prep_runs WHERE conversation_id=? "
            "ORDER BY updated_at DESC LIMIT 1",
            (cid,),
        ).fetchone()
    if row is None:
        return None
    return get_prep_bench_view(row["prep_run_id"])


def get_prep_bench_view(prep_run_id: str) -> dict:
    """组装一张准备台的完整视图。"""

    with closing(get_connection()) as conn:
        run_row = conn.execute(
            "SELECT * FROM prep_runs WHERE prep_run_id=?",
            (prep_run_id,),
        ).fetchone()
        if run_row is None:
            return None
        item_rows = conn.execute(
            "SELECT * FROM prep_run_items WHERE prep_run_id=? ORDER BY sort_order",
            (prep_run_id,),
        ).fetchall()

    items = [_row_to_item(row) for row in item_rows]
    ready_count = sum(1 for i in items if i["state"] == "ready")
    prep_now_count = sum(1 for i in items if i["state"] == "prep_now")
    missing_count = sum(1 for i in items if i["state"] == "missing")
    insufficient_count = sum(1 for i in items if i["state"] == "insufficient")

    return {
        "prep_run_id": prep_run_id,
        "protocol_id": run_row["protocol_id"],
        "protocol_title": run_row["protocol_title"],
        "scale_unit": run_row["scale_unit"],
        "scale_basis": run_row["scale_basis"],
        "default_scale": run_row["default_scale"],
        "user_scale": run_row["user_scale"],
        "status": run_row["status"],
        "items": items,
        "summary": {
            "total": len(items),
            "ready": ready_count,
            "prep_now": prep_now_count,
            "missing": missing_count,
            "insufficient": insufficient_count,
        },
    }


def _row_to_item(row) -> dict:
    auto_state = row["auto_state"]
    manual_state = row["manual_state"]
    # 用户覆盖优先，否则系统自动判定。
    # manual_state 用 have/missing（用户语言），归一到 ready/missing（系统三态）。
    if manual_state == "have":
        state = "ready"
    elif manual_state == "missing":
        state = "missing"
    else:
        state = auto_state
    return {
        "prep_run_item_id": row["prep_run_item_id"],
        "item_key": row["item_key"],
        "kind": row["kind"],
        "name": row["name"],
        "auto_state": auto_state,
        "manual_state": manual_state,
        "state": state,
        "reagent_prep_id": row["reagent_prep_id"],
        "storage_hint": row["storage_hint"],
        "quantity": row["quantity"],
        "estimated_minutes": row["estimated_minutes"],
        "time_sensitivity": row["time_sensitivity"],
        "note": row["note"],
    }


# ---------------------------------------------------------------------------
# 更新单项（用户覆盖）
# ---------------------------------------------------------------------------

def update_prep_item(prep_run_item_id: str, manual_state: str) -> dict:
    """用户覆盖某一项的状态：have（标记为有）/ missing（标记为缺）/ ''（清除覆盖）。"""

    if manual_state not in ("have", "missing", ""):
        raise ValueError("manual_state 只能是 have / missing / 空。")
    with closing(get_connection()) as conn, conn:
        row = conn.execute(
            "SELECT prep_run_id FROM prep_run_items WHERE prep_run_item_id=?",
            (prep_run_item_id,),
        ).fetchone()
        if row is None:
            raise ValueError("找不到这条准备项。")
        prep_run_id = row["prep_run_id"]
        conn.execute(
            "UPDATE prep_run_items SET manual_state=? WHERE prep_run_item_id=?",
            (manual_state, prep_run_item_id),
        )
        conn.execute(
            "UPDATE prep_runs SET updated_at=CURRENT_TIMESTAMP WHERE prep_run_id=?",
            (prep_run_id,),
        )
    return get_prep_bench_view(prep_run_id)


# ---------------------------------------------------------------------------
# 整体状态
# ---------------------------------------------------------------------------

def set_prep_run_status(prep_run_id: str, status: str) -> dict:
    """标记准备台状态：ready（就绪）/ skipped（跳过准备）/ preparing（准备中）。"""

    if status not in ("ready", "skipped", "preparing"):
        raise ValueError("status 只能是 ready / skipped / preparing。")
    with closing(get_connection()) as conn, conn:
        conn.execute(
            "UPDATE prep_runs SET status=?, updated_at=CURRENT_TIMESTAMP WHERE prep_run_id=?",
            (status, prep_run_id),
        )
    return get_prep_bench_view(prep_run_id)


# ---------------------------------------------------------------------------
# 缩放：用户改规模后重算用量
# ---------------------------------------------------------------------------

def rescale_prep_bench(prep_run_id: str, user_scale: str) -> dict:
    """用户改规模（如"做 20 个样本"），AI 按新规模重算每项用量，更新落库。

    流程：
      1. 读取现有准备台
      2. 把试剂列表喂给 AI，传入新规模 scale_input
      3. 用新用量更新 prep_run_items
      4. 更新 prep_runs.user_scale
    """
    bench = get_prep_bench_view(prep_run_id)
    if bench is None:
        raise ValueError("找不到准备台。")

    # 构建喂给 AI 的列表——只含试剂和需配制项
    reagent_items_for_ai = []
    for i, item in enumerate(bench["items"]):
        if item["kind"] in ("reagent", "prep"):
            reagent_items_for_ai.append({
                "id": i,
                "name": item["name"],
                "auto_state": "unknown",
                "prep_name": item["name"],
            })

    # 重算用量
    ai_draft = _safe_ai_draft(
        protocol_title=bench["protocol_title"],
        step_text="",  # 重算时已有计量方式，不需要重读方案步骤
        reagent_items=reagent_items_for_ai,
        scale_input=user_scale,
    )

    # 更新每项用量
    ai_items_by_id = {
        int(it.get("id", -1)): it
        for it in (ai_draft.get("items") or [])
        if isinstance(it, dict)
    }

    with closing(get_connection()) as conn, conn:
        for i, item in enumerate(bench["items"]):
            ai_item = ai_items_by_id.get(i)
            if ai_item and item["kind"] in ("reagent", "prep"):
                new_qty = ai_item.get("quantity", "")
                conn.execute(
                    "UPDATE prep_run_items SET quantity=? WHERE prep_run_item_id=?",
                    (new_qty, item["prep_run_item_id"]),
                )
        conn.execute(
            "UPDATE prep_runs SET user_scale=?, updated_at=CURRENT_TIMESTAMP WHERE prep_run_id=?",
            (user_scale, prep_run_id),
        )

    return get_prep_bench_view(prep_run_id)
