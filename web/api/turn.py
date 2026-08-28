"""Unified SSE adapters for text and audio conversation Turns."""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from asr_application_service import AudioValidationError, get_asr_application_service
from database.turn_store import TurnRequestConflictError, TurnStore
from playback_runtime import web_playback_service
from src.core.conversation_turn import ExperimentContext, InputSource, InteractionMode
from src.core.turn_input import TurnInput
from src.core.turn_request_envelope import TurnRequestEnvelope
from turn_application_service import TurnApplicationService, TurnSubmission
from turn_processors import ChatProcessor, ExperimentProcessor, TemplateProcessor
from turn_stream_contract import (
    sse_event, turn_accepted_event, turn_error_event, turn_status_event,
)

router = APIRouter(prefix="/turn", tags=["统一 Turn"])
logger = logging.getLogger(__name__)

turn_store = TurnStore()
turn_application_service = TurnApplicationService(
    store=turn_store,
    chat_processor=ChatProcessor(),
    experiment_processor=ExperimentProcessor(turn_store),
    template_processor=TemplateProcessor(),
)

_STATUS_TEXT = {
    "audio_saved": "音频已保存",
    "asr": "正在识别语音…",
    "dispatching": "正在选择业务处理器…",
    "understanding": "正在理解内容…",
    "validating": "正在校验结果…",
    "saving": "正在保存…",
}


class _ModeFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str | None = Field(default=None, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    turn_id: str = Field(min_length=1, max_length=128)
    lab_session_id: str | None = Field(default=None, max_length=128)
    interaction_mode: InteractionMode
    experiment_context: ExperimentContext
    mode_version: int = Field(ge=1)

    def resolved_conversation_id(self) -> str:
        return self.conversation_id or str(uuid.uuid4())


class TurnTextRequest(_ModeFields):
    text: str = Field(min_length=1, max_length=10000)


class TurnAudioMetadata(_ModeFields):
    input_source: InputSource


def _stream(submission: TurnSubmission, envelope: TurnRequestEnvelope):
    yield sse_event(turn_accepted_event(
        conversation_id=envelope.conversation_id,
        request_id=envelope.request_id,
        turn_id=envelope.turn_id,
        replayed=submission.replayed,
    ))
    index = 0
    while not submission.future.done():
        phases, finished = submission.progress.wait(index)
        for phase in phases:
            index += 1
            yield sse_event(turn_status_event(phase, _STATUS_TEXT[phase]))
        if finished:
            break
    phases, _ = submission.progress.wait(index, timeout=0)
    for phase in phases:
        yield sse_event(turn_status_event(phase, _STATUS_TEXT[phase]))
    try:
        completed = submission.future.result()
    except Exception as error:
        yield sse_event(turn_error_event(
            type(error).__name__.upper(), str(error) or "Turn 处理失败。",
            retryable=True,
        ))
        yield sse_event({"type": "done"})
        return

    yield sse_event({
        "type": "turn_result",
        **dict(completed.result),
        "replayed": completed.replayed,
    })
    if not completed.replayed and completed.voice_items:
        try:
            for event in web_playback_service.authorize(
                completed.voice_items, conversation_id=envelope.conversation_id
            ):
                yield sse_event(event)
        except Exception:
            # 业务结果已经提交并上屏；语音授权失败不能吞掉流的 done，
            # 否则连续通话会误以为本轮仍在处理中而无法关闭麦克风。
            logger.exception(
                "voice_authorization_failed_after_commit request_id=%s",
                envelope.request_id,
            )
    yield sse_event({"type": "done"})


def _streaming_response(submission, envelope):
    return StreamingResponse(
        _stream(submission, envelope),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/text")
def turn_text(payload: TurnTextRequest):
    conversation_id = payload.resolved_conversation_id()
    try:
        turn = TurnInput(
            conversation_id, payload.request_id, payload.turn_id,
            payload.lab_session_id, payload.interaction_mode,
            payload.experiment_context, payload.mode_version,
            InputSource.TEXT, payload.text.strip(), None,
        )
        submission = turn_application_service.submit(turn)
    except TurnRequestConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    envelope = TurnRequestEnvelope(
        turn.conversation_id, turn.request_id, turn.turn_id, turn.lab_session_id,
        turn.interaction_mode, turn.experiment_context, turn.mode_version,
        turn.input_source,
    )
    return _streaming_response(submission, envelope)


@router.post("/audio")
async def turn_audio(
    audio: UploadFile = File(...), metadata: str = Form(...),
):
    try:
        parsed = TurnAudioMetadata.model_validate(json.loads(metadata))
        envelope = TurnRequestEnvelope(
            parsed.resolved_conversation_id(), parsed.request_id, parsed.turn_id,
            parsed.lab_session_id, parsed.interaction_mode,
            parsed.experiment_context, parsed.mode_version, parsed.input_source,
        )
        payload = await audio.read()
        get_asr_application_service().validate_wav(payload)
        submission = turn_application_service.submit_audio(
            envelope, payload, asr_service=get_asr_application_service()
        )
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=422, detail="metadata 不是合法 JSON。") from error
    except TurnRequestConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (AudioValidationError, TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return _streaming_response(submission, envelope)


@router.get("/requests/{request_id}")
def turn_diagnostics(request_id: str):
    result = turn_store.diagnostics(request_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Turn 请求不存在。")
    return result


def _delete_audio_paths(paths):
    service = get_asr_application_service()
    removed = 0
    failures = []
    for path in paths:
        try:
            removed += int(service.delete_audio(path))
        except Exception as error:
            failures.append({"path": path, "error": str(error)})
    return {"audio_removed": removed, "audio_failures": failures}


@router.get("/history")
def turn_history(conversation_id: str):
    """按会话读取已提交 Turn 的完整结构（含 think/tool/assistant 等块）。"""
    return {"turns": turn_store.list_committed_turns(conversation_id)}


@router.delete("/conversations/{conversation_id}")
def delete_conversation_turn_data(conversation_id: str):
    paths = turn_store.delete_conversation_turn_data(conversation_id)
    return {"conversation_id": conversation_id, **_delete_audio_paths(paths)}


@router.delete("/conversations/{conversation_id}/experiment-sessions/{lab_session_id}")
def delete_experiment_session(conversation_id: str, lab_session_id: str):
    paths = turn_store.delete_experiment_session(conversation_id, lab_session_id)
    return {
        "conversation_id": conversation_id,
        "lab_session_id": lab_session_id,
        **_delete_audio_paths(paths),
    }
