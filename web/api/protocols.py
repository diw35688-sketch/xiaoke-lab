# -*- coding: utf-8 -*-
"""实验方案接口：选方案、走步骤、按方案做确定性判断与安全提示。"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import domain
import llm_bridge
from database.turn_store import ExperimentStateConflictError, TurnStore
from src.core.protocol_execution_state import ProtocolExecutionState
from src.core.protocol_navigation import decide_protocol_move
from src.core.reply_coordinator import ReplyCoordinator

router = APIRouter(prefix="/protocols", tags=["实验方案"])
turn_store = TurnStore()


class SelectPayload(BaseModel):
    protocol_id: str | None = None


class MovePayload(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=128)
    lab_session_id: str = Field(min_length=1, max_length=128)
    action: str
    step_number: int | None = None


class EvaluatePayload(BaseModel):
    entities: dict = {}
    transcript: str | None = None


class AiDraftPayload(BaseModel):
    text: str = Field(min_length=5, max_length=2000)


class SaveDraftPayload(BaseModel):
    protocol: dict


@router.get("")
def list_protocols():
    """可选实验方案列表；含自由记录模式。"""
    items = []
    for protocol in domain.protocols().list_all():
        items.append({
            "id": protocol.protocol_id,
            "title": protocol.title,
            "source": protocol.source,
            "version": protocol.version,
            "total_steps": len(protocol.steps),
        })
    return {"protocols": items}

@router.post("/ai-draft")
def ai_draft(payload: AiDraftPayload):
    """用 AI 生成实验方案草稿（不落盘）。"""
    try:
        return llm_bridge.generate_protocol_draft(payload.text)
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"AI 生成方案失败：{error}")



@router.post("/save-draft")
def save_draft(payload: SaveDraftPayload):
    """把 AI 生成的方案草稿确认保存进方案库（严格校验后落盘）。"""
    try:
        saved = domain.add_protocol(payload.protocol)
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"保存方案失败：{error}")
    return {"ok": True, "protocol": saved}


@router.get("/session")
def read_session(
    conversation_id: str | None = Query(default=None),
    lab_session_id: str | None = Query(default=None),
):
    """当前会话：已选方案、当前步骤、安全提示。"""
    return _session_view(conversation_id, lab_session_id, include_steps=False)


@router.get("/session/steps")
def session_steps(
    conversation_id: str | None = Query(default=None),
    lab_session_id: str | None = Query(default=None),
):
    """当前会话 + 全部步骤概要，供状态机卡片栏使用。"""
    return _session_view(conversation_id, lab_session_id, include_steps=True)


@router.post("/session")
def start(payload: SelectPayload):
    """选择方案开始会话；protocol_id 为空表示自由记录模式。"""
    try:
        state = domain.start_session(payload.protocol_id or None)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))
    return domain.step_view(state)


@router.post("/session/move")
def move(payload: MovePayload):
    """按会话事实和问题状态确定性切步，不调用模型。"""
    try:
        selected = domain.session()
        selected_view = domain.step_view(selected)
        if selected_view.get("mode") != "protocol":
            raise ValueError("当前没有选择实验方案。")
        protocol = selected_view["protocol"]
        stored = turn_store.load_experiment_state(
            payload.conversation_id, payload.lab_session_id
        )
        execution = ProtocolExecutionState.from_snapshot(
            stored.get("protocol_step_facts"),
            protocol_id=str(protocol["id"]),
            protocol_version=str(protocol["version"]),
            default_step_number=int(selected_view["step"]["number"]),
        )
        current_domain = selected.jump_to(execution.current_step_number)
        current_facts = execution.step_state(execution.current_step_number)
        evaluation = domain.evaluate_for_state(
            current_domain, current_facts.entity_values()
        )
        coordinator = ReplyCoordinator.from_snapshot(
            dict(stored.get("reply_coordinator") or {})
        )
        decision = decide_protocol_move(
            state=execution,
            action=payload.action,
            target_step_number=payload.step_number,
            total_steps=int(protocol["total_steps"]),
            evaluation=evaluation,
            unresolved=coordinator.active_clarifications(),
        )
        if not decision.allowed:
            raise HTTPException(status_code=409, detail={
                "reason": decision.reason,
                "missing_fields": list(decision.missing_fields),
                "blocking_question_numbers": list(
                    decision.blocking_question_numbers
                ),
                "deferred_question_numbers": list(
                    decision.deferred_question_numbers
                ),
                "current_step_number": decision.from_step_number,
                "target_step_number": decision.target_step_number,
            })
        revision = turn_store.save_protocol_navigation(
            conversation_id=payload.conversation_id,
            lab_session_id=payload.lab_session_id,
            expected_revision=int(stored["revision"]),
            protocol_step_facts=decision.state.to_snapshot(),
        )
        state = selected.jump_to(decision.state.current_step_number)
    except Exception as error:
        if isinstance(error, HTTPException):
            raise
        if isinstance(error, ExperimentStateConflictError):
            raise HTTPException(status_code=409, detail=str(error))
        raise HTTPException(status_code=400, detail=str(error))
    result = domain.step_view(state)
    result["revision"] = revision
    result["move"] = {
        "allowed": True,
        "reason": decision.reason,
        "from_step_number": decision.from_step_number,
        "target_step_number": decision.target_step_number,
        "deferred_question_numbers": list(decision.deferred_question_numbers),
    }
    return result


def _session_view(
    conversation_id: str | None,
    lab_session_id: str | None,
    *,
    include_steps: bool,
):
    selected = domain.session()
    base = (
        domain.all_steps_view(selected)
        if include_steps else domain.step_view(selected)
    )
    if (
        not conversation_id or not lab_session_id
        or base.get("mode") != "protocol"
    ):
        return base
    stored = turn_store.load_experiment_state(conversation_id, lab_session_id)
    protocol = base["protocol"]
    execution = ProtocolExecutionState.from_snapshot(
        stored.get("protocol_step_facts"),
        protocol_id=str(protocol["id"]),
        protocol_version=str(protocol["version"]),
        default_step_number=int(base["step"]["number"]),
    )
    scoped = selected.jump_to(execution.current_step_number)
    result = (
        domain.all_steps_view(scoped)
        if include_steps else domain.step_view(scoped)
    )
    result["revision"] = int(stored["revision"])
    result["step_statuses"] = {
        str(number): status.value
        for number, status in execution.statuses.items()
    }
    return result


@router.post("/evaluate")
def evaluate(payload: EvaluatePayload):
    """按当前步骤判断缺什么、有没有偏离方案。不调用大模型。"""
    try:
        return domain.evaluate(payload.entities or {})
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.get("/reagents")
def reagents():
    """试剂安全知识库概览。"""
    store = domain.hazmat()
    items = []
    for reagent in store.all_reagents():
        items.append({
            "name": reagent.name_zh,
            "cas": reagent.cas,
            "critical": reagent.is_critical,
            "codes": list(reagent.critical_codes),
        })
    return {"note": store.authority_note, "count": len(items), "reagents": items}

class StepEditPayload(BaseModel):
    """一个大步骤的可编辑内容。"""

    protocol_id: str
    step_number: int
    title: str | None = None
    instruction: str | None = None
    hazard_note: str | None = None
    protocol_values: dict | None = None
    must_record: list | None = None
    field_prompts: dict | None = None
    substeps: list | None = None


@router.put("/step")
def edit_step(payload: StepEditPayload):
    """编辑一个大步骤并落盘。

    改动先按契约校验（字段白名单、field_prompts 必须属于 must_record、
    小步序号连续），校验不过则整笔拒绝，不写入半成品。
    """
    try:
        return domain.update_step(payload.model_dump(exclude_none=False))
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"{type(error).__name__}: {error}")


@router.get("/entity-fields")
def entity_fields():
    """可用于 protocol_values / must_record 的实体字段白名单。"""
    return {"fields": domain.entity_field_names()}
