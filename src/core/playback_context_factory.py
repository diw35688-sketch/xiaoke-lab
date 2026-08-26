"""Create immutable playback snapshots from coordinated runtime facts."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from src.core.playback_context import PlaybackContext, PlaybackSessionPhase
from src.core.voice_runtime_state import VoiceStateCoordinator


class PlaybackContextFactory:
    """Read runtime facts once and copy them into a decision snapshot."""

    def __init__(
        self,
        coordinator: VoiceStateCoordinator,
        clock: Callable[[], datetime],
    ) -> None:
        if not isinstance(coordinator, VoiceStateCoordinator):
            raise TypeError("coordinator 必须是 VoiceStateCoordinator。")
        if not callable(clock):
            raise TypeError("clock 必须是可调用对象。")
        self._coordinator = coordinator
        self._clock = clock

    def create(self, *, session_phase: PlaybackSessionPhase) -> PlaybackContext:
        if not isinstance(session_phase, PlaybackSessionPhase):
            raise TypeError("session_phase 必须是 PlaybackSessionPhase。")

        state = self._coordinator.snapshot()
        observed_at = self._clock()
        return PlaybackContext(
            observed_at=observed_at,
            user_speaking=state.user_speaking,
            voice_input_busy=state.segment_capturing or state.asr_processing,
            tts_playing=state.tts_playing,
            session_phase=session_phase,
            active_tts_priority=state.active_tts_priority,
        )
