"""Pure priority and timing rules for voice playback eligibility."""

from __future__ import annotations

from src.core.playback_context import PlaybackContext, PlaybackSessionPhase
from src.core.playback_decision import (
    PlaybackDecision,
    PlaybackDisposition,
    PlaybackReason,
)
from src.core.playback_request import PlaybackRequest
from src.core.presentation_intent import MessagePriority


def decide_playback(
    request: PlaybackRequest,
    context: PlaybackContext,
) -> PlaybackDecision:
    """Return a deterministic decision without reading clocks or changing state."""

    if not isinstance(request, PlaybackRequest):
        raise TypeError("request 必须是 PlaybackRequest。")
    if not isinstance(context, PlaybackContext):
        raise TypeError("context 必须是 PlaybackContext。")

    if context.session_phase == PlaybackSessionPhase.ENDED:
        return _decision(PlaybackDisposition.DROP, PlaybackReason.SESSION_ENDED)
    if context.observed_at >= request.expires_at:
        return _decision(PlaybackDisposition.DROP, PlaybackReason.EXPIRED)
    if request.priority in (MessagePriority.ROUTINE, MessagePriority.DEBUG):
        return _decision(PlaybackDisposition.DROP, PlaybackReason.CONTEXT_LOST)

    if context.session_phase == PlaybackSessionPhase.INACTIVE:
        return _decision(
            PlaybackDisposition.DEFERRED,
            PlaybackReason.SESSION_NOT_ACTIVE,
        )
    if (
        context.session_phase == PlaybackSessionPhase.CLOSING
        and request.priority not in (
            MessagePriority.CRITICAL,
            MessagePriority.SUMMARY,
        )
    ):
        return _decision(
            PlaybackDisposition.DEFERRED,
            PlaybackReason.SESSION_NOT_ACTIVE,
        )

    if request.priority != MessagePriority.CRITICAL:
        if context.user_speaking:
            return _decision(
                PlaybackDisposition.DEFERRED,
                PlaybackReason.USER_SPEAKING,
            )
        if context.voice_input_busy:
            return _decision(
                PlaybackDisposition.DEFERRED,
                PlaybackReason.VOICE_INPUT_BUSY,
            )

    if context.tts_playing:
        if (
            request.priority == MessagePriority.CRITICAL
            and context.active_tts_priority is not None
            and context.active_tts_priority > MessagePriority.CRITICAL
        ):
            return _decision(
                PlaybackDisposition.PREEMPT,
                PlaybackReason.CRITICAL_OVER_LOWER_PRIORITY,
            )
        return _decision(PlaybackDisposition.DEFERRED, PlaybackReason.TTS_BUSY)

    return _decision(
        PlaybackDisposition.READY,
        PlaybackReason.PLAYBACK_WINDOW_OPEN,
    )


def _decision(
    disposition: PlaybackDisposition,
    reason: PlaybackReason,
) -> PlaybackDecision:
    return PlaybackDecision(disposition, reason)
