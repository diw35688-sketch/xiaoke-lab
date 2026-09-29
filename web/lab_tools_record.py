# -*- coding: utf-8 -*-
from __future__ import annotations

"""实验记录（由 lab_tools.py 拆分生成）。"""

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

# ---------------- 实验记录 ----------------

def _current_terms() -> tuple[str, ...]:
    step = domain.session().current_step()
    return tuple(step.terms) if step is not None else ()


def _next_record_segment(session_id: str) -> int:
    with _record_lock:
        return next_segment_id(session_id)


def _save_record_locked(item: dict[str, object]):
    with _record_lock:
        return save_record(item)


def _build_record_service() -> SharedRecordService:
    """Bind tool/runtime dependencies to the shared record application service."""

    return SharedRecordService(
        current_session_id=current_session_id,
        next_segment_id=_next_record_segment,
        list_records=list_records,
        extract_entities_llm=llm_bridge.extract,
        extract_entities_rule=extract_entities,
        current_terms=_current_terms,
        evaluate=domain.evaluate,
        step_view=lambda: domain.step_view(domain.session()),
        save_record=_save_record_locked,
        clock=datetime.now,
        request_id_factory=lambda: f"tool-{uuid.uuid4().hex[:12]}",
    )

@tool(
    "record_observation",
    "记录一段实验口述，系统会抽取其中的数量、单位、浓度、温度、时长等实测值，"
    "并按当前方案判断还缺什么、有没有偏离方案规定值。"
    "用户描述刚做了什么操作或测到什么数据时调用。用户说做完了/完成了/下一步时，"
    "如果本轮有新数据就先调本工具记录，然后调 move_step(action=\"next\") 推进步骤。"
    "不要把闲聊或提问当记录。",
    {
        "type": "object",
        "properties": {"transcript": {"type": "string", "description": "用户口述原文"}},
        "required": ["transcript"],
        "additionalProperties": False,
    },
    kind="execute", title="记录实验口述", experiment_command=True,
    present=lambda a, r: ([f"抽取：{'、'.join(f'{k}={v}' for k, v in r['entities'].items()) or '未抽到结构化字段'}"]
                          + [f"⚠ 偏差：{d['field']} 实际 {d['actual_value']}，方案 {d['protocol_value']}" for d in r["deviations"]]),
)
def _record_observation(transcript):
    result = _build_record_service().record(RecordCommand(transcript=transcript))
    observation = result.observation_result
    saved_evaluation = result.saved_record.get("evaluation")
    evaluation = saved_evaluation if isinstance(saved_evaluation, dict) else {}
    entities = dict(
        observation.entities
        if observation is not None
        else result.saved_record.get("entities") or {}
    )
    deviations = [
        dict(d) if not isinstance(d, dict) else d
        for d in (
            observation.deviations
            if observation is not None
            else evaluation.get("deviations") or ()
        )
    ]
    payload = {
        "transcript": (
            observation.transcript
            if observation is not None
            else result.saved_record["transcript"]
        ),
        "entities": entities,
        "recorded_fields": sorted(entities.keys()),
        "deviations": deviations,
    }
    # 同步抽取的实体到 domain 步骤进度追踪器。
    # 不做这一步，_progress 只记字段名不记值，下一轮上下文看不到实测值，
    # 模型会反复追问"实际称了多少克"。
    if entities:
        try:
            step = domain.session().current_step()
            if step is not None:
                domain.record_step_fields(step.step_number, dict(entities), bool(deviations))
        except Exception:  # noqa: BLE001
            pass
    return PresentedToolResult(
        payload=payload,
        presentation_plan=build_delivery_plan(
            result.intents, ui_mode="user",
            speech_rate=settings_store.current().tts_speed,
        ),
    )

