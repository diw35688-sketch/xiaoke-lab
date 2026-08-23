"""Thread-safe storage for playback requests already decided as deferred."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import Lock

from src.core.playback_decision import PlaybackDecision, PlaybackDisposition
from src.core.playback_request import PlaybackRequest


@dataclass(frozen=True)
class DeferredPlaybackEntry:
    """A request retained together with the decision that deferred it."""

    request: PlaybackRequest
    decision: PlaybackDecision

    def __post_init__(self) -> None:
        if not isinstance(self.request, PlaybackRequest):
            raise TypeError("request 必须是 PlaybackRequest。")
        if not isinstance(self.decision, PlaybackDecision):
            raise TypeError("decision 必须是 PlaybackDecision。")
        if self.decision.disposition != PlaybackDisposition.DEFERRED:
            raise ValueError("延后队列只接受 DEFERRED 决定。")


class DeferredPlaybackQueue:
    """FIFO queue that stores deferred entries but never plays them."""

    def __init__(self) -> None:
        self._entries: deque[DeferredPlaybackEntry] = deque()
        self._intent_ids: set[str] = set()
        self._closed = False
        self._lock = Lock()

    def defer(
        self,
        request: PlaybackRequest,
        decision: PlaybackDecision,
    ) -> DeferredPlaybackEntry:
        """Store one deferred request without evaluating or playing it."""

        entry = DeferredPlaybackEntry(request=request, decision=decision)
        with self._lock:
            if self._closed:
                raise RuntimeError("延后队列已关闭，不能再加入请求。")
            if request.intent_id in self._intent_ids:
                raise ValueError(f"intent_id 已在延后队列中：{request.intent_id}")
            self._entries.append(entry)
            self._intent_ids.add(request.intent_id)
        return entry

    def snapshot(self) -> tuple[DeferredPlaybackEntry, ...]:
        """Return an immutable FIFO snapshot without removing entries."""

        with self._lock:
            return tuple(self._entries)

    def take_next(self) -> DeferredPlaybackEntry | None:
        """Remove and return the oldest entry, or None when the queue is empty."""

        with self._lock:
            if not self._entries:
                return None
            entry = self._entries.popleft()
            self._intent_ids.remove(entry.request.intent_id)
            return entry

    def close(self) -> tuple[DeferredPlaybackEntry, ...]:
        """Permanently close the queue and atomically drain existing entries."""

        with self._lock:
            self._closed = True
            drained = tuple(self._entries)
            self._entries.clear()
            self._intent_ids.clear()
            return drained

    @property
    def is_closed(self) -> bool:
        with self._lock:
            return self._closed

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)
