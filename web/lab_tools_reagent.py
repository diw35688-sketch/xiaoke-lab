# -*- coding: utf-8 -*-
from __future__ import annotations

"""试剂安全（由 lab_tools.py 拆分生成）。"""

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

# ---------------- 试剂安全 ----------------

@tool(
    "check_reagent_safety",
    "查询试剂的危险性信息，包含 CAS 号、GHS 危险性说明和高危提示。"
    "用户问某个试剂有没有毒、要注意什么、能不能直接倒掉时调用。"
    "数据来自 PubChem，未经实验室安全负责人复核，不能替代 MSDS。",
    {
        "type": "object",
        "properties": {"reagent": {"type": "string", "description": "试剂中文名，如 氢氧化钠"}},
        "required": ["reagent"],
        "additionalProperties": False,
    },
    kind="read", title="查询试剂安全：{reagent}", experiment_command=True,
    present=lambda a, r: ([r["message"]] if not r.get("found") else
                          [f"{r['name']}（CAS {r['cas'] or '未获取'}）"]
                          + ([f"⚠ 高危 {'/'.join(r['critical_codes'])}"] if r["critical"] else ["无高危项"])
                          + r["statements"][:3]),
)
def _check_reagent_safety(reagent):
    store = domain.hazmat()
    found = store.find(reagent) or (store.find_in_text(reagent) or [None])[0]
    if found is None:
        return {
            "found": False,
            "message": "知识库中没有这种试剂，不能据此认为它安全。请查阅 MSDS。",
        }
    return {
        "found": True,
        "name": found.name_zh,
        "cas": found.cas,
        "molecular_formula": found.molecular_formula,
        "critical": found.is_critical,
        "critical_codes": list(found.critical_codes),
        "statements": [s.text for s in found.hazard_statements],
        "disclaimer": store.authority_note,
    }

