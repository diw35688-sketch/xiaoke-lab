"""Replace deferred playback requests that share a supersession context."""

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
from src.core.playback_request import PlaybackRequest


@dataclass(frozen=True)
class SupersededPlayback:
    """One old deferred entry and its permanent superseded decision."""

    entry: DeferredPlaybackEntry
    decision: PlaybackDecision


@dataclass(frozen=True)
class SupersessionResult:
    """The queued replacement and evidence for every removed old entry."""

    replacement: DeferredPlaybackEntry
    superseded: tuple[SupersededPlayback, ...]


def supersede_deferred(
    queue: DeferredPlaybackQueue,
    *,
    replacement: PlaybackRequest,
    decision: PlaybackDecision,
) -> SupersessionResult:
    """Replace all queued requests with the replacement's non-empty key.

    Unrelated entries retain FIFO order.  The replacement is appended at the
    tail and no playback is executed.
    """

    if not isinstance(queue, DeferredPlaybackQueue):
        raise TypeError("queue 必须是 DeferredPlaybackQueue。")

    # Validate the complete replacement before removing any old entry.
    DeferredPlaybackEntry(request=replacement, decision=decision)
    if replacement.supersession_key is None:
        raise ValueError("replacement 必须包含 supersession_key。")

    initial = queue.snapshot()
    if any(entry.request.intent_id == replacement.intent_id for entry in initial):
        raise ValueError(f"intent_id 已在延后队列中：{replacement.intent_id}")

    superseded: list[SupersededPlayback] = []
    for _ in range(len(initial)):
        entry = queue.take_next()
        if entry is None:
            break
        if entry.request.supersession_key == replacement.supersession_key:
            superseded.append(SupersededPlayback(
                entry=entry,
                decision=PlaybackDecision(
                    PlaybackDisposition.DROP,
                    PlaybackReason.SUPERSEDED,
                ),
            ))
        else:
            queue.defer(entry.request, entry.decision)

    replacement_entry = queue.defer(replacement, decision)
    return SupersessionResult(
        replacement=replacement_entry,
        superseded=tuple(superseded),
    )
