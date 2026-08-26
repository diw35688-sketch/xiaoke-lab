"""Event-driven ownership of mutable voice runtime facts.

The coordinator is the only writer.  It consumes fact events and replaces its
immutable state value; it does not capture audio, invoke ASR/TTS, create a
PlaybackContext, or decide whether anything may be played.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from threading import Lock

from src.core.presentation_intent import MessagePriority


class VoiceRuntimeEventType(str, Enum):
    USER_SPEECH_STARTED = "user_speech_started"
    USER_SPEECH_PAUSED = "user_speech_paused"
    USER_SPEECH_RESUMED = "user_speech_resumed"
    SEGMENT_FINALIZED = "segment_finalized"
    ASR_PROCESSING_STARTED = "asr_processing_started"
    ASR_PROCESSING_FINISHED = "asr_processing_finished"
    ASR_PROCESSING_FAILED = "asr_processing_failed"
    TTS_STARTED = "tts_started"
    TTS_FINISHED = "tts_finished"
    TTS_STOPPED = "tts_stopped"
    TTS_FAILED = "tts_failed"


@dataclass(frozen=True)
class VoiceRuntimeEvent:
    event_type: VoiceRuntimeEventType
    tts_priority: MessagePriority | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.event_type, VoiceRuntimeEventType):
            raise TypeError("event_type 必须是 VoiceRuntimeEventType。")
        if self.tts_priority is not None and not isinstance(
            self.tts_priority, MessagePriority
        ):
            raise TypeError("tts_priority 必须是 MessagePriority 或 None。")
        if self.event_type is VoiceRuntimeEventType.TTS_STARTED:
            if self.tts_priority is None:
                raise ValueError("TTS_STARTED 必须携带 tts_priority。")
        elif self.tts_priority is not None:
            raise ValueError("只有 TTS_STARTED 可以携带 tts_priority。")


@dataclass(frozen=True)
class VoiceRuntimeState:
    user_speaking: bool = False
    segment_capturing: bool = False
    asr_processing: bool = False
    tts_playing: bool = False
    active_tts_priority: MessagePriority | None = None

    def __post_init__(self) -> None:
        for name in (
            "user_speaking",
            "segment_capturing",
            "asr_processing",
            "tts_playing",
        ):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} 必须是 bool。")
        if self.user_speaking and not self.segment_capturing:
            raise ValueError("用户讲话时必须处于片段采集状态。")
        if self.active_tts_priority is not None and not isinstance(
            self.active_tts_priority, MessagePriority
        ):
            raise TypeError("active_tts_priority 必须是 MessagePriority 或 None。")
        if self.tts_playing != (self.active_tts_priority is not None):
            raise ValueError("tts_playing 与 active_tts_priority 必须同时存在或同时清空。")


class VoiceStateCoordinator:
    """The sole mutable owner that reduces voice events into runtime facts."""

    def __init__(self, initial_state: VoiceRuntimeState | None = None) -> None:
        if initial_state is not None and not isinstance(initial_state, VoiceRuntimeState):
            raise TypeError("initial_state 必须是 VoiceRuntimeState 或 None。")
        self._state = initial_state or VoiceRuntimeState()
        self._lock = Lock()

    def snapshot(self) -> VoiceRuntimeState:
        with self._lock:
            return self._state

    def consume(self, event: VoiceRuntimeEvent) -> VoiceRuntimeState:
        if not isinstance(event, VoiceRuntimeEvent):
            raise TypeError("event 必须是 VoiceRuntimeEvent。")
        with self._lock:
            next_state = self._reduce(self._state, event)
            self._state = next_state
            return next_state

    @staticmethod
    def _reduce(
        state: VoiceRuntimeState, event: VoiceRuntimeEvent
    ) -> VoiceRuntimeState:
        kind = event.event_type

        if kind is VoiceRuntimeEventType.USER_SPEECH_STARTED:
            if state.segment_capturing:
                raise ValueError("片段已在采集；请使用 USER_SPEECH_RESUMED。")
            # 连续通话的 USER_SPEECH_STARTED 与浏览器 stopSpeech() 是同一
            # 次 barge-in 的两面。即使独立的 TTS_STOPPED HTTP 事实丢失或
            # 倒序，用户开口也必须立即终止服务端的旧播放占用；旧内容不恢复。
            return replace(
                state,
                user_speaking=True,
                segment_capturing=True,
                tts_playing=False,
                active_tts_priority=None,
            )

        if kind is VoiceRuntimeEventType.USER_SPEECH_PAUSED:
            if not state.user_speaking:
                raise ValueError("用户未在讲话，不能进入停顿。")
            return replace(state, user_speaking=False)

        if kind is VoiceRuntimeEventType.USER_SPEECH_RESUMED:
            if state.user_speaking or not state.segment_capturing:
                raise ValueError("只有未结束片段中的停顿可以继续讲话。")
            # 恢复讲话同样属于 barge-in。即使独立的 TTS_STOPPED 事件
            # 丢失或晚到，也不能让旧播放占用阻塞本轮后续回复。
            return replace(
                state,
                user_speaking=True,
                tts_playing=False,
                active_tts_priority=None,
            )

        if kind is VoiceRuntimeEventType.SEGMENT_FINALIZED:
            if state.user_speaking or not state.segment_capturing:
                raise ValueError("只有用户停顿后的活动片段可以固化。")
            return replace(state, segment_capturing=False)

        if kind is VoiceRuntimeEventType.ASR_PROCESSING_STARTED:
            if state.segment_capturing or state.asr_processing:
                raise ValueError("ASR 只能处理已固化且尚未处理的片段。")
            return replace(state, asr_processing=True)

        if kind in (
            VoiceRuntimeEventType.ASR_PROCESSING_FINISHED,
            VoiceRuntimeEventType.ASR_PROCESSING_FAILED,
        ):
            if not state.asr_processing:
                raise ValueError("没有正在处理的 ASR 任务。")
            return replace(state, asr_processing=False)

        if kind is VoiceRuntimeEventType.TTS_STARTED:
            if state.tts_playing:
                raise ValueError("已有 TTS 正在播放。")
            return replace(
                state,
                tts_playing=True,
                active_tts_priority=event.tts_priority,
            )

        if kind in (
            VoiceRuntimeEventType.TTS_FINISHED,
            VoiceRuntimeEventType.TTS_STOPPED,
            VoiceRuntimeEventType.TTS_FAILED,
        ):
            if not state.tts_playing:
                raise ValueError("没有正在播放的 TTS。")
            return replace(state, tts_playing=False, active_tts_priority=None)

        raise AssertionError(f"未处理的语音运行事件：{kind!r}")
