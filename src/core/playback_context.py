"""Immutable live-state snapshot used by future playback decisions.

The snapshot reports facts only.  It does not read or control microphones,
ASR, TTS, queues, or session state, and it does not make playback decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from src.core.presentation_intent import MessagePriority


class PlaybackSessionPhase(str, Enum):
    """High-level conversation lifecycle, separate from device activity."""

    INACTIVE = "inactive"
    ACTIVE = "active"
    CLOSING = "closing"
    ENDED = "ended"


@dataclass(frozen=True)
class PlaybackContext:
    """Facts observed together at one instant for deterministic evaluation."""

    observed_at: datetime
    user_speaking: bool
    voice_input_busy: bool
    tts_playing: bool
    session_phase: PlaybackSessionPhase
    active_tts_priority: MessagePriority | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.observed_at, datetime):
            raise TypeError("observed_at 必须是 datetime。")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at 必须包含时区。")
        for name in ("user_speaking", "voice_input_busy", "tts_playing"):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} 必须是 bool。")
        if not isinstance(self.session_phase, PlaybackSessionPhase):
            raise TypeError("session_phase 必须是 PlaybackSessionPhase。")
        if self.active_tts_priority is not None and not isinstance(
            self.active_tts_priority, MessagePriority
        ):
            raise TypeError("active_tts_priority 必须是 MessagePriority 或 None。")
        if not self.tts_playing and self.active_tts_priority is not None:
            raise ValueError("TTS 未播放时不能设置 active_tts_priority。")
