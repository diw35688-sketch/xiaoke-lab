"""Explicit-time expiry cleanup for deferred playback requests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

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
class ExpiredPlayback:
    """One removed deferred entry and its permanent drop decision."""

    entry: DeferredPlaybackEntry
    decision: PlaybackDecision


@dataclass(frozen=True)
class ExpirySweep:
    """Immutable evidence returned by one explicit-time queue scan."""

    observed_at: datetime
    expired: tuple[ExpiredPlayback, ...]


def drop_expired(
    queue: DeferredPlaybackQueue,
    *,
    observed_at: datetime,
) -> ExpirySweep:
    """Remove requests whose expiry boundary has been reached.

    The function does not read a clock.  Non-expired entries retain their
    original FIFO order and deferred decisions.
    """

    if not isinstance(queue, DeferredPlaybackQueue):
        raise TypeError("queue 必须是 DeferredPlaybackQueue。")
    if not isinstance(observed_at, datetime):
        raise TypeError("observed_at 必须是 datetime。")
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("observed_at 必须包含时区。")

    pending_count = len(queue.snapshot())
    expired: list[ExpiredPlayback] = []
    for _ in range(pending_count):
        entry = queue.take_next()
        if entry is None:
            break
        if observed_at >= entry.request.expires_at:
            expired.append(ExpiredPlayback(
                entry=entry,
                decision=PlaybackDecision(
                    PlaybackDisposition.DROP,
                    PlaybackReason.EXPIRED,
                ),
            ))
        else:
            queue.defer(entry.request, entry.decision)

    return ExpirySweep(observed_at=observed_at, expired=tuple(expired))
