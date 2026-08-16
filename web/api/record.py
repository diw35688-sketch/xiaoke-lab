# -*- coding: utf-8 -*-
"""实验记录主链路：口述 → 结构化实体 → 按方案确定性判断 → 追问。

分工严格：
- LLM 只负责从口述里抽取实体（它擅长的）。
- 缺什么字段、有没有偏离方案，由程序按方案算（确定性，不可漂移）。
"""

from __future__ import annotations

import threading
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import domain
import llm_bridge
from database.lab_record_store import (
    current_session_id,
    list_records,
    next_segment_id,
    save_record,
    start_new_session,
)
from src.core.rule_entity_extraction import extract_entities

router = APIRouter(prefix="/record", tags=["实验记录"])

_lock = threading.Lock()





class RecordPayload(BaseModel):
    transcript: str
    extract: bool = True


def _next_segment() -> int:  # deprecated: 段号统一由 _next_record_segment 从 SQLite 推算
    return 0
    with _lock:
        pass
        pass


def _next_record_segment(session_id: str) -> int:
    with _lock:
        return next_segment_id(session_id)


@router.post("")
def record(payload: RecordPayload):
    """处理一段口述，返回结构化结果与确定性追问。"""
    text = (payload.transcript or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="口述内容为空")

    session_id = current_session_id()
    segment_id = _next_record_segment(session_id)
    entities: dict = {}
    extraction = None

    extraction_source = "none"
    if payload.extract:
        try:
            extraction = llm_bridge.extract(text, session_id, segment_id)
            for event in extraction["events"]:
                for name, value in event["entities"].items():
                    if value and not entities.get(name):
                        entities[name] = value
            extraction_source = "degraded" if extraction.get("degraded") else "llm"
        except Exception as error:
            extraction = {
                "events": [],
                "degraded": True,
                "error": f"{type(error).__name__}: {error}",
            }
            extraction_source = "degraded"

    # 模型不可用或没抽到东西时，用规则抽取兜底：
    # 数量、单位、浓度、温度、时长这些有明确书写形式的事实不需要大模型。
    if not entities:
        step = domain.session().current_step()
        known_terms = tuple(step.terms) if step is not None else ()
        rule_entities = extract_entities(text, known_terms)
        rule_fields = {
            name: value
            for name, value in vars(rule_entities).items()
            if value
        }
        if rule_fields:
            entities.update(rule_fields)
            extraction_source = "rule"

    evaluation = domain.evaluate(entities)
    item = {
        "segment_id": segment_id,
        "session_id": session_id,
        "transcript": text,
        "entities": entities,
        "extraction": extraction,
        "extraction_source": extraction_source,
        "evaluation": evaluation,
        "step": domain.step_view(domain.session()),
        "at": datetime.now().isoformat(timespec="seconds"),
    }
    with _lock:
        try:
            saved = save_record(item)
        except Exception as error:
            raise HTTPException(status_code=500, detail=f"实验记录落盘失败：{error}") from error
        return saved



@router.get("/history")
def history():
    """本次会话已记录的全部段落。"""
    session_id = current_session_id()
    items = list_records(session_id)
    return {"session_id": session_id, "count": len(items), "items": items}


@router.post("/reset")
def reset():
    """开始新会话。"""
    session_id = start_new_session()
    with _lock:
        pass



    return {"session_id": session_id, "message": "已开始新会话"}
