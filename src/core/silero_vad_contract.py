"""Runtime-independent contract for a future call-mode Silero VAD adapter.

This module deliberately contains no model loading, microphone access, RMS
implementation, or mutable voice state.  An adapter consumes normalized audio
frames and reports semantic speech-boundary events.  The existing
``VoiceStateCoordinator`` remains the sole owner of runtime state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Protocol, runtime_checkable

from src.core.voice_runtime_state import VoiceRuntimeEvent, VoiceRuntimeEventType


SILERO_SAMPLE_RATE = 16_000
SILERO_FRAME_SAMPLES = 512


class SileroVadEventType(str, Enum):
    SPEECH_STARTED = "speech_started"
    SPEECH_PAUSED = "speech_paused"
    SPEECH_RESUMED = "speech_resumed"
    SEGMENT_FINALIZED = "segment_finalized"


class SileroVadFailureCode(str, Enum):
    RUNTIME_UNAVAILABLE = "runtime_unavailable"
    MODEL_LOAD_FAILED = "model_load_failed"
    INFERENCE_FAILED = "inference_failed"
    INVALID_OUTPUT = "invalid_output"


class SileroVadFallback(str, Enum):
    USE_RMS = "use_rms"


@dataclass(frozen=True)
class SileroVadFrame:
    """One normalized mono Float32-equivalent frame for Silero inference."""

    sequence: int
    captured_at: float
    samples: tuple[float, ...]
    sample_rate: int = SILERO_SAMPLE_RATE

    def __post_init__(self) -> None:
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("sequence 必须是非负整数。")
        if isinstance(self.captured_at, bool) or not isinstance(
            self.captured_at, (int, float)
        ):
            raise TypeError("captured_at 必须是单调时钟秒数。")
        if not isfinite(float(self.captured_at)) or self.captured_at < 0:
            raise ValueError("captured_at 必须是有限的非负数。")
        if type(self.sample_rate) is not int or self.sample_rate != SILERO_SAMPLE_RATE:
            raise ValueError(f"sample_rate 必须固定为 {SILERO_SAMPLE_RATE} Hz。")
        if not isinstance(self.samples, tuple):
            raise TypeError("samples 必须是不可变 tuple。")
        if len(self.samples) != SILERO_FRAME_SAMPLES:
            raise ValueError(f"samples 必须恰好包含 {SILERO_FRAME_SAMPLES} 个采样。")
        for sample in self.samples:
            if isinstance(sample, bool) or not isinstance(sample, (int, float)):
                raise TypeError("每个 sample 必须是浮点数。")
            if not isfinite(float(sample)) or not -1.0 <= sample <= 1.0:
                raise ValueError("每个 sample 必须是 [-1.0, 1.0] 内的有限值。")


@dataclass(frozen=True)
class SileroVadEvent:
    event_type: SileroVadEventType
    occurred_at: float

    def __post_init__(self) -> None:
        if not isinstance(self.event_type, SileroVadEventType):
            raise TypeError("event_type 必须是 SileroVadEventType。")
        if isinstance(self.occurred_at, bool) or not isinstance(
            self.occurred_at, (int, float)
        ):
            raise TypeError("occurred_at 必须是单调时钟秒数。")
        if not isfinite(float(self.occurred_at)) or self.occurred_at < 0:
            raise ValueError("occurred_at 必须是有限的非负数。")


@dataclass(frozen=True)
class SileroVadFailure:
    code: SileroVadFailureCode
    detail: str
    fallback: SileroVadFallback = SileroVadFallback.USE_RMS

    def __post_init__(self) -> None:
        if not isinstance(self.code, SileroVadFailureCode):
            raise TypeError("code 必须是 SileroVadFailureCode。")
        if not isinstance(self.detail, str) or not self.detail.strip():
            raise ValueError("detail 必须是非空字符串。")
        if not isinstance(self.fallback, SileroVadFallback):
            raise TypeError("fallback 必须是 SileroVadFallback。")


@dataclass(frozen=True)
class SileroVadResult:
    """Exactly one outcome: semantic events or an explicit RMS fallback."""

    events: tuple[SileroVadEvent, ...] = ()
    failure: SileroVadFailure | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.events, tuple) or any(
            not isinstance(event, SileroVadEvent) for event in self.events
        ):
            raise TypeError("events 必须是 SileroVadEvent 的 tuple。")
        if self.failure is not None and not isinstance(self.failure, SileroVadFailure):
            raise TypeError("failure 必须是 SileroVadFailure 或 None。")
        if self.failure is not None and self.events:
            raise ValueError("失败结果不能同时携带语音边界事件。")


_COORDINATOR_EVENT_MAP = {
    SileroVadEventType.SPEECH_STARTED: VoiceRuntimeEventType.USER_SPEECH_STARTED,
    SileroVadEventType.SPEECH_PAUSED: VoiceRuntimeEventType.USER_SPEECH_PAUSED,
    SileroVadEventType.SPEECH_RESUMED: VoiceRuntimeEventType.USER_SPEECH_RESUMED,
    SileroVadEventType.SEGMENT_FINALIZED: VoiceRuntimeEventType.SEGMENT_FINALIZED,
}


def to_voice_runtime_event(event: SileroVadEvent) -> VoiceRuntimeEvent:
    """Map a VAD fact to Coordinator input without mutating the Coordinator."""

    if not isinstance(event, SileroVadEvent):
        raise TypeError("event 必须是 SileroVadEvent。")
    return VoiceRuntimeEvent(event_type=_COORDINATOR_EVENT_MAP[event.event_type])


@runtime_checkable
class SileroVadAdapter(Protocol):
    """Port implemented in C4-2; C4-1 defines only this callable surface."""

    def accept(self, frame: SileroVadFrame) -> SileroVadResult:
        """Consume one ordered frame and return zero or more boundary events."""

    def reset(self) -> None:
        """Forget detector-local segment state without touching runtime state."""
