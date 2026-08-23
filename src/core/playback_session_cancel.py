"""Permanent cancellation of deferred playback when a session ends."""

from __future__ import annotations

from dataclasses import dataclass

from src.core.deferred_playback_queue import (
    DeferredPlaybackEntry,
    DeferredPlaybackQueue,
)
from src.core.playback_decision import (
    PlaybackDecision,
    PlaybackDisposition,
    PlaybackReason,
)


@dataclass(frozen=True)
class CancelledPlayback:
    """One drained entry and its permanent session-ended decision."""

    entry: DeferredPlaybackEntry
    decision: PlaybackDecision


@dataclass(frozen=True)
class SessionCancellation:
    """Immutable evidence from permanently closing one deferred queue."""

    cancelled: tuple[CancelledPlayback, ...]


def cancel_deferred_for_session(
    queue: DeferredPlaybackQueue,
) -> SessionCancellation:
    """Close and drain a session queue without executing playback."""

    if not isinstance(queue, DeferredPlaybackQueue):
        raise TypeError("queue 必须是 DeferredPlaybackQueue。")

    drained = queue.close()
    return SessionCancellation(cancelled=tuple(
        CancelledPlayback(
            entry=entry,
            decision=PlaybackDecision(
                PlaybackDisposition.DROP,
                PlaybackReason.SESSION_ENDED,
            ),
        )
        for entry in drained
    ))
