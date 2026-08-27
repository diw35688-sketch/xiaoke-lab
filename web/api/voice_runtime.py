"""Browser-to-server voice runtime fact events."""

import logging

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import settings_store
from database.crud import conversation_exists, ensure_conversation
from src.core.voice_runtime_state import VoiceRuntimeEventType, VoiceRuntimeState
from src.core.playback_reevaluation import ReevaluationTrigger
from src.core.presentation_intent import MessagePriority
from src.core.presentation_intent import MessageKind
from src.core.presentation_delivery import VoiceDeliveryItem
from src.core.tts_adapter import TTSExecutionEvent, TTSExecutionEventType
from playback_runtime import web_playback_service
from voice_runtime_sessions import voice_runtime_sessions


router = APIRouter(prefix="/voice/runtime", tags=["voice-runtime"])
logger = logging.getLogger(__name__)


class VoiceRuntimeEventRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=64)
    type: Literal[
        "user_speech_started",
        "user_speech_paused",
        "user_speech_resumed",
        "segment_finalized",
        "asr_processing_started",
        "asr_processing_finished",
        "asr_processing_failed",
        "tts_started",
        "tts_finished",
        "tts_stopped",
        "tts_failed",
    ]
    intent_id: str | None = Field(default=None, min_length=1, max_length=128)
    priority: str | None = Field(default=None, max_length=32)
    error: str | None = Field(default=None, max_length=1000)


class VoiceDeliveryClientResultRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=1, max_length=64)
    authorization: str | None = Field(default=None, max_length=32)
    reason: str | None = Field(default=None, max_length=128)
    intent_id: str | None = Field(default=None, max_length=128)


class VoiceStartupRequest(BaseModel):
    conversation_id: str | None = Field(default=None, min_length=1, max_length=64)
    source_block_id: str = Field(min_length=1, max_length=128)
    local_hour: int = Field(ge=0, le=23)
    local_minute: int = Field(ge=0, le=59)
    mode: Literal["chat", "free", "protocol"] = "chat"


_EVENT_TYPES = {
    "user_speech_started": VoiceRuntimeEventType.USER_SPEECH_STARTED,
    "user_speech_paused": VoiceRuntimeEventType.USER_SPEECH_PAUSED,
    "user_speech_resumed": VoiceRuntimeEventType.USER_SPEECH_RESUMED,
    "segment_finalized": VoiceRuntimeEventType.SEGMENT_FINALIZED,
    "asr_processing_started": VoiceRuntimeEventType.ASR_PROCESSING_STARTED,
    "asr_processing_finished": VoiceRuntimeEventType.ASR_PROCESSING_FINISHED,
    "asr_processing_failed": VoiceRuntimeEventType.ASR_PROCESSING_FAILED,
    "tts_started": VoiceRuntimeEventType.TTS_STARTED,
    "tts_finished": VoiceRuntimeEventType.TTS_FINISHED,
    "tts_stopped": VoiceRuntimeEventType.TTS_STOPPED,
    "tts_failed": VoiceRuntimeEventType.TTS_FAILED,
}

_TTS_EVENT_TYPES = {
    "tts_started": TTSExecutionEventType.STARTED,
    "tts_finished": TTSExecutionEventType.FINISHED,
    "tts_stopped": TTSExecutionEventType.STOPPED,
    "tts_failed": TTSExecutionEventType.FAILED,
}


def _state_payload(state: VoiceRuntimeState) -> dict:
    return {
        "user_speaking": state.user_speaking,
        "segment_capturing": state.segment_capturing,
        "asr_processing": state.asr_processing,
        "tts_playing": state.tts_playing,
        "active_tts_priority": (
            state.active_tts_priority.value if state.active_tts_priority is not None else None
        ),
    }


@router.post("/startup")
def create_voice_startup(request: VoiceStartupRequest):
    """Create the page-start welcome through the normal playback scheduler."""
    conversation_id = ensure_conversation(request.conversation_id)
    if request.local_hour < 6:
        greeting = "凌晨好"
    elif request.local_hour < 12:
        greeting = "早上好"
    elif request.local_hour < 18:
        greeting = "下午好"
    else:
        greeting = "晚上好"
    mode_text = {
        "chat": "自由聊天",
        "free": "自由实验记录",
        "protocol": "方案实验",
    }[request.mode]
    item = VoiceDeliveryItem(
        intent_id=f"voice-startup-{conversation_id}",
        kind=MessageKind.WAKE_ACK,
        priority=MessagePriority.DIRECT_ACK,
        voice_text=(
            f"{greeting}，现在是{request.local_hour}点{request.local_minute:02d}分，"
            f"当前为{mode_text}。"
        ),
        source_block_id=request.source_block_id,
        speech_rate=settings_store.current().tts_speed,
    )
    return {
        "conversation_id": conversation_id,
        "welcome_text": item.voice_text,
        "voice_delivery_events": web_playback_service.authorize(
            (item,), conversation_id=conversation_id
        ),
    }


@router.post("/event")
def consume_voice_runtime_event(request: VoiceRuntimeEventRequest):
    if not conversation_exists(request.conversation_id):
        raise HTTPException(status_code=404, detail="当前会话不存在。")

    priority = None
    if request.type in _TTS_EVENT_TYPES:
        if request.intent_id is None or request.priority is None:
            raise HTTPException(
                status_code=422,
                detail="TTS 事件必须携带 intent_id 和 priority。",
            )
        try:
            priority = MessagePriority[request.priority]
        except KeyError as error:
            raise HTTPException(status_code=422, detail="TTS priority 无效。") from error
        if request.type == "tts_failed" and not (request.error or "").strip():
            raise HTTPException(status_code=422, detail="tts_failed 必须携带 error。")

    state, applied = voice_runtime_sessions.consume(
        request.conversation_id,
        _EVENT_TYPES[request.type],
        tts_priority=priority if request.type == "tts_started" else None,
    )
    delivery_events = []
    if applied and request.type in _TTS_EVENT_TYPES:
        delivery_events.extend(
            web_playback_service.handle_tts_event(
                request.conversation_id,
                TTSExecutionEvent(
                    _TTS_EVENT_TYPES[request.type],
                    request.intent_id or "",
                    priority,
                    request.error,
                ),
            )
        )
    if applied and request.type in (
        "asr_processing_finished",
        "asr_processing_failed",
    ):
        delivery_events.extend(
            web_playback_service.reevaluate(
                request.conversation_id,
                ReevaluationTrigger.VOICE_INPUT_BECAME_IDLE,
            )
        )
    if applied and request.type in (
        "tts_finished",
        "tts_stopped",
        "tts_failed",
    ):
        delivery_events.extend(
            web_playback_service.reevaluate(
                request.conversation_id,
                ReevaluationTrigger.TTS_PLAYBACK_ENDED,
            )
        )
    return {
        "conversation_id": request.conversation_id,
        "type": request.type,
        "applied": applied,
        "state": _state_payload(state),
        "voice_delivery_events": delivery_events,
    }


@router.post("/client-result")
def record_voice_delivery_client_result(request: VoiceDeliveryClientResultRequest):
    """Record the browser's final playback-boundary outcome without changing state."""
    if not conversation_exists(request.conversation_id):
        raise HTTPException(status_code=404, detail="当前会话不存在。")
    logger.info(
        "voice_delivery_client_result conversation_id=%s code=%s authorization=%s reason=%s intent_id=%s",
        request.conversation_id,
        request.code,
        request.authorization,
        request.reason,
        request.intent_id,
    )
    return {"accepted": True}
