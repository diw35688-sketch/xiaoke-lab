# -*- coding: utf-8 -*-
"""实验前准备清单：从方案生成试剂/耗材/仪器/安全清单，并与储存库同步。

提取策略：优先用 LLM 从方案步骤中提取试剂/仪器/耗材（通用性强），
LLM 失败时降级到关键词提取。储存库匹配、配方匹配、安全提醒提取
始终走规则逻辑，不依赖 LLM。
"""

from __future__ import annotations

import json
import re

import domain
from database import crud

# ── 降级用关键词（仅在 LLM 不可用时生效） ──

_EQUIPMENT_KEYWORDS = [
    "分析天平", "天平", "移液枪", "移液器", "离心机", "水浴锅", "水浴", "烘箱",
    "摇床", "磁力搅拌器", "滴定管", "锥形瓶", "容量瓶", "烧杯", "量筒",
    "分光光度计", "酶标仪", "显微镜", "pH计", "pH 计", "电泳仪", "灭菌锅",
    "超净工作台", "培养箱", "冰箱", "制冰机", "振荡器", "涡旋仪", "游标卡尺",
    "温度计", "计时器", "玻璃棒", "研钵",
]

_CONSUMABLE_KEYWORDS = [
    "枪头", "吸头", "离心管", "移液管", "胶头滴管", "滴管", "滤纸", "称量纸",
    "一次性手套", "手套", "口罩", "护目镜", "封口膜", "保鲜膜",
    "试管", "培养皿", "载玻片", "盖玻片", "比色皿", "样品瓶", "冻存管",
    "EP管", "PE手套", "无粉手套", "酒精棉", "纱布",
    "PVDF膜", "NC膜", "硝酸纤维素膜", "吸附柱", "洗脱柱", "透析袋",
]


def _norm(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").lower())


# ── LLM 提取（结果持久化到数据库，重启不丢） ──


def _build_step_text(detail: dict) -> str:
    """把方案步骤拼成 LLM 可读的文本块。"""
    lines = []
    for step in detail.get("steps", []):
        parts = [f"第{step.get('number', '?')}步：{step.get('title', '')}"]
        instruction = step.get("instruction", "")
        if instruction:
            parts.append(f"  操作：{instruction}")
        terms = step.get("terms") or []
        if terms:
            parts.append(f"  术语：{', '.join(terms)}")
        hazard = step.get("hazard_note") or ""
        if hazard:
            parts.append(f"  安全：{hazard}")
        for sub in step.get("substeps") or []:
            text = sub.get("text", "") if isinstance(sub, dict) else str(sub)
            if text:
                parts.append(f"  - {text}")
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


def _llm_extract_items(detail: dict) -> dict | None:
    """用 LLM 从方案步骤中提取试剂、仪器、耗材。失败返回 None。"""
    step_text = _build_step_text(detail)
    if not step_text.strip():
        return None

    try:
        from llm_bridge import WebSettingsLLMClient
    except Exception:
        return None

    system_prompt = (
        "你是实验准备清单提取助手。用户会给你一份实验方案的所有步骤文本。"
        "请从中提取做这个实验需要准备的三类物品，只输出 JSON，不要 Markdown，不要解释。\n\n"
        "三类定义：\n"
        "- reagents（试剂/缓冲液/溶液）：化学药品、缓冲液、培养基、抗体、酶、染料等消耗性化学物质。"
        "只列具体名称，不列操作动作。\n"
        "- equipment（仪器）：实验室设备，如离心机、天平、移液枪、pH计、培养箱、电泳仪等。\n"
        "- consumables（耗材）：一次性用品，如 EP管、枪头、离心管、手套、滤纸、PVDF膜、培养皿等。\n\n"
        "注意事项：\n"
        "- 方案里写「离心」意味着需要「离心机」，写「称量」意味着需要「分析天平」，"
        "写「移液」意味着需要「移液枪」——从操作动词推断所需仪器。\n"
        "- 不要把同一种东西列两次（如「裂解缓冲液」和「裂解液」如果指的是同一种只列一个）。\n"
        "- 不要列纯数值、单位、pH 值等非物品词。\n\n"
        '输出格式：{"reagents":["试剂1","试剂2"],"equipment":["仪器1"],"consumables":["耗材1"]}'
    )

    try:
        client = WebSettingsLLMClient(max_attempts=1, timeout_seconds=30.0)
        result = client.generate_json(
            system_prompt=system_prompt,
            user_prompt=f"方案：{detail['protocol']['title']}\n\n{step_text}",
        )
        data = json.loads(result.content)
        reagents = [str(x).strip() for x in (data.get("reagents") or []) if str(x).strip()]
        equipment = [str(x).strip() for x in (data.get("equipment") or []) if str(x).strip()]
        consumables = [str(x).strip() for x in (data.get("consumables") or []) if str(x).strip()]
        if not reagents and not equipment and not consumables:
            return None
        return {"reagents": reagents, "equipment": equipment, "consumables": consumables}
    except Exception:
        return None


# ── 降级：关键词提取 ──

_NON_REAGENT_WORDS = [
    "称量", "校准", "酸碱度", "定量转移", "定容", "倒转混匀", "混匀", "标签",
    "保存条件", "溶解", "加热", "离心", "过滤", "振荡", "摇匀", "静置",
    "观察", "记录", "转移", "调节", "配置", "配制", "待测", "标准溶液",
    "空白对照", "样品", "对照", "重复", "稀释", "浓缩",
    "pvdf膜", "nc膜", "吸附柱", "洗脱柱",
]

_REAGENT_HINTS = (
    "缓冲液", "buffer", "pbs", "tbs", "tbst", "ripa", "sds", "bsa",
    "marker", "甲醇", "乙醇", "异丙醇", "tween", "抗体", "一抗", "二抗",
    "显色", "发光", "染色", "溶液", "培养基", "琼脂", "蛋白", "酶", "抑制剂",
    "dtt", "pmsf", "nacl", "kcl", "naoh", "hcl", "试剂", "甘油", "溴酚蓝",
    "脱脂", "奶粉", "染料", "裂解液", "上样", "封闭液", "电泳液", "转移液",
    "洗涤液", "固定液",
)
_REAGENT_SKIP = (
    "转膜", "洗膜", "蛋白检测", "显色法", "发光法", "电泳", "sds-page",
    "蛋白浓度", "封闭", "杂交", "检测", "跑胶", "上样", "煮沸", "超声",
    "离心", "漂洗", "洗涤", "转移", "配制", "染色法", "提取", "纯化",
)


def _is_reagentish(value: str) -> bool:
    low = _norm(value)
    if not low or len(low) < 2:
        return False
    if any(_norm(k) == low or _norm(k) in low for k in _NON_REAGENT_WORDS):
        return False
    if any(k in low for k in _REAGENT_SKIP):
        return False
    if any(k in low for k in _REAGENT_HINTS):
        return True
    return False


def _keyword_extract_items(detail: dict, steps: list) -> dict:
    """降级路径：用关键词从方案步骤中提取试剂/仪器/耗材。"""
    all_text = " ".join(
        str(x) for step in steps for x in [
            step.get("title", ""),
            step.get("instruction", ""),
            step.get("hazard_note", ""),
            *(step.get("terms") or []),
            *[s.get("text", "") for s in (step.get("substeps") or [])],
        ]
    )
    # 试剂
    reagents: dict[str, str] = {}
    analysis = domain.analyze_reagents([all_text])
    for item in analysis.get("hazmat", []):
        name = str(item.get("name") or "").strip()
        if name:
            reagents[_norm(name)] = name
    for item in analysis.get("reagent_preps", []):
        name = str(item.get("name_zh") or "").strip()
        if name:
            reagents[_norm(name)] = name
    for prep in detail.get("prep_requirements") or []:
        name = str(prep.get("name_zh") or prep.get("name") or "").strip()
        if name:
            reagents[_norm(name)] = name
    seen: dict[str, str] = {}
    for step in steps:
        for term in step.get("terms") or []:
            word = str(term or "").strip()
            key = _norm(word)
            if not key or len(key) < 2:
                continue
            if re.fullmatch(r"\d+(?:\.\d+)?(?:mol/l|m|g|mg|ml|ul|升|克|毫升)?", key):
                continue
            if any(_norm(k) == key or _norm(k) in key for k in _EQUIPMENT_KEYWORDS + _CONSUMABLE_KEYWORDS):
                continue
            if any(_norm(k) == key or key in _norm(k) for k in _NON_REAGENT_WORDS):
                continue
            if key not in seen:
                seen[key] = word
    for term in seen.values():
        if _is_reagentish(term):
            reagents.setdefault(_norm(term), term)
    # 仪器/耗材
    equipment = _collect_keywords(all_text, _EQUIPMENT_KEYWORDS)
    consumables = _collect_keywords(all_text, _CONSUMABLE_KEYWORDS)
    return {
        "reagents": list(reagents.values()),
        "equipment": equipment,
        "consumables": consumables,
    }


def _collect_keywords(text: str, keywords: list[str]) -> list[str]:
    norm_text = _norm(text)
    found = []
    seen: set[str] = set()
    for kw in keywords:
        key = _norm(kw)
        if key in norm_text and key not in seen:
            seen.add(key)
            found.append(kw)
    return found


# ── 储存库 & 配方匹配（规则逻辑，通用） ──

def _lookup_storage(name: str) -> list[dict]:
    normalized = _norm(name)
    try:
        rows = crud.list_storage_items(q=name, status="")
    except Exception:
        rows = []
    hits = []
    for row in rows:
        item_name = str(row.get("name") or "")
        key = _norm(item_name)
        if normalized and (
            normalized == key
            or normalized in key
            or key in normalized
        ):
            hits.append({
                "name": item_name,
                "quantity": row.get("quantity") or "",
                "unit": row.get("unit") or "",
                "location": row.get("position") or "",
                "status": row.get("status") or "",
            })
    return hits


def _match_reagent_prep(name: str) -> dict | None:
    """把试剂名跟本地配方库里的配方做模糊匹配。

    优先级：1. 精确匹配  2. 子串匹配选配方名最短的  3. ≤2 字符只允许精确匹配。
    """
    normalized = _norm(name)
    if not normalized or len(normalized) < 2:
        return None
    candidates: list[tuple[int, str, str]] = []
    for prep in domain.reagent_preps().list_all():
        prep_name = _norm(prep.name_zh or "")
        prep_id_norm = _norm(prep.reagent_prep_id or "")
        if not prep_name:
            continue
        if normalized == prep_name or normalized == prep_id_norm:
            return {"reagent_prep_id": prep.reagent_prep_id, "name_zh": prep.name_zh}
        if len(normalized) >= 3 and (
            normalized in prep_name or prep_name in normalized
            or normalized in prep_id_norm or prep_id_norm in normalized
        ):
            candidates.append((len(prep_name), prep.reagent_prep_id, prep.name_zh))
    if candidates:
        candidates.sort(key=lambda c: c[0])
        return {"reagent_prep_id": candidates[0][1], "name_zh": candidates[0][2]}
    return None


# ── 安全提醒提取（规则逻辑，通用） ──

def _extract_safety(steps: list) -> list[dict]:
    safety: list[dict] = []
    seen: set[tuple] = set()
    for step in steps:
        step_num = step.get("number")
        hazard_note = str(step.get("hazard_note") or "").strip()
        if hazard_note:
            key = (step_num, hazard_note)
            if key not in seen:
                seen.add(key)
                safety.append({"step": step_num, "note": hazard_note})
        for item in step.get("safety") or []:
            if isinstance(item, dict):
                note = str(item.get("note") or item.get("text") or item.get("name") or "").strip()
            else:
                note = str(item).strip()
            if not note:
                continue
            key = (step_num, note)
            if key not in seen:
                seen.add(key)
                safety.append({"step": step_num, "note": note})
    return safety


# ── 持久化缓存 ──

def _load_cached_extraction(protocol_id: str, step_signature: str) -> dict | None:
    """从数据库读取缓存的 LLM 提取结果。不存在返回 None。"""
    try:
        from database.db import get_connection
        with get_connection() as conn:
            row = conn.execute(
                "SELECT extracted_json FROM protocol_checklists WHERE protocol_id=? AND step_signature=?",
                (protocol_id, step_signature),
            ).fetchone()
        if row:
            return json.loads(row["extracted_json"])
    except Exception:
        pass
    return None


def _save_cached_extraction(protocol_id: str, step_signature: str, data: dict) -> None:
    """把 LLM 提取结果写入数据库，持久保存。"""
    try:
        from database.db import get_connection
        with get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO protocol_checklists (protocol_id, step_signature, extracted_json) "
                "VALUES (?, ?, ?)",
                (protocol_id, step_signature, json.dumps(data, ensure_ascii=False)),
            )
    except Exception:
        pass


# ── 主函数 ──

def generate_protocol_checklist(protocol_id: str) -> dict:
    """从方案生成准备清单。LLM 提取结果持久化到数据库，重启不丢；方案修改后自动重算。"""
    detail = domain.protocol_detail(protocol_id)
    steps = detail.get("steps", [])
    step_signature = f"{detail['protocol']['total_steps']}:{len(steps)}"

    # 1. 提取试剂/仪器/耗材——优先读数据库缓存，缓存未命中才调 LLM
    extracted = _load_cached_extraction(protocol_id, step_signature)
    if extracted is None:
        extracted = _llm_extract_items(detail)
        if extracted is None:
            extracted = _keyword_extract_items(detail, steps)
        _save_cached_extraction(protocol_id, step_signature, extracted)

    reagent_names: list[str] = extracted.get("reagents", [])
    equipment: list[str] = extracted.get("equipment", [])
    consumables: list[str] = extracted.get("consumables", [])

    # 2. 试剂逐个查储存库 + 匹配配方
    reagent_items = []
    for name in reagent_names:
        storage_hits = _lookup_storage(name)
        item = {
            "name": name,
            "found_in_storage": bool(storage_hits),
            "storage": storage_hits,
        }
        if not storage_hits:
            prep_match = _match_reagent_prep(name)
            if prep_match:
                item["available_prep"] = prep_match
        reagent_items.append(item)

    # 3. 安全提醒（始终走规则）
    safety = _extract_safety(steps)

    # 4. 方案里的"需提前配制"
    prep_requirements = detail.get("prep_requirements") or []

    missing = [item for item in reagent_items if not item["found_in_storage"]]
    missing_with_prep = [item for item in missing if item.get("available_prep")]
    return {
        "protocol_id": protocol_id,
        "protocol_title": detail["protocol"]["title"],
        "total_steps": detail["protocol"]["total_steps"],
        "reagents": reagent_items,
        "equipment": equipment,
        "consumables": consumables,
        "safety": safety,
        "prep_requirements": prep_requirements,
        "summary": {
            "reagent_count": len(reagent_items),
            "missing_count": len(missing),
            "can_prep_count": len(missing_with_prep),
            "equipment_count": len(equipment),
            "consumables_count": len(consumables),
        },
        "missing_reagents": missing,
    }
