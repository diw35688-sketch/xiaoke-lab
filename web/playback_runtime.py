# -*- coding: utf-8 -*-
"""Web adapter that routes voice-qualified items through PlaybackScheduler.

The browser remains the physical TTS executor.  This module is the server-side
authorization boundary: it turns content-qualified items into PlaybackRequest
objects, asks the shared scheduler once, and returns wire events describing the
decision.  Producers such as /record and chat tools never call browser TTS.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timedelta, timezone

from src.core.deferred_playback_queue import DeferredPlaybackQueue
from src.core.playback_context import PlaybackSessionPhase
from src.core.playback_context_factory import PlaybackContextFactory
from src.core.playback_decision import PlaybackDisposition
from src.core.playback_gate import PlaybackGate
from src.core.playback_request import PlaybackRequest
from src.core.playback_scheduler import PlaybackScheduleAction, PlaybackScheduler
from src.core.presentation_delivery import VoiceDeliveryItem
from src.core.voice_runtime_state import VoiceStateCoordinator
from stream_contract import voice_delivery_event


DEFAULT_PLAYBACK_TTL = timedelta(seconds=20)


class BrowserPlaybackExecutionPort:
    """Scheduler execution port whose physical hand-off is an HTTP/SSE event.

    ``play`` deliberately performs no local audio operation.  A successful
    return tells PlaybackScheduler that the request can be serialized as a
    READY event by WebPlaybackService.
    """

    def play(self, request: PlaybackRequest) -> None:
        if not isinstance(request, PlaybackRequest):
            raise TypeError("request 必须是 PlaybackRequest。")

    def stop(self) -> None:
        """Browser stop feedback is not connected until the real TTS loop."""


class WebPlaybackService:
    """One adapter shared by every Web producer that owns voice candidates."""

    def __init__(
        self,
        scheduler: PlaybackScheduler,
        *,
        clock: Callable[[], datetime],
        ttl: timedelta = DEFAULT_PLAYBACK_TTL,
    ) -> None:
        if not isinstance(scheduler, PlaybackScheduler):
            raise TypeError("scheduler 必须是 PlaybackScheduler。")
        if not callable(clock):
            raise TypeError("clock 必须是可调用对象。")
        if not isinstance(ttl, timedelta) or ttl <= timedelta(0):
            raise ValueError("ttl 必须是大于 0 的 timedelta。")
        self._scheduler = scheduler
        self._clock = clock
        self._ttl = ttl

    def authorize(
        self,
        items: Iterable[VoiceDeliveryItem],
        *,
        session_phase: PlaybackSessionPhase = PlaybackSessionPhase.ACTIVE,
    ) -> tuple[dict, ...]:
        """Return one scheduler-owned authorization event per candidate."""

        events = []
        for item in tuple(items):
            if not isinstance(item, VoiceDeliveryItem):
                raise TypeError("items 只能包含 VoiceDeliveryItem。")
            request = PlaybackRequest.from_delivery_item(
                item,
                created_at=self._clock(),
                ttl=self._ttl,
            )
            result = self._scheduler.schedule(
                request,
                session_phase=session_phase,
            )
            authorization = result.decision.disposition.value.upper()
            reason = result.decision.reason.value
            if result.action is PlaybackScheduleAction.PLAYBACK_FAILED:
                authorization = PlaybackDisposition.DROP.value.upper()
                reason = "playback_handoff_failed"
            elif result.action is PlaybackScheduleAction.PREEMPT_STOP_REQUESTED:
                # The new item must wait for a matching browser STOPPED fact.
                # Until that feedback channel exists, never tell the browser to
                # stop and immediately play the replacement item.
                authorization = PlaybackDisposition.DEFERRED.value.upper()
                reason = "preempt_feedback_pending"
            events.append(
                voice_delivery_event(
                    (item,),
                    authorization=authorization,
                    reason=reason,
                )
            )
        return tuple(events)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


_coordinator = VoiceStateCoordinator()
_clock = _utc_now
_scheduler = PlaybackScheduler(
    PlaybackContextFactory(_coordinator, _clock),
    PlaybackGate(),
    DeferredPlaybackQueue(),
    BrowserPlaybackExecutionPort(),
)
web_playback_service = WebPlaybackService(_scheduler, clock=_clock)
