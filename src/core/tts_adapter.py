"""TTS execution adapter with traceable lifecycle event reporting."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Protocol, runtime_checkable

from src.core.playback_request import PlaybackRequest
from src.core.presentation_intent import MessagePriority
from src.core.tts_failure_boundary import TTSFailureBoundary, TTSFailureStage
from src.core.voice_runtime_state import (
    VoiceRuntimeEvent,
    VoiceRuntimeEventType,
    VoiceStateCoordinator,
)


class TTSExecutionEventType(str, Enum):
    STARTED = "started"
    FINISHED = "finished"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True)
class TTSExecutionEvent:
    event_type: TTSExecutionEventType
    intent_id: str
    priority: MessagePriority
    error: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.event_type, TTSExecutionEventType):
            raise TypeError("event_type 必须是 TTSExecutionEventType。")
        if not isinstance(self.intent_id, str) or not self.intent_id.strip():
            raise ValueError("intent_id 不能为空。")
        if not isinstance(self.priority, MessagePriority):
            raise TypeError("priority 必须是 MessagePriority。")
        if self.event_type is TTSExecutionEventType.FAILED:
            if not isinstance(self.error, str) or not self.error.strip():
                raise ValueError("FAILED 事件必须携带非空 error。")
        elif self.error is not None:
            raise ValueError("只有 FAILED 事件可以携带 error。")


@runtime_checkable
class TTSDriver(Protocol):
    """Low-level player contract; concrete browser/provider wiring comes later."""

    def play(
        self,
        request: PlaybackRequest,
        report: Callable[[TTSExecutionEventType, str | None], None],
    ) -> None: ...

    def stop(self) -> None: ...


class TTSAdapter:
    """Execute play/stop and translate driver signals into runtime facts."""

    def __init__(
        self,
        driver: TTSDriver,
        coordinator: VoiceStateCoordinator,
        event_sink: Callable[[TTSExecutionEvent], None],
        failure_boundary: TTSFailureBoundary | None = None,
    ) -> None:
        if not isinstance(driver, TTSDriver):
            raise TypeError("driver 必须实现 TTSDriver。")
        if not isinstance(coordinator, VoiceStateCoordinator):
            raise TypeError("coordinator 必须是 VoiceStateCoordinator。")
        if not callable(event_sink):
            raise TypeError("event_sink 必须是可调用对象。")
        self._driver = driver
        self._coordinator = coordinator
        self._event_sink = event_sink
        if failure_boundary is not None and not isinstance(
            failure_boundary, TTSFailureBoundary
        ):
            raise TypeError("failure_boundary 必须是 TTSFailureBoundary 或 None。")
        self._failure_boundary = failure_boundary or TTSFailureBoundary()
        self._pending: PlaybackRequest | None = None
        self._active: PlaybackRequest | None = None
        self._lock = Lock()

    def play(self, request: PlaybackRequest) -> None:
        if not isinstance(request, PlaybackRequest):
            raise TypeError("request 必须是 PlaybackRequest。")
        with self._lock:
            if self._pending is not None or self._active is not None:
                raise RuntimeError("TTSAdapter 已有待启动或正在播放的请求。")
            self._pending = request
        try:
            self._driver.play(request, self._handle_driver_signal)
        except Exception:
            with self._lock:
                if self._pending is request:
                    self._pending = None
            raise

    def stop(self) -> None:
        with self._lock:
            if self._active is None:
                raise RuntimeError("没有已 STARTED 的 TTS 可以停止。")
        self._driver.stop()

    def _handle_driver_signal(
        self,
        signal: TTSExecutionEventType,
        error: str | None = None,
    ) -> None:
        if not isinstance(signal, TTSExecutionEventType):
            raise TypeError("driver signal 必须是 TTSExecutionEventType。")

        with self._lock:
            if signal is TTSExecutionEventType.STARTED:
                if self._pending is None or self._active is not None:
                    raise RuntimeError("STARTED 与当前 TTS 请求状态不一致。")
                request = self._pending
                event = TTSExecutionEvent(
                    signal, request.intent_id, request.priority, error
                )
                self._coordinator.consume(
                    VoiceRuntimeEvent(
                        VoiceRuntimeEventType.TTS_STARTED,
                        tts_priority=request.priority,
                    )
                )
                self._active = request
                self._pending = None
            else:
                if self._active is None:
                    raise RuntimeError(
                        f"{signal.value.upper()} 之前没有 STARTED。"
                    )
                request = self._active
                event = TTSExecutionEvent(
                    signal, request.intent_id, request.priority, error
                )
                runtime_type = {
                    TTSExecutionEventType.FINISHED:
                        VoiceRuntimeEventType.TTS_FINISHED,
                    TTSExecutionEventType.STOPPED:
                        VoiceRuntimeEventType.TTS_STOPPED,
                    TTSExecutionEventType.FAILED:
                        VoiceRuntimeEventType.TTS_FAILED,
                }[signal]
                self._coordinator.consume(VoiceRuntimeEvent(runtime_type))
                self._active = None

        try:
            self._event_sink(event)
        except Exception as exc:
            self._failure_boundary.record(
                intent_id=event.intent_id,
                stage=TTSFailureStage.EVENT_DELIVERY,
                error=str(exc).strip() or type(exc).__name__,
            )
