# -*- coding: utf-8 -*-
from __future__ import annotations

"""试剂配置流程（由 lab_tools.py 拆分生成）。"""

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

# ---------- 试剂配置流程工具（小型分支 protocol） ----------

def _flow_conversation_id() -> str:
    """试剂配制流程的稳定会话键。

    以前从磁盘文件读取 current-conversation-id.txt，结果经常和真实会话不同步，
    导致"配置写错会话"。现在改用稳定常量：单用户助手只有一个活动会话，
    配制流程挂在会话上，不再随聊天会话漂移。
    """
    return "lab-session"


def _flow_present_lines(flow: dict) -> list[str]:
    if not flow:
        return ["当前没有进行中的试剂配置流程。"]
    steps = flow.get("steps") or []
    current = int(flow.get("current_index") or 0)
    sub_index = int(flow.get("current_sub_index") or 0)
    sub_steps = flow.get("sub_steps") or []
    sub_count = int(flow.get("current_sub_count") or len(sub_steps) or 1)
    step_text = flow.get("current_step_text") or (steps[current] if steps and current < len(steps) else "")
    name = flow.get("name_zh") or flow.get("prep_id") or "试剂配置"
    status = flow.get("status") or "running"
    if status == "completed" or (steps and current >= len(steps)):
        return [f"✅ {name} 配置完成，全部 {len(steps)} 步已做完。"]
    # 子步骤是否已被状态机记录（sub_count>1 说明当前大步骤已被拆分）
    decomposed = sub_count > 1
    header = f"📋 {name}（第 {current + 1}/{len(steps)} 步"
    if decomposed:
        header += f"，小步骤 {sub_index + 1}/{sub_count}"
    header += "）"
    lines = [header]
    lines.append("")
    if decomposed:
        # 已拆分：当前小步骤是模型唯一要说的内容
        current_sub = flow.get("step") or (sub_steps[sub_index] if sub_index < len(sub_steps) else step_text)
        lines.append(f"▶ 当前小步骤（{sub_index + 1}/{sub_count}）：{current_sub}")
        if sub_index + 1 < sub_count:
            lines.append("")
            lines.append(f"本大步骤还有 {sub_count - sub_index - 1} 个小步骤没做。用户说做好了后调用 advance_reagent_prep_flow 进入下一个小步骤（仍在同一大步骤内）。")
        else:
            lines.append("")
            lines.append("这是本大步骤的最后一个小步骤。用户说做好了后调用 advance_reagent_prep_flow 进入下一个大步骤。")
    else:
        # 未拆分：展示大步骤原文，并提示 AI 若含多个动作就先拆分落库
        lines.append(f"▶ 当前步骤原文：{step_text}")
        lines.append("")
        lines.append("⚠️ 如果这一步里包含多个独立动作（例如一次称取好几种试剂、或称取+溶解连在一起），")
        lines.append("请先调用 set_reagent_prep_substeps 把它拆成一个个小步骤——每条小步骤只含一个动作。")
        lines.append("拆分会写进记录，之后 advance 会按记录逐个小步骤推进，不会跳步、也不会漂移。")
        lines.append("如果这一步只有一个动作，无需拆分，直接引导用户做完后调 advance_reagent_prep_flow。")
    # 计算提示
    focus = flow.get("step") or step_text
    has_quantity = bool(re.search(r"\d+(?:\.\d+)?\s*(g|mg|mL|ml|mol|克|毫升|升)", focus))
    has_calc_word = any(w in focus for w in ("称取", "量取", "稀释", "浓度", "定容"))
    if has_quantity or has_calc_word:
        lines.append("")
        lines.append("💡 涉及称量/浓度且用户需求与配方参考值不同时，先调 calculate_solution_prep 或 calculate_proportion 算出本次实际用量再说。")
    # 剩余大步骤仅列标题
    remaining = steps[current + 1:] if current + 1 < len(steps) else []
    if remaining:
        lines.append("")
        lines.append(f"后续还有 {len(remaining)} 个大步骤（等当前大步骤全部做完后再说）：")
        for i, s in enumerate(remaining):
            brief = s[:30] + "…" if len(s) > 30 else s
            lines.append(f"  {current + 2 + i}. {brief}")
    return lines


@tool(
    "start_reagent_prep_flow",
    "启动某个试剂配方/缓冲液的逐步配制流程（相当于一个小型分支 protocol）。"
    "用户说“开始配 PBS/开始配置这个试剂/按这个配方开始”时调用。"
    "调用后返回第一步原文——你只需语音描述这第一步。"
    "重要：如果第一步里包含多个独立动作（如“称取 A、B、C”三种试剂），"
    "先调用 set_reagent_prep_substeps 把它拆成一条一个小动作的小步骤列表写进记录，"
    "然后逐个小步骤引导用户——每说完一个等用户确认，再调 advance 进入下一个小步骤。"
    "只有单一步骤（一个动作）时不用拆。涉及称量/浓度时先调 calculate_solution_prep 算用量。",
    {
        "type": "object",
        "properties": {
            "reagent_prep_id": {"type": "string", "description": "试剂配置ID，先用 list_reagent_preps/get_reagent_prep 获取"},
        },
        "required": ["reagent_prep_id"],
        "additionalProperties": False,
    },
    kind="execute", title="开始配置：{reagent_prep_id}",
    present=lambda a, r: _flow_present_lines(r),
)
def _start_reagent_prep_flow(reagent_prep_id):
    from api.reagent_prep import FlowStartPayload, start_flow
    cid = _flow_conversation_id()
    flow = start_flow(FlowStartPayload(conversation_id=cid, reagent_prep_id=reagent_prep_id))
    flow["name_zh"] = flow.get("prep_id") or reagent_prep_id
    try:
        prep = domain.reagent_preps().get_by_id(reagent_prep_id)
        if prep:
            flow["name_zh"] = prep.name_zh
    except Exception:
        pass
    flow["ui_action"] = {"type": "navigate", "view": "reagent_prep"}
    flow["guidance"] = (
        "只描述当前步骤。如果当前步骤原文里含多个独立动作（多个称量/量取连在一起），"
        "先调 set_reagent_prep_substeps 拆成小步骤写进记录，再逐个引导。"
        "每个小步骤做完只是口头确认；全部小步骤做完才调 advance_reagent_prep_flow 进入下一个大步骤。"
        "涉及称量/浓度且与参考值不同时先调 calculate_solution_prep。"
    )
    return flow


@tool(
    "set_reagent_prep_substeps",
    "把当前试剂配制步骤拆分成一条一个小动作的小步骤列表，写进状态机记录。"
    "当某个步骤包含多个独立动作（如“称取胰化蛋白胨、酵母提取物、NaCl”三种试剂，或“称取+溶解”连在一起）时调用。"
    "拆分后 advance 会按记录逐个小步骤推进，避免跳步或多轮漂移。"
    "每条小步骤只描述一个动作；不要把整个配方所有步骤都塞进来，只拆当前这一大步。",
    {
        "type": "object",
        "properties": {
            "step_substeps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "当前大步骤拆成的小步骤，每条一个动作，例如 [\"称取胰化蛋白胨 2 g 放入烧杯\",\"称取酵母提取物 0.5 g 放入同一烧杯\",\"称取 NaCl 0.05 g 放入同一烧杯\"]",
            }
        },
        "required": ["step_substeps"],
        "additionalProperties": False,
    },
    kind="execute", title="拆分当前步骤",
    present=lambda a, r: _flow_present_lines(r),
)
def _set_reagent_prep_substeps(step_substeps):
    from api.reagent_prep import FlowSubstepsPayload, set_substeps
    cid = _flow_conversation_id()
    flow = set_substeps(FlowSubstepsPayload(conversation_id=cid, step_substeps=step_substeps))
    try:
        prep = domain.reagent_preps().get_by_id(flow.get("prep_id"))
        if prep:
            flow["name_zh"] = prep.name_zh
    except Exception:
        pass
    flow["guidance"] = (
        "已记录当前大步骤的小步骤。现在只引导用户做第 1 个小步骤；"
        "用户说做好了就调 advance_reagent_prep_flow 进入下一个小步骤（仍在同一大步骤内）。"
    )
    return flow


@tool(
    "show_reagent_prep_flow",
    "查看当前正在进行的试剂配制流程（当前进度、剩余步骤）。当用户问“配到哪一步/这个试剂配制流程”时调用。只读。",
    {"type": "object", "properties": {}, "additionalProperties": False},
    kind="search", title="查看试剂配制进度",
    present=lambda a, r: _flow_present_lines(r),
)
def _show_reagent_prep_flow():
    from api.reagent_prep import FlowStartPayload, current_flow
    cid = _flow_conversation_id()
    try:
        flow = current_flow(cid)
    except Exception:
        return {"active": False, "message": "当前没有进行中的试剂配置流程。"}
    try:
        prep = domain.reagent_preps().get_by_id(flow.get("prep_id"))
        if prep:
            flow["name_zh"] = prep.name_zh
    except Exception:
        pass
    return flow


@tool(
    "advance_reagent_prep_flow",
    "推进当前试剂配制流程。"
    "状态机记录了当前大步骤的小步骤（如果有）：调用 next 会先在当前大步骤内走到下一个小步骤，"
    "走完最后一个小步骤才进入下一个大步骤。所以“做好了/下一步”一律调 next，状态机会自动判断是进下一个小步骤还是下一个大步骤。"
    "用户确认整个配置结束时调 complete。",
    {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["next", "complete"], "description": "next=完成当前小步骤，进入下一个（小步骤或大步骤由状态机决定）；complete=结束整个配制"}
        },
        "required": ["action"],
        "additionalProperties": False,
    },
    kind="execute", title="推进试剂配置：{action}",
    present=lambda a, r: _flow_present_lines(r) if r.get("status") != "completed" else [f"配置完成：{r.get('name_zh') or r.get('prep_id')}"],
)
def _advance_reagent_prep_flow(action="next"):
    from api.reagent_prep import FlowMovePayload, move_flow
    cid = _flow_conversation_id()
    flow = move_flow(FlowMovePayload(conversation_id=cid, action=action))
    try:
        prep = domain.reagent_preps().get_by_id(flow.get("prep_id"))
        if prep:
            flow["name_zh"] = prep.name_zh
    except Exception:
        pass
    if flow.get("status") != "completed":
        flow["guidance"] = (
            "只描述当前这一步的操作（返回的 step 字段）。如果进入了新的大步骤且它含多个动作，"
            "先调 set_reagent_prep_substeps 拆分；否则直接引导。不要提前说出后续步骤。"
        )
    return flow
