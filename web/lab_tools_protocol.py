# -*- coding: utf-8 -*-
from __future__ import annotations

"""实验方案（由 lab_tools.py 拆分生成）。"""

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

# ---------------- 实验方案 ----------------

@tool(
    "create_protocol_from_text",
    "根据自然语言描述创建一份新的实验方案。传入你能收集到的最完整描述即可（实验名称+目的+关键参数），"
    "AI 会自动补齐标准实验步骤，不需要用户提供逐步文字。"
    "用户说'和现有方案一样只是某部分不同'时，把原方案步骤+修改点一起写入 description 直接调用。"
    "用户说'确定'/'新建'/'做'后立即调用，不要追问。仅当用户明确要求创建方案时调用。",
    {
        "type": "object",
        "properties": {"description": {"type": "string", "description": "实验方案的自然语言描述。包含实验名称、目的、关键参数（体系体积/温度/循环数等）。如果基于现有方案修改，把原步骤和修改点都写进去。"}},
        "required": ["description"],
        "additionalProperties": False,
    },
    kind="execute",
    title="AI 创建实验方案",
    present=lambda a, r: [f"已创建方案：{r['title']}", f"共 {len(r['steps'])} 步"],
)
def _create_protocol_from_text(description):
    draft = llm_bridge.generate_protocol_draft(description)
    saved = domain.add_protocol(draft)
    saved["ui_action"] = {"type": "navigate", "view": "protocols"}
    return saved


@tool(
    "list_protocols",
    "列出所有可选的实验方案，包含方案名称、步骤总数和来源。用户问有哪些实验、想做什么实验时调用。不要用于查询当前正在进行的实验/当前步骤。",
    {"type": "object", "properties": {}, "additionalProperties": False},
    kind="search", title="查看可选实验方案", experiment_command=True,
    present=lambda a, r: [f"共 {len(r)} 份方案，已在方案库展示全部"] + [f"{i}. {x['title']}（{x['total_steps']} 步）" for i, x in enumerate(r[:6], start=1)],
)
def _list_protocols():
    return [
        {
            "protocol_id": p.protocol_id,
            "title": p.title,
            "total_steps": len(p.steps),
            "source": p.source,
        }
        for p in domain.protocols().list_all()
    ]


@tool(
    "search_protocols",
    "按关键词搜索实验方案。用户说'我要做XXX'/'做个XXX'时调用本工具搜索，"
    "不要用 list_protocols 翻全部方案。会先查这个关键词的历史偏好（用户上次选了哪个），"
    "如果有偏好直接返回 auto_select=true；只有一个匹配也返回 auto_select=true。"
    "多个匹配时返回所有候选并标记 need_choice=true——此时把候选展示给用户选，不要自己选。",
    {
        "type": "object",
        "properties": {"keyword": {"type": "string", "description": "搜索关键词，从用户消息中提取，如'磷酸缓冲液'、' Bradford'、'质粒提取'"}},
        "required": ["keyword"],
        "additionalProperties": False,
    },
    kind="search", title="搜索方案「{keyword}」", experiment_command=True,
    present=lambda a, r: (
        [f"偏好命中：{r['matches'][0]['title']}（上次选过，已自动选定）"]
        if r.get("auto_select") and r["matches"]
        else [f"找到 {len(r['matches'])} 个匹配方案，请让用户选择："]
        + [f"  {chr(65+i)}：{m['title']}（{m['total_steps']}步，{m['first_step']}）"
           + (" ← 上次选过" if m.get("preferred") else "")
           for i, m in enumerate(r["matches"])]
        if r.get("need_choice")
        else [f"没有找到匹配「{a['keyword']}」的方案"]
    ),
)
def _search_protocols(keyword):
    # 1. 查历史偏好
    pref_id = get_protocol_preference(keyword)
    # 2. 模糊搜索方案库
    kw = keyword.strip().lower()
    all_protos = domain.protocols().list_all()
    matches = []
    for p in all_protos:
        title_lower = p.title.lower()
        pid_lower = p.protocol_id.lower()
        if kw in title_lower or kw in pid_lower or title_lower in kw:
            matches.append(p)
    # 也用标题里的关键词做 token 级匹配
    if not matches:
        kw_tokens = set(kw.replace("缓冲液", "").split())
        for p in all_protos:
            title_tokens = set(p.title.lower().split())
            if kw_tokens & title_tokens:
                matches.append(p)
    # 去重
    seen_ids = set()
    deduped = []
    for p in matches:
        if p.protocol_id not in seen_ids:
            seen_ids.add(p.protocol_id)
            deduped.append(p)
    matches = deduped
    # 3. 构建结果
    result_list = []
    for p in matches:
        step1 = p.steps[0] if p.steps else None
        result_list.append({
            "protocol_id": p.protocol_id,
            "title": p.title,
            "total_steps": len(p.steps),
            "source": p.source,
            "first_step": step1.title if step1 else "",
            "preferred": (pref_id == p.protocol_id) if pref_id else False,
        })
    # 4. 判断动作
    if not matches:
        return {"matches": [], "auto_select": False, "need_choice": False,
                "action": f"没有匹配「{keyword}」的方案"}
    # 偏好命中：方案还在
    if pref_id and any(m["protocol_id"] == pref_id for m in result_list):
        return {"matches": result_list, "auto_select": True, "need_choice": False,
                "preferred_protocol_id": pref_id,
                "action": f"偏好命中，直接调 select_protocol(protocol_id=\"{pref_id}\", search_keyword=\"{keyword}\")"}
    # 只有一个匹配
    if len(matches) == 1:
        return {"matches": result_list, "auto_select": True, "need_choice": False,
                "action": f"唯一匹配，直接调 select_protocol(protocol_id=\"{result_list[0]['protocol_id']}\", search_keyword=\"{keyword}\")"}
    # 多个匹配
    return {"matches": result_list, "auto_select": False, "need_choice": True,
            "action": f"有 {len(matches)} 个匹配，展示给用户选，用户选完后调 select_protocol(protocol_id=..., search_keyword=\"{keyword}\")"}


@tool(
    "select_protocol",
    "选择一份实验方案开始实验；protocol_id 传 null 表示自由记录模式（不按方案）。"
    "用户说要做某个实验时调用。如果之前调过 search_protocols，把搜索关键词传到 search_keyword，"
    "系统会记住这个偏好，下次同样的关键词自动选定。不要用于查看当前实验进度/当前步骤。",
    {
        "type": "object",
        "properties": {"protocol_id": {"type": ["string", "null"],
                                       "description": "方案ID，null表示自由记录"},
                       "search_keyword": {"type": "string",
                                          "description": "用户搜索时用的关键词（如'磷酸缓冲液'），用于记住偏好。如果之前没调过 search_protocols 就不传。"}},
        "required": ["protocol_id"],
        "additionalProperties": False,
    },
    kind="execute", title="选择实验方案 {protocol_id}", experiment_command=True,
    present=lambda a, r: ([f"已进入自由记录模式"] if r.get("mode") == "free" else
                          [f"方案：{r['protocol']['title']}",
                           f"共 {r['protocol']['total_steps']} 步，当前第 {r['step']['number']} 步：{r['step']['title']}"]),
)
def _select_protocol(protocol_id=None, search_keyword=None):
    result = domain.step_view(domain.start_session(protocol_id or None))
    if result.get("mode") == "free":
        result["ui_action"] = {
            "type": "switch_interaction_mode",
            "mode": "free",
            "view": "run",
        }
    else:
        result["ui_action"] = {
            "type": "switch_interaction_mode",
            "mode": "protocol",
            "protocol_id": result["protocol"]["id"],
            "view": "run",
        }
    if search_keyword and protocol_id:
        save_protocol_preference(search_keyword, protocol_id)
        result["preference_saved"] = True

    # 选定方案时开始新实验记录会话，让实验本立刻出现这个实验。
    # 不做这一步，用户选了方案但还没记录口述时，实验本里看不到这条实验。
    if isinstance(result, dict) and result.get("mode") == "protocol":
        try:
            from database.lab_record_store import start_new_session, save_record
            start_new_session()
            proto = result.get("protocol", {})
            step = result.get("step", {})
            save_record({
                "transcript": f"开始实验：{proto.get('title', '')}，共{proto.get('total_steps', 0)}步。",
                "entities": {},
                "evaluation": {},
                "step": {
                    "number": step.get("number", 1),
                    "title": step.get("title", ""),
                    "protocol": proto.get("title", ""),
                    "action": "started",
                },
            })
        except Exception:
            pass

    return result


@tool(
    "create_reagent_prep_from_text",
    "根据用户的自然语言描述创建一条试剂配置。仅当用户明确要求创建配方时调用；不要用于修改已有配置。",
    {
        "type": "object",
        "properties": {"description": {"type": "string"}},
        "required": ["description"],
        "additionalProperties": False,
    },
    kind="execute",
    title="AI 创建试剂配置",
    present=lambda a, r: [f"已创建：{r['name_zh']}", f"共 {len(r['steps'])} 个配制步骤"],
)
def _create_reagent_prep_from_text(description):
    draft = llm_bridge.generate_reagent_prep_draft(description)
    saved = domain.add_reagent_prep(draft)
    saved["ui_action"] = {"type": "navigate", "view": "reagent_prep"}
    return saved


@tool(
    "list_reagent_preps",
    "列出所有可配制的试剂/缓冲液配方。用户在实验前问“要先配什么”“有什么溶液要准备”时调用。不要用于查看当前实验进度。",
    {"type": "object", "properties": {}, "additionalProperties": False},
    kind="search", title="查看试剂配置库", experiment_command=True,
    present=lambda a, r: [f"共 {len(r['items'])} 条试剂配置，已在配置库展示全部"]
    + [f"{i}. {x['name_zh']}（{x['target_concentration'] or '工作液'}）" for i, x in enumerate(r["items"][:8], start=1)],
)
def _list_reagent_preps():
    return {
        "items": [domain.reagent_prep_view(p) for p in domain.reagent_preps().list_all()]
    }


@tool(
    "get_reagent_prep",
    "查看某一种试剂/缓冲液的具体配制方法、保存条件和危险提示。"
    "用户问“怎么配 50× TAE”“PBS 怎么配”时调用。不要用于列出所有配方。",
    {
        "type": "object",
        "properties": {"reagent_prep_id": {"type": "string", "description": "试剂配置ID"}},
        "required": ["reagent_prep_id"],
        "additionalProperties": False,
    },
    kind="read", title="查看试剂配方：{reagent_prep_id}", experiment_command=True,
    present=lambda a, r: [f"配方：{r['name_zh']}", f"目标：{r['target_concentration'] or '未指定'}，溶剂：{r['solvent'] or '未指定'}"]
    + [f"步骤 {i}. {s}" for i, s in enumerate(r["steps"], start=1)]
    + [f"⚠ {s['name']}：{'；'.join(s['statements'][:1])}" for s in r.get("safety", []) if s.get("critical")],
)
def _get_reagent_prep(reagent_prep_id):
    prep = domain.reagent_preps().get_by_id(reagent_prep_id)
    if prep is None:
        raise ValueError("没有这种试剂配置：" + str(reagent_prep_id))
    return domain.reagent_prep_view(prep)


@tool(
    "update_reagent_prep",
    "按ID更新一条试剂配置。仅当用户明确要求“改一下配方/修正某某配法”时调用；不要用于查询。",
    {
        "type": "object",
        "properties": {
            "reagent_prep_id": {"type": "string", "description": "试剂配置ID"},
            "reagent_prep": {"type": "object", "description": "完整的新配方 JSON，字段与 create_reagent_prep_from_text 生成的草稿一致"}
        },
        "required": ["reagent_prep_id", "reagent_prep"],
        "additionalProperties": False,
    },
    kind="execute", title="更新试剂配置：{reagent_prep_id}",
    present=lambda a, r: [f"已更新：{r['name_zh']}", f"共 {len(r['steps'])} 个配制步骤"],
)
def _update_reagent_prep(reagent_prep_id, reagent_prep):
    saved = domain.update_reagent_prep(reagent_prep_id, reagent_prep)
    saved["ui_action"] = {"type": "refresh"}
    return saved


@tool(
    "delete_reagent_prep",
    "按ID删除一条试剂配置。仅当用户明确要求“删掉这个配方”时调用；不要用于查询或修改其他配置。",
    {
        "type": "object",
        "properties": {"reagent_prep_id": {"type": "string", "description": "试剂配置ID"}},
        "required": ["reagent_prep_id"],
        "additionalProperties": False,
    },
    kind="execute", title="删除试剂配置：{reagent_prep_id}",
    present=lambda a, r: [f"已删除：{r['reagent_prep_id']}"],
)
def _delete_reagent_prep(reagent_prep_id):
    result = domain.delete_reagent_prep(reagent_prep_id)
    result["ui_action"] = {"type": "navigate", "view": "reagent_prep"}
    return result


@tool(
    "get_protocol_prep_requirements",
    "查看当前所选实验方案在开始前需要准备哪些试剂/缓冲液/仪器/耗材，并输出实验前准备清单。"
    "用户问“做这个实验前要先配什么/准备什么/清单”时调用。",
    {"type": "object", "properties": {}, "additionalProperties": False},
    kind="read", title="实验前准备清单", experiment_command=True,
    artifact_type="checklist",
    present=lambda a, r: _checklist_present_lines(r),
)
def _get_protocol_prep_requirements():
    from checklist_service import generate_protocol_checklist
    state = domain.session()
    protocol_id = state.selection.protocol.protocol_id if state.selection.protocol else None
    if not protocol_id:
        return {"protocol_id": None, "protocol_title": "", "items": [], "message": "当前没有选择实验方案。"}
    checklist = generate_protocol_checklist(protocol_id)
    checklist["message"] = None
    return checklist


def _checklist_present_lines(r: dict) -> list[str]:
    """把准备清单转成聊天里可读的勾选清单。"""
    if r.get("message"):
        return [r["message"]]
    lines = [f"请准备：{r.get('protocol_title') or ''}".strip()]
    reagents = r.get("reagents") or []
    if reagents:
        lines.append("试剂/缓冲液：")
        for item in reagents:
            mark = "☑" if item.get("found_in_storage") else "☐"
            suffix = ""
            if not item.get("found_in_storage") and item.get("available_prep"):
                suffix = " → 可配"
            lines.append(f"{mark} {item.get('name')}{suffix}")
    equipment = r.get("equipment") or []
    if equipment:
        lines.append("仪器：")
        for item in equipment:
            lines.append(f"☐ {item}")
    consumables = r.get("consumables") or []
    if consumables:
        lines.append("耗材：")
        for item in consumables:
            lines.append(f"☐ {item}")
    preps = r.get("prep_requirements") or []
    if preps:
        lines.append("需提前配制：")
        for item in preps:
            lines.append(f"☐ {item.get('name_zh') or item.get('name') or ''}")
    safety = r.get("safety") or []
    if safety:
        lines.append("安全提醒：")
        for item in safety[:4]:
            lines.append(f"⚠ 第{item.get('step')}步：{item.get('note')}")
    if not any([reagents, equipment, consumables, preps, safety]):
        lines.append("当前没有可用的准备材料清单。")
    return lines


@tool(
    "generate_prep_bench",
    "根据当前实验方案自动生成一张准备台：AI 推断这个实验按什么计量（体积/样本数/反应数…）、"
    "推荐默认规模，并把试剂/仪器/耗材分成「现成可用/需现配/缺料」三态，为现配项标注用量、耗时和时效。"
    "用户说'帮我准备''做这个实验要先弄什么''生成准备表'时调用。这是实验开始前的准备阶段。",
    {
        "type": "object",
        "properties": {
            "scale_input": {
                "type": ["string", "null"],
                "description": "用户口头说的规模，如'做50个样本''配200mL'。不传则由AI推断默认值。",
            }
        },
        "additionalProperties": False,
    },
    kind="read", title="生成实验准备台", experiment_command=True,
    artifact_type="prep_bench",
    present=lambda a, r: _prep_bench_present_lines(r),
)
def _generate_prep_bench(scale_input=None):
    from prep_bench_service import generate_prep_bench

    state = domain.session()
    protocol = state.selection.protocol if state.selection else None
    if not protocol:
        return {"prep_run_id": None, "message": "当前没有选择实验方案，无法生成准备台。"}
    bench = generate_prep_bench(
        protocol_id=protocol.protocol_id,
        scale_input=scale_input,
    )
    bench["ui_action"] = {"type": "navigate", "view": "run"}
    return bench


def _prep_bench_present_lines(r: dict) -> list[str]:
    """把准备台转成聊天里可读的摘要。"""
    if r.get("message"):
        return [r["message"]]
    lines = []
    if r.get("scale_unit"):
        basis = r.get("scale_basis", "")
        lines.append(
            f"计量方式：{r.get('scale_unit')}"
            + (f"（{basis}）" if basis else "")
            + f" · 推荐规模：{r.get('default_scale', '未指定')}"
        )
    summary = r.get("summary") or {}
    lines.append(
        f"共 {summary.get('total', 0)} 项："
        f"✅{summary.get('ready', 0)} 现成 · "
        f"🔬{summary.get('prep_now', 0)} 需配 · "
        f"⚠️{summary.get('missing', 0)} 缺料"
    )
    _SENSITIVITY_LABELS = {"prechill": "需预冷", "overnight": "需过夜", "fresh": "现配现用"}
    for item in (r.get("items") or [])[:12]:
        mark = {"ready": "✅", "prep_now": "🔬", "missing": "⚠️"}.get(
            item.get("state", ""), "☐"
        )
        qty = item.get("quantity")
        qty_str = f" {qty}" if qty else ""
        timing = item.get("time_sensitivity", "normal")
        tag = ""
        if timing and timing != "normal":
            tag = " [" + _SENSITIVITY_LABELS.get(timing, timing) + "]"
        minutes = item.get("estimated_minutes")
        mins = f" 约{minutes}分钟" if minutes else ""
        lines.append(f"{mark} {item.get('name', '')}{qty_str}{mins}{tag}")
    return lines


@tool(
    "mark_prep_item",
    "在准备台上把某一项标记为「有」或「没有」。用户说'这个我有了''BSA标准品有了'"
    "'那个缺'时调用。item_name 是试剂/耗材名称，state 是 have（有）或 missing（没有）。"
    "调用后返回更新后的准备台。",
    {
        "type": "object",
        "properties": {
            "item_name": {
                "type": "string",
                "description": "准备台上某一项的名称（如'BSA标准品''Bradford工作液'），尽量跟准备台上的名字对应",
            },
            "state": {
                "type": "string",
                "enum": ["have", "missing"],
                "description": "have=标记为已有（打勾）；missing=标记为缺料",
            },
        },
        "required": ["item_name", "state"],
        "additionalProperties": False,
    },
    kind="execute", title="标记准备项：{item_name}", experiment_command=True,
    present=lambda a, r: _prep_bench_present_lines(r) if r.get("items") else [r.get("message", "操作完成")],
)
def _mark_prep_item(item_name, state):
    from prep_bench_service import get_prep_bench, update_prep_item

    bench = get_prep_bench(None)
    if bench is None:
        return {"message": "当前没有准备台，请先说'帮我准备'生成一张。"}
    target = _find_prep_item_by_name(bench["items"], item_name)
    if target is None:
        return {"message": f"准备台上没有找到「{item_name}」，请确认名称是否匹配。"}
    updated = update_prep_item(target["prep_run_item_id"], state)
    updated["ui_action"] = {"type": "navigate", "view": "run"}
    return updated


def _find_prep_item_by_name(items, query):
    """在准备台条目里模糊匹配名称。"""
    import re
    q = re.sub(r"\s+", "", str(query or "").lower())
    if not q:
        return None
    # 精确匹配优先
    for item in items:
        if re.sub(r"\s+", "", str(item.get("name", "")).lower()) == q:
            return item
    # 子串匹配
    for item in items:
        name = re.sub(r"\s+", "", str(item.get("name", "")).lower())
        if name and (q in name or name in q):
            return item
    return None


@tool(
    "set_prep_bench_status",
    "标记准备台整体状态：ready（准备就绪，开始实验）或 skipped（跳过准备，直接开始）。"
    "用户说'准备好了''开始实验''不用准备了直接开始'时调用。",
    {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["ready", "skipped"],
                "description": "ready=准备就绪；skipped=跳过准备",
            },
        },
        "required": ["status"],
        "additionalProperties": False,
    },
    kind="execute", title="准备台：{status}", experiment_command=True,
    present=lambda a, r: [
        f"准备台已标记为{'就绪' if r.get('status') == 'ready' else '跳过'}",
        f"方案：{r.get('protocol_title', '')}",
    ] if r.get("status") else [r.get("message", "操作完成")],
)
def _set_prep_bench_status(status):
    from prep_bench_service import get_prep_bench, set_prep_run_status

    bench = get_prep_bench(None)
    if bench is None:
        return {"message": "当前没有准备台，请先说'帮我准备'生成一张。"}
    updated = set_prep_run_status(bench["prep_run_id"], status)
    updated["ui_action"] = {"type": "navigate", "view": "run"}
    return updated


@tool(
    "rescale_prep_bench",
    "修改准备台的实验规模（如'做20个样本''配1升'），AI 按新规模重算每项用量。"
    "用户说'我要做20个样本''改成配1升''规模改大一点'时调用。user_scale 是用户描述的新规模。",
    {
        "type": "object",
        "properties": {
            "user_scale": {
                "type": "string",
                "description": "用户要求的新规模，如'20个样本''1 L''48孔'",
            },
        },
        "required": ["user_scale"],
        "additionalProperties": False,
    },
    kind="execute", title="缩放准备台：{user_scale}", experiment_command=True,
    present=lambda a, r: _prep_bench_present_lines(r) if r.get("items") else [r.get("message", "操作完成")],
)
def _rescale_prep_bench(user_scale):
    from prep_bench_service import get_prep_bench, rescale_prep_bench

    bench = get_prep_bench(None)
    if bench is None:
        return {"message": "当前没有准备台，请先说'帮我准备'生成一张。"}
    updated = rescale_prep_bench(bench["prep_run_id"], user_scale)
    updated["ui_action"] = {"type": "navigate", "view": "run"}
    return updated


@tool(
    "get_current_step",
    "查看当前实验进行到第几步、当前步骤标题和操作要点、安全提示。用户问“现在做到哪了”时调用。"
    "注意：没有任何字段是必填的，不要催促用户补录，不要声称“还需要记录某某”。",
    {"type": "object", "properties": {}, "additionalProperties": False},
    kind="read", title="查看当前步骤", experiment_command=True,
    present=lambda a, r: ([f"当前为自由记录模式"] if r.get("mode") == "free" else
                          [f"第 {r['step']['number']}/{r['protocol']['total_steps']} 步：{r['step']['title']}",
                           f"状态：{r['step'].get('status', '')}"]
                          + ([f"已记录：{'、'.join(r['step']['recorded']) or '无'}"
                              ] if r.get("step", {}).get("recorded") else [])
                          + [f"⚠ {s['name']}：{'；'.join(s['statements'][:1])}" for s in r.get("safety", []) if s.get("critical")]),
)
def _get_current_step():
    view = domain.step_view(domain.session())
    view["progress"] = domain.step_progress_view(domain.session())
    return view


@tool(
    "move_step",
    "推进实验步骤。action 取 next（下一步）、prev（上一步）或 jump（跳到指定步）。"
    "用户说做完了/下一步/继续时调 next 推进；用户说回到上一步/搞错了/退回去时调 prev 回退。"
    "jump 时必须传 step_number。推进后告诉用户下一步做什么，并提示可以回退。",
    {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["next", "prev", "jump"]},
            "step_number": {"type": ["integer", "null"], "description": "仅 jump 时需要，next/prev 传 null 或省略"},
        },
        "required": ["action"],
        "additionalProperties": False,
    },
    kind="execute", title="推进步骤 {action}", experiment_command=True,
    present=lambda a, r: ([f"当前为自由记录模式"] if r.get("mode") == "free" else
                          [f"已到第 {r['step']['number']}/{r['protocol']['total_steps']} 步：{r['step']['title']}"]),
)
def _move_step(action, step_number=None):
    # 记录步骤推进前的状态，用于写入实验本
    pre_view = domain.step_view(domain.session())
    pre_step = None
    pre_protocol = None
    if isinstance(pre_view, dict) and pre_view.get("mode") == "protocol":
        pre_step = pre_view.get("step", {})
        pre_protocol = pre_view.get("protocol", {})

    result = domain.step_view(domain.move(action, step_number))
    result["ui_action"] = {"type": "navigate", "view": "run"}

    # 推进步骤时自动写一条实验记录，让实验本能看到进度变化。
    # 不做这一步，用户说"下一步"但本轮没有口述数据时，实验本一直是空的。
    if action == "next" and pre_step and isinstance(result, dict) and result.get("mode") == "protocol":
        try:
            from database.lab_record_store import save_record
            save_record({
                "transcript": f"已完成第{pre_step['number']}步：{pre_step['title']}",
                "entities": {},
                "evaluation": {},
                "step": {
                    "number": pre_step["number"],
                    "title": pre_step["title"],
                    "protocol": pre_protocol.get("title", ""),
                    "action": "completed",
                },
            })
        except Exception:
            pass

    return result


@tool(
    "navigate_view",
    "打开软件中的指定页面。用户说查看方案、查看安全库、打开设置或返回实验进行中时调用。不要用于处理实验数据或记录操作。",
    {
        "type": "object",
        "properties": {
            "view": {
                "type": "string",
                "enum": ["run", "protocols", "reagent_prep", "reagents", "records", "settings"],
            }
        },
        "required": ["view"],
        "additionalProperties": False,
    },
    kind="read",
    title="打开页面 {view}", experiment_command=True,
    present=lambda a, r: ["已打开目标页面"],
)
def _navigate_view(view):
    return {"ui_action": {"type": "navigate", "view": view}}


@tool(
    "get_protocol_detail",
    "查看一份实验方案的完整步骤、准备材料和安全提示。"
    "可以传 protocol_id 查任意方案（如从 search_protocols 拿到的 ID）；"
    "不传则自动查当前会话已选定的方案。"
    "当你需要读取已有方案的步骤来创建新方案时，用这个工具读出原文。",
    {
        "type": "object",
        "properties": {"protocol_id": {"type": "string", "description": "要查看的方案ID。不传则查当前会话的方案。"}},
        "required": [],
        "additionalProperties": False,
    },
    kind="read", experiment_command=True,
    title="查看方案 {protocol_id}",
    present=lambda a, r: [f"方案：{r['protocol']['title']}", f"共 {len(r['steps'])} 步"],
)
def _get_protocol_detail(protocol_id=None):
    if not protocol_id:
        # 未传 protocol_id 时，自动解析当前会话的方案
        view = domain.step_view(domain.session())
        if isinstance(view, dict) and view.get("mode") == "protocol":
            protocol_id = str(view["protocol"]["id"])
        else:
            raise ValueError("当前没有选定的方案。请传 protocol_id 指定要查看的方案。")
    result = domain.protocol_detail(protocol_id)
    result["ui_action"] = {"type": "navigate", "view": "protocols"}
    return result


@tool(
    "add_protocol_step",
    "在指定实验方案的某一步之后添加新步骤。仅当用户明确要求添加步骤时调用；不要用于修改已有步骤。",
    {
        "type": "object",
        "properties": {
            "protocol_id": {"type": "string"},
            "after_step_number": {"type": ["integer", "null"]},
            "title": {"type": "string"},
            "instruction": {"type": "string"},
        },
        "required": ["protocol_id", "after_step_number", "title", "instruction"],
        "additionalProperties": False,
    },
    kind="execute",
    title="添加方案步骤 {title}",
    present=lambda a, r: ["步骤已添加，方案版本已更新"],
)
def _add_protocol_step(protocol_id, after_step_number, title, instruction):
    result = domain.add_protocol_step({
        "protocol_id": protocol_id,
        "after_step_number": after_step_number,
        "title": title,
        "instruction": instruction,
        "must_record": [],
        "terms": [],
    })
    result["ui_action"] = {"type": "navigate", "view": "protocols"}
    return result


@tool(
    "update_protocol_step",
    "修改指定实验方案中某一步的标题、说明或安全提示。只传需要修改的字段；仅当用户明确要求修改时调用，不要用于添加/删除步骤。",
    {
        "type": "object",
        "properties": {
            "protocol_id": {"type": "string"},
            "step_number": {"type": "integer"},
            "title": {"type": ["string", "null"]},
            "instruction": {"type": ["string", "null"]},
            "hazard_note": {"type": ["string", "null"]},
        },
        "required": ["protocol_id", "step_number", "title", "instruction", "hazard_note"],
        "additionalProperties": False,
    },
    kind="execute",
    title="修改方案步骤 {step_number}",
    present=lambda a, r: ["步骤已修改，方案版本已更新"],
)
def _update_protocol_step(protocol_id, step_number, title=None, instruction=None, hazard_note=None):
    result = domain.update_step({
        "protocol_id": protocol_id,
        "step_number": step_number,
        "title": title,
        "instruction": instruction,
        "hazard_note": hazard_note,
    })
    result["ui_action"] = {"type": "navigate", "view": "protocols"}
    return result


@tool(
    "delete_protocol_step",
    "删除指定实验方案中的某一步。仅当用户明确要求删除时调用；不要用于修改其他步骤。",
    {
        "type": "object",
        "properties": {
            "protocol_id": {"type": "string"},
            "step_number": {"type": "integer"},
        },
        "required": ["protocol_id", "step_number"],
        "additionalProperties": False,
    },
    kind="execute",
    title="删除方案步骤 {step_number}",
    present=lambda a, r: ["步骤已删除，后续步骤已重新编号"],
)
def _delete_protocol_step(protocol_id, step_number):
    result = domain.delete_protocol_step(protocol_id, step_number)
    result["ui_action"] = {"type": "navigate", "view": "protocols"}
    return result

