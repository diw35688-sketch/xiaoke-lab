# -*- coding: utf-8 -*-
"""实验点菜 / 批量规划 / AI 智能排程 / 实验产物链。

核心功能：
1. 点菜：从方案库选多个实验，合并准备清单，与储存库同步。
2. AI 排程：LLM 根据生物学依赖关系、储存库现状排出可执行计划。
3. 产物追踪：每次实验记录产出了什么、消耗了什么，自动入库带溯源。
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import domain
from checklist_service import generate_protocol_checklist
from database import crud
from database import experiment_chain_store as chain

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/planning", tags=["实验规划"])


# ── 请求模型 ──


class OrderPayload(BaseModel):
    protocol_ids: list[str] = Field(min_length=1, max_length=30)
    start_at: str | None = Field(default=None, max_length=40)


class CombinedChecklistPayload(BaseModel):
    protocol_ids: list[str] = Field(min_length=1, max_length=30)


class AISchedulePayload(BaseModel):
    protocol_ids: list[str] = Field(min_length=1, max_length=30)
    start_at: str | None = Field(default=None, max_length=40)
    context: str = Field(default="", max_length=2000)


class ProductPayload(BaseModel):
    session_id: str = ""
    experiment_id: int | None = None
    product_name: str = Field(min_length=1, max_length=200)
    product_type: str = "sample"
    quantity: str = ""
    unit: str = ""
    notes: str = ""
    to_storage: bool = True
    location_id: int | None = None
    storage_condition: str = ""


class ConsumePayload(BaseModel):
    session_id: str = ""
    experiment_id: int | None = None
    storage_item_id: int
    quantity_used: str = ""


# ── 工具函数 ──


def _merge_lists(lists):
    seen = set()
    result = []
    for items in lists:
        for item in items or []:
            if isinstance(item, dict):
                key = str(item.get("name") or item.get("id") or item)
            else:
                key = str(item)
            if key and key not in seen:
                seen.add(key)
                result.append(item)
    return result


def _protocol_detail_for_ai(protocol_id: str) -> dict:
    """获取方案标题和步骤摘要，供 AI 排程参考。"""
    try:
        protocol = domain.protocols().get_by_id(protocol_id)
    except Exception:
        protocol = None
    if protocol is None:
        return {"id": protocol_id, "title": protocol_id, "steps_summary": ""}
    title = getattr(protocol, "title", protocol_id)
    steps = getattr(protocol, "steps", ()) or ()
    step_lines = []
    for s in steps:
        num = getattr(s, "step_number", "?")
        stitle = getattr(s, "title", "")
        instruction = getattr(s, "instruction", "")
        terms = getattr(s, "terms", ()) or ()
        line = f"第{num}步 {stitle}: {instruction}"
        if terms:
            line += f" (涉及: {', '.join(terms)})"
        step_lines.append(line)
    return {
        "id": protocol_id,
        "title": title,
        "steps_summary": "\n".join(step_lines)[:600],
        "total_steps": len(steps),
    }


def _storage_snapshot() -> list[dict]:
    """获取储存库现有物品快照。"""
    items = crud.list_storage_items(status="in_storage", limit=200)
    return [
        {
            "name": it.get("name", ""),
            "type": it.get("item_type", ""),
            "quantity": it.get("quantity", ""),
            "unit": it.get("unit", ""),
            "location": it.get("location_name", ""),
            "source": it.get("source_experiment_id", ""),
        }
        for it in items
        if it.get("name")
    ]


# ── 合并清单 ──


@router.post("/combined-checklist")
def combined_checklist(payload: CombinedChecklistPayload):
    """点菜后合并多份方案的准备清单，并继续与储存库同步。"""
    combined = {
        "reagents": [],
        "equipment": [],
        "consumables": [],
        "safety": [],
        "prep_requirements": [],
        "protocols": [],
        "missing_reagents": [],
    }
    for protocol_id in payload.protocol_ids:
        try:
            checklist = generate_protocol_checklist(protocol_id)
        except Exception:
            continue
        combined["protocols"].append({
            "protocol_id": protocol_id,
            "title": checklist.get("protocol_title", protocol_id),
            "total_steps": checklist.get("total_steps", 0),
        })
        combined["reagents"].extend(checklist.get("reagents") or [])
        combined["equipment"].extend(checklist.get("equipment") or [])
        combined["consumables"].extend(checklist.get("consumables") or [])
        combined["safety"].extend(checklist.get("safety") or [])
        combined["prep_requirements"].extend(checklist.get("prep_requirements") or [])
    # 试剂去重：同名合并库存命中状态
    reagent_seen = {}
    for reagent in combined["reagents"]:
        name = reagent.get("name") or ""
        if not name:
            continue
        key = name
        if key in reagent_seen:
            existing = reagent_seen[key]
            if reagent.get("found_in_storage") and not existing.get("found_in_storage"):
                existing["found_in_storage"] = True
                existing["storage"] = reagent.get("storage") or []
            continue
        reagent_seen[key] = dict(reagent)
    combined["reagents"] = list(reagent_seen.values())
    combined["equipment"] = _merge_lists([combined["equipment"]])
    combined["consumables"] = _merge_lists([combined["consumables"]])
    combined["missing_reagents"] = [
        item for item in combined["reagents"] if not item.get("found_in_storage")
    ]
    combined["summary"] = {
        "protocol_count": len(combined["protocols"]),
        "reagent_count": len(combined["reagents"]),
        "missing_count": len(combined["missing_reagents"]),
        "equipment_count": len(combined["equipment"]),
        "consumables_count": len(combined["consumables"]),
    }
    return combined


# ── AI 智能排程 ──


@router.post("/ai-schedule")
def ai_schedule(payload: AISchedulePayload):
    """让 AI 根据生物学依赖、储存库现状排出可执行的多实验计划。

    返回排好序的实验列表，包含依赖关系、预计耗时、产物链。
    如果 LLM 不可用则降级为简单顺序排列。
    """
    protocols_info = [_protocol_detail_for_ai(pid) for pid in payload.protocol_ids]
    protocols_info = [p for p in protocols_info if p["title"] != p["id"]]  # 过滤找不到的
    if not protocols_info:
        raise HTTPException(status_code=404, detail="未找到任何有效方案")

    storage = _storage_snapshot()

    # 尝试 LLM 排程
    schedule = _llm_schedule(protocols_info, storage, payload.context)
    if schedule is None:
        # 降级：简单顺序排列
        schedule = _fallback_schedule(protocols_info)

    # 补充每个实验的清单信息
    for item in schedule:
        pid = item.get("protocol_id", "")
        try:
            checklist = generate_protocol_checklist(pid)
            item["checklist_summary"] = {
                "reagents": len(checklist.get("reagents") or []),
                "equipment": checklist.get("equipment") or [],
                "missing": [
                    r.get("name", "") for r in (checklist.get("reagents") or [])
                    if not r.get("found_in_storage")
                ],
            }
        except Exception:
            item["checklist_summary"] = {"reagents": 0, "equipment": [], "missing": []}

    return {
        "schedule": schedule,
        "storage_snapshot": storage,
        "protocol_count": len(protocols_info),
    }


def _llm_schedule(protocols: list[dict], storage: list[dict], context: str) -> list[dict] | None:
    """调用 LLM 排程。失败返回 None。"""
    try:
        from llm_bridge import WebSettingsLLMClient
    except Exception:
        return None

    # 明确给出 protocol_id 映射，防止 LLM 自造 ID
    id_map_lines = []
    for i, p in enumerate(protocols):
        id_map_lines.append(f"[{i + 1}] protocol_id=\"{p['id']}\" 标题=\"{p['title']}\"")
    id_map_text = "\n".join(id_map_lines)

    protocols_text = "\n\n".join(
        f"实验 [{i + 1}] \"{p['title']}\" (protocol_id={p['id']})\n步骤:\n{p['steps_summary']}"
        for i, p in enumerate(protocols)
    )
    storage_text = ""
    if storage:
        storage_text = "\n储存库现有物品:\n" + "\n".join(
            f"- {s['name']} ({s['type']}) {s['quantity']}{s['unit']}"
            for s in storage[:50]
        )

    system_prompt = (
        "你是生物实验排程助手。用户选了多个实验要做，你需要排出一个合理的执行顺序。\n\n"
        "生物学实验的依赖关系示例：\n"
        "- 今天培养的感受态细胞，可以作为明天转化实验的材料\n"
        "- 今天洗涤的种子，可以作为几个月后侵染实验的材料\n"
        "- 某个实验的产物（如质粒DNA、抗体、培养物）可以作为后续实验的输入\n"
        "- 有些实验需要等待（如培养过夜、冰冻几小时），有些可以马上做\n\n"
        "排程原则：\n"
        "1. 有依赖关系的实验按先后排序（先产出再使用）\n"
        "2. 能并行的标注 parallel=true\n"
        "3. 预估每个实验的时长（分钟）和等待时间\n"
        "4. 标注每个实验的 produces（会产出什么）和 requires（需要什么材料）\n"
        "5. 检查储存库里已有的材料，标注 missing（还缺什么）\n\n"
        "⚠️ 关键：protocol_id 字段必须原样使用下面给出的 ID 值，不要改成「实验1」之类的序号！\n\n"
        "只输出 JSON 数组，每个元素格式：\n"
        '{"order": 1, "protocol_id": "原样ID", "title": "实验名", '
        '"depends_on": [排序号], "parallel": false, '
        '"estimated_minutes": 60, "wait_hours": 0, '
        '"produces": ["产物1"], "requires": ["材料1"], "missing": ["缺的1"], '
        '"rationale": "为什么排在这个位置"}'
    )

    user_prompt = (
        f"ID 对照表（protocol_id 必须原样使用这些值）：\n{id_map_text}\n\n"
        f"方案详情：\n{protocols_text}\n{storage_text}"
    )
    if context:
        user_prompt += f"\n\n用户备注：{context}"

    try:
        client = WebSettingsLLMClient(max_attempts=1, timeout_seconds=45.0)
        result = client.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        data = json.loads(result.content)
        if isinstance(data, dict) and "schedule" in data:
            data = data["schedule"]
        if not isinstance(data, list):
            return None

        # 后处理：修正 LLM 可能乱编的 protocol_id
        valid_ids = {p["id"] for p in protocols}
        id_by_title = {p["title"]: p["id"] for p in protocols}
        for item in data:
            pid = item.get("protocol_id", "")
            if pid not in valid_ids:
                # 尝试用 title 匹配
                title = item.get("title", "")
                if title in id_by_title:
                    item["protocol_id"] = id_by_title[title]
        return data
    except Exception as exc:
        logger.warning("AI 排程 LLM 调用失败，降级: %s", exc)
        return None


def _fallback_schedule(protocols: list[dict]) -> list[dict]:
    """降级排程：按用户选择顺序排列，无依赖分析。"""
    return [
        {
            "order": i + 1,
            "protocol_id": p["id"],
            "title": p["title"],
            "depends_on": [],
            "parallel": False,
            "estimated_minutes": 0,
            "wait_hours": 0,
            "produces": [],
            "requires": [],
            "missing": [],
            "rationale": "（AI 不可用，按选择顺序排列）",
        }
        for i, p in enumerate(protocols)
    ]


# ── 创建计划 ──


@router.post("/order")
def create_order(payload: OrderPayload):
    """点菜创建实验记录。"""
    created = []
    for protocol_id in payload.protocol_ids:
        protocol = domain.protocols().get_by_id(protocol_id)
        if protocol is None:
            raise HTTPException(status_code=404, detail=f"找不到方案 {protocol_id}")
        try:
            checklist = generate_protocol_checklist(protocol_id)
        except Exception:
            checklist = {"equipment": [], "summary": {}}
        equipment = "、".join(checklist.get("equipment") or [])[:200]
        item = crud.create_experiment(
            name=protocol.title,
            goal="",
            start_at=payload.start_at,
            end_at=None,
            equipment=equipment,
            notes=f"protocol_id={protocol_id}",
        )
        created.append(item)
    return {"created": created, "count": len(created)}


@router.post("/create-plan")
def create_plan(payload: AISchedulePayload):
    """根据 AI 排程结果创建带依赖关系的多实验计划。

    与 /order 不同，这个会建立 depends_on 关系，
    并把排程信息（预估耗时、产出/消耗）写入 notes。
    """
    from datetime import datetime
    # 没指定开始时间就默认今天——否则实验不会出现在今日规划里
    start_at = payload.start_at or datetime.now().strftime("%Y-%m-%d %H:%M")

    schedule_result = ai_schedule(payload)
    schedule = schedule_result["schedule"]

    created = []
    order_to_id: dict[int, int] = {}
    for item in sorted(schedule, key=lambda x: x.get("order", 0)):
        pid = item.get("protocol_id", "")
        protocol = domain.protocols().get_by_id(pid)
        if protocol is None:
            continue
        deps = item.get("depends_on", [])
        depends_ids = [str(order_to_id[d]) for d in deps if d in order_to_id]
        notes_parts = [f"protocol_id={pid}"]
        if item.get("rationale"):
            notes_parts.append(f"rationale={item['rationale']}")
        if item.get("produces"):
            notes_parts.append(f"produces={','.join(item['produces'])}")
        if item.get("requires"):
            notes_parts.append(f"requires={','.join(item['requires'])}")

        exp = crud.create_experiment(
            name=protocol.title,
            goal=item.get("rationale", ""),
            start_at=start_at,
            end_at=None,
            equipment="",
            notes="; ".join(notes_parts),
            step_order=item.get("order"),
            depends_on=",".join(depends_ids),
        )
        order_to_id[item.get("order", 0)] = exp["id"]
        exp["schedule_info"] = item
        created.append(exp)

    return {"created": created, "count": len(created), "schedule": schedule}


# ── 实验产物链 ──


@router.post("/products")
def record_product(payload: ProductPayload):
    """记录一个实验产物，并可选自动入库到储存库（带溯源）。"""
    storage_item_id = None
    if payload.to_storage and payload.product_name:
        # 自动入库
        item_data = {
            "item_type": _map_product_type(payload.product_type),
            "name": payload.product_name,
            "quantity": payload.quantity,
            "unit": payload.unit,
            "location_id": payload.location_id,
            "storage_condition": payload.storage_condition,
            "source_experiment_id": payload.session_id or str(payload.experiment_id or ""),
            "status": "in_storage",
            "notes": payload.notes or f"实验产物",
        }
        try:
            created_item = crud.create_storage_item(item_data)
            storage_item_id = created_item.get("id")
        except Exception as exc:
            logger.warning("产物入库失败: %s", exc)

    product = chain.add_product(
        session_id=payload.session_id,
        experiment_id=payload.experiment_id,
        product_name=payload.product_name,
        product_type=payload.product_type,
        quantity=payload.quantity,
        unit=payload.unit,
        storage_item_id=storage_item_id,
        notes=payload.notes,
    )
    return {"product": product, "storage_item_id": storage_item_id}


@router.get("/products")
def get_products(
    session_id: str = "",
    experiment_id: int | None = None,
):
    """查询某实验的所有产物。"""
    products = chain.list_products(session_id=session_id, experiment_id=experiment_id)
    return {"products": products, "count": len(products)}


@router.delete("/products/{product_id}")
def delete_product(product_id: int):
    if not chain.remove_product(product_id):
        raise HTTPException(status_code=404, detail="产物记录不存在")
    return {"ok": True}


@router.post("/consumes")
def record_consume(payload: ConsumePayload):
    """记录实验消耗了某个库存物品。"""
    consume = chain.add_consume(
        session_id=payload.session_id,
        experiment_id=payload.experiment_id,
        storage_item_id=payload.storage_item_id,
        quantity_used=payload.quantity_used,
    )
    return {"consume": consume}


@router.get("/consumes")
def get_consumes(
    session_id: str = "",
    experiment_id: int | None = None,
):
    """查询某实验消耗的所有库存物品。"""
    consumes = chain.list_consumes(session_id=session_id, experiment_id=experiment_id)
    return {"consumes": consumes, "count": len(consumes)}


@router.get("/chain/{session_id}")
def get_chain(session_id: str):
    """获取一个实验 session 的完整产物/消耗链。"""
    return chain.session_chain(session_id)


@router.get("/provenance/{storage_item_id}")
def get_provenance(storage_item_id: int):
    """溯源一个储存物的实验来源。"""
    result = chain.storage_provenance(storage_item_id)
    if result is None:
        raise HTTPException(status_code=404, detail="储存物品不存在")
    return result


def _map_product_type(product_type: str) -> str:
    """把产物类型映射到 storage_item 的 item_type。"""
    mapping = {
        "sample": "样品",
        "reagent": "试剂",
        "culture": "培养物",
        "tissue": "组织",
        "antibody": "抗体",
        "dna": "核酸",
        "protein": "蛋白",
        "cell": "细胞",
        "other": "其他",
    }
    return mapping.get(product_type, "其他")
