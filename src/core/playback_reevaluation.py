"""Explicit state-change triggers for reevaluating deferred playback."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.core.deferred_playback_queue import (
    DeferredPlaybackEntry,
    DeferredPlaybackQueue,
)
from src.core.playback_context import PlaybackContext
from src.core.playback_decision import PlaybackDecision, PlaybackDisposition
from src.core.playback_gate import PlaybackGate


class ReevaluationTrigger(str, Enum):
    """State transitions that may open a playback window."""

    USER_STOPPED_SPEAKING = "user_stopped_speaking"
    VOICE_INPUT_BECAME_IDLE = "voice_input_became_idle"
    TTS_PLAYBACK_ENDED = "tts_playback_ended"


@dataclass(frozen=True)
class ReevaluationOutcome:
    """The old deferred entry and its decision under the new snapshot."""

    entry: DeferredPlaybackEntry
    decision: PlaybackDecision


@dataclass(frozen=True)
class ReevaluationBatch:
    """Immutable results from one explicit state-change trigger."""

    trigger: ReevaluationTrigger
    outcomes: tuple[ReevaluationOutcome, ...]


def reevaluate_deferred(
    queue: DeferredPlaybackQueue,
    *,
    trigger: ReevaluationTrigger,
    context: PlaybackContext,
) -> ReevaluationBatch:
    """Reevaluate the entries present when this trigger begins.

    Entries that remain DEFERRED are put back at the tail.  Other outcomes are
    returned to the caller and are not executed here.
    """

    if not isinstance(queue, DeferredPlaybackQueue):
        raise TypeError("queue 必须是 DeferredPlaybackQueue。")
    if not isinstance(trigger, ReevaluationTrigger):
        raise TypeError("trigger 必须是 ReevaluationTrigger。")
    if not isinstance(context, PlaybackContext):
        raise TypeError("context 必须是 PlaybackContext。")
    _validate_transition(trigger, context)

    pending_count = len(queue.snapshot())
    outcomes: list[ReevaluationOutcome] = []
    for _ in range(pending_count):
        entry = queue.take_next()
        if entry is None:
            break
        try:
            decision = PlaybackGate.evaluate(entry.request, context)
        except Exception:
            queue.defer(entry.request, entry.decision)
            raise
        outcomes.append(ReevaluationOutcome(entry=entry, decision=decision))
        if decision.disposition == PlaybackDisposition.DEFERRED:
            queue.defer(entry.request, decision)

    return ReevaluationBatch(trigger=trigger, outcomes=tuple(outcomes))


def _validate_transition(
    trigger: ReevaluationTrigger,
    context: PlaybackContext,
) -> None:
    if (
        trigger == ReevaluationTrigger.USER_STOPPED_SPEAKING
        and context.user_speaking
    ):
        raise ValueError("用户停止讲话触发器要求 user_speaking=False。")
    if (
        trigger == ReevaluationTrigger.VOICE_INPUT_BECAME_IDLE
        and context.voice_input_busy
    ):
        raise ValueError("语音输入空闲触发器要求 voice_input_busy=False。")
    if (
        trigger == ReevaluationTrigger.TTS_PLAYBACK_ENDED
        and context.tts_playing
    ):
        raise ValueError("TTS 结束触发器要求 tts_playing=False。")
