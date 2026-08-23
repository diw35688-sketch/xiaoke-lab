"""Result contract for playback evaluation, without evaluation rules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PlaybackDisposition(str, Enum):
    """Mutually exclusive outcomes of a future playback evaluation."""

    READY = "ready"
    DEFERRED = "deferred"
    DROP = "drop"
    PREEMPT = "preempt"


class PlaybackReason(str, Enum):
    """Stable machine-readable explanations grouped by disposition."""

    PLAYBACK_WINDOW_OPEN = "playback_window_open"

    USER_SPEAKING = "user_speaking"
    VOICE_INPUT_BUSY = "voice_input_busy"
    TTS_BUSY = "tts_busy"
    SESSION_NOT_ACTIVE = "session_not_active"

    EXPIRED = "expired"
    SUPERSEDED = "superseded"
    SESSION_ENDED = "session_ended"
    CONTEXT_LOST = "context_lost"

    CRITICAL_OVER_LOWER_PRIORITY = "critical_over_lower_priority"


_REASONS_BY_DISPOSITION = {
    PlaybackDisposition.READY: frozenset({
        PlaybackReason.PLAYBACK_WINDOW_OPEN,
    }),
    PlaybackDisposition.DEFERRED: frozenset({
        PlaybackReason.USER_SPEAKING,
        PlaybackReason.VOICE_INPUT_BUSY,
        PlaybackReason.TTS_BUSY,
        PlaybackReason.SESSION_NOT_ACTIVE,
    }),
    PlaybackDisposition.DROP: frozenset({
        PlaybackReason.EXPIRED,
        PlaybackReason.SUPERSEDED,
        PlaybackReason.SESSION_ENDED,
        PlaybackReason.CONTEXT_LOST,
    }),
    PlaybackDisposition.PREEMPT: frozenset({
        PlaybackReason.CRITICAL_OVER_LOWER_PRIORITY,
    }),
}


@dataclass(frozen=True)
class PlaybackDecision:
    """One validated outcome and its stable reason code."""

    disposition: PlaybackDisposition
    reason: PlaybackReason

    def __post_init__(self) -> None:
        if not isinstance(self.disposition, PlaybackDisposition):
            raise TypeError("disposition 必须是 PlaybackDisposition。")
        if not isinstance(self.reason, PlaybackReason):
            raise TypeError("reason 必须是 PlaybackReason。")
        if self.reason not in _REASONS_BY_DISPOSITION[self.disposition]:
            raise ValueError(
                f"原因 {self.reason.value} 不属于决定 {self.disposition.value}。"
            )

    def as_dict(self) -> dict[str, str]:
        """Return the stable wire representation for future adapters."""

        return {
            "disposition": self.disposition.value,
            "reason": self.reason.value,
        }
