"""Per-conversation ownership for mutable voice runtime state."""

from __future__ import annotations

from threading import Lock

from src.core.voice_runtime_state import (
    VoiceRuntimeEvent,
    VoiceRuntimeEventType,
    VoiceRuntimeState,
    VoiceStateCoordinator,
)
from src.core.presentation_intent import MessagePriority


class VoiceRuntimeSessionRegistry:
    """Keep one coordinator per conversation instead of one process-global state."""

    def __init__(self) -> None:
        self._coordinators: dict[str, VoiceStateCoordinator] = {}
        self._lock = Lock()

    def snapshot(self, conversation_id: str) -> VoiceRuntimeState | None:
        with self._lock:
            coordinator = self._coordinators.get(conversation_id)
            return coordinator.snapshot() if coordinator is not None else None

    def coordinator(self, conversation_id: str) -> VoiceStateCoordinator:
        """Return the sole coordinator owned by one named conversation."""
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            raise ValueError("conversation_id 不能为空。")
        with self._lock:
            return self._coordinators.setdefault(
                conversation_id, VoiceStateCoordinator()
            )

    def consume(
        self,
        conversation_id: str,
        event_type: VoiceRuntimeEventType,
        *,
        tts_priority: MessagePriority | None = None,
    ) -> tuple[VoiceRuntimeState, bool]:
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            raise ValueError("conversation_id 不能为空。")
        if not isinstance(event_type, VoiceRuntimeEventType):
            raise TypeError("event_type 必须是 VoiceRuntimeEventType。")

        with self._lock:
            coordinator = self._coordinators.setdefault(
                conversation_id, VoiceStateCoordinator()
            )
            current = coordinator.snapshot()
            # Browser VAD implementations do not all distinguish a brand-new
            # segment from speech returning after a short pause.  When the
            # named session still owns an open segment, a repeated "started"
            # fact means "resumed" for the strict core state machine.
            if (
                event_type is VoiceRuntimeEventType.USER_SPEECH_STARTED
                and current.segment_capturing
                and not current.user_speaking
            ):
                event_type = VoiceRuntimeEventType.USER_SPEECH_RESUMED
            # HTTP 请求可能重试；重复上报同一语音事实时不再改写状态。
            if (
                event_type is VoiceRuntimeEventType.USER_SPEECH_STARTED
                and current.user_speaking
            ):
                return current, False
            if (
                event_type is VoiceRuntimeEventType.USER_SPEECH_PAUSED
                and current.segment_capturing
                and not current.user_speaking
            ):
                return current, False
            if (
                event_type is VoiceRuntimeEventType.USER_SPEECH_RESUMED
                and current.segment_capturing
                and current.user_speaking
            ):
                return current, False
            if (
                event_type is VoiceRuntimeEventType.SEGMENT_FINALIZED
                and not current.segment_capturing
            ):
                return current, False
            # 浏览器/手机 VAD 有时漏发 SEGMENT_FINALIZED，ASR 就开始了。
            # 这里把已经停下来的采集片段自动视为“已固化”，避免状态机拒绝。
            if (
                event_type is VoiceRuntimeEventType.ASR_PROCESSING_STARTED
                and current.segment_capturing
                and not current.user_speaking
            ):
                current = coordinator.consume(
                    VoiceRuntimeEvent(VoiceRuntimeEventType.SEGMENT_FINALIZED)
                )
            if (
                event_type is VoiceRuntimeEventType.ASR_PROCESSING_STARTED
                and current.asr_processing
            ):
                return current, False
            if (
                event_type in (
                    VoiceRuntimeEventType.ASR_PROCESSING_FINISHED,
                    VoiceRuntimeEventType.ASR_PROCESSING_FAILED,
                )
                and not current.asr_processing
            ):
                return current, False
            if (
                event_type is VoiceRuntimeEventType.TTS_STARTED
                and current.tts_playing
            ):
                return current, False
            if (
                event_type in (
                    VoiceRuntimeEventType.TTS_FINISHED,
                    VoiceRuntimeEventType.TTS_STOPPED,
                    VoiceRuntimeEventType.TTS_FAILED,
                )
                and not current.tts_playing
            ):
                return current, False
            state = coordinator.consume(
                VoiceRuntimeEvent(event_type, tts_priority=tts_priority)
            )
            return state, True

    def clear(self) -> None:
        """Clear transient state; primarily used to isolate application tests."""
        with self._lock:
            self._coordinators.clear()


voice_runtime_sessions = VoiceRuntimeSessionRegistry()
