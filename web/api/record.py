# -*- coding: utf-8 -*-
"""HTTP adapter for the shared experiment-record application service."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import domain
import llm_bridge
import web_renderer
from playback_runtime import web_playback_service
from src.core.presentation_delivery import build_delivery_plan
from record_service import (
    RecordCommand,
    RecordPersistenceError,
    SharedRecordService,
)
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


def _current_terms() -> tuple[str, ...]:
    step = domain.session().current_step()
    return tuple(step.terms) if step is not None else ()


def _save_record_locked(item: dict[str, object]):
    with _lock:
        return save_record(item)


def _build_record_service() -> SharedRecordService:
    """Bind Web/database dependencies without putting them in the service."""

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
        request_id_factory=lambda: f"web-{uuid.uuid4().hex[:12]}",
    )


@router.post("")
def record(payload: RecordPayload):
    """处理一段口述，返回结构化结果与确定性追问。"""
    text = (payload.transcript or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="口述内容为空")
    try:
        return _record_response(text, extract=payload.extract)
    except RecordPersistenceError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


def _record_response(text: str, *, extract: bool) -> dict[str, object]:
    """Run the shared transaction and build the post-commit HTTP payload."""

    result = _build_record_service().record(
        RecordCommand(transcript=text, extract=extract)
    )
    response = dict(result.saved_record)
    plan = build_delivery_plan(result.intents, ui_mode="user")
    response["messages"] = web_renderer.WebRenderer().render_plan(plan)
    response["voice_delivery_events"] = list(
        web_playback_service.authorize(plan.voice_items)
    )
    return response


def _stream_event(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"


def _record_events(text: str, *, extract: bool):
    """Yield immediate progress, then the same committed result as POST /record."""

    yield _stream_event({
        "type": "record_status",
        "phase": "understanding",
        "text": "正在理解实验内容…",
    })
    try:
        response = _record_response(text, extract=extract)
    except RecordPersistenceError as error:
        yield _stream_event({"type": "record_error", "detail": str(error)})
        return
    except Exception as error:
        yield _stream_event({
            "type": "record_error",
            "detail": f"处理失败：{type(error).__name__}: {error}",
        })
        return
    yield _stream_event({"type": "record_result", "data": response})


@router.post("/stream")
def record_stream(payload: RecordPayload):
    """Stream progress while preserving the post-commit result boundary."""

    text = (payload.transcript or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="口述内容为空")
    return StreamingResponse(
        _record_events(text, extract=payload.extract),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )



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
