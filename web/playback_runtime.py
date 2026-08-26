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
from threading import Lock

from src.core.deferred_playback_queue import DeferredPlaybackQueue
from src.core.playback_context import PlaybackSessionPhase
from src.core.playback_context_factory import PlaybackContextFactory
from src.core.playback_decision import PlaybackDisposition
from src.core.playback_gate import PlaybackGate
from src.core.playback_request import PlaybackRequest
from src.core.playback_reevaluation import ReevaluationTrigger
from src.core.playback_scheduler import PlaybackScheduleAction, PlaybackScheduler
from src.core.presentation_delivery import VoiceDeliveryItem
from src.core.tts_adapter import TTSExecutionEvent
from src.core.voice_runtime_state import VoiceStateCoordinator
from stream_contract import voice_delivery_event
from voice_runtime_sessions import VoiceRuntimeSessionRegistry, voice_runtime_sessions


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

    @staticmethod
    def _item_from_request(request: PlaybackRequest) -> VoiceDeliveryItem:
        return VoiceDeliveryItem(
            request.intent_id,
            request.kind,
            request.priority,
            request.voice_text,
            request.source_block_id,
            request.max_chars,
            request.speech_rate,
        )

    def _event_from_result(self, result) -> dict:
        authorization = result.decision.disposition.value.upper()
        reason = result.decision.reason.value
        if result.action is PlaybackScheduleAction.PLAYBACK_FAILED:
            authorization = PlaybackDisposition.DROP.value.upper()
            reason = "playback_handoff_failed"
        elif result.action is PlaybackScheduleAction.PREEMPT_STOP_REQUESTED:
            authorization = PlaybackDisposition.DEFERRED.value.upper()
            reason = "preempt_feedback_pending"
        return voice_delivery_event(
            (self._item_from_request(result.request),),
            authorization=authorization,
            reason=reason,
        )

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
            events.append(self._event_from_result(result))
        return tuple(events)

    def reevaluate(
        self,
        trigger: ReevaluationTrigger,
        *,
        session_phase: PlaybackSessionPhase = PlaybackSessionPhase.ACTIVE,
    ) -> tuple[dict, ...]:
        return tuple(
            self._event_from_result(result)
            for result in self._scheduler.reevaluate(
                trigger, session_phase=session_phase
            )
        )

    def handle_tts_event(
        self,
        event: TTSExecutionEvent,
        *,
        session_phase: PlaybackSessionPhase = PlaybackSessionPhase.ACTIVE,
    ) -> tuple[dict, ...]:
        result = self._scheduler.handle_tts_event(
            event, session_phase=session_phase
        )
        return () if result is None else (self._event_from_result(result),)


class ConversationPlaybackRegistry:
    """Own one scheduler/queue per conversation and share its coordinator."""

    def __init__(
        self,
        runtime_sessions: VoiceRuntimeSessionRegistry,
        *,
        clock: Callable[[], datetime],
        ttl: timedelta = DEFAULT_PLAYBACK_TTL,
    ) -> None:
        self._runtime_sessions = runtime_sessions
        self._clock = clock
        self._ttl = ttl
        self._services: dict[str, WebPlaybackService] = {}
        self._lock = Lock()

    def for_conversation(self, conversation_id: str) -> WebPlaybackService:
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            raise ValueError("conversation_id 不能为空。")
        with self._lock:
            service = self._services.get(conversation_id)
            if service is None:
                coordinator = self._runtime_sessions.coordinator(conversation_id)
                service = WebPlaybackService(
                    PlaybackScheduler(
                        PlaybackContextFactory(coordinator, self._clock),
                        PlaybackGate(),
                        DeferredPlaybackQueue(),
                        BrowserPlaybackExecutionPort(),
                    ),
                    clock=self._clock,
                    ttl=self._ttl,
                )
                self._services[conversation_id] = service
            return service

    def authorize(self, items, *, conversation_id: str) -> tuple[dict, ...]:
        return self.for_conversation(conversation_id).authorize(items)

    def reevaluate(
        self, conversation_id: str, trigger: ReevaluationTrigger
    ) -> tuple[dict, ...]:
        return self.for_conversation(conversation_id).reevaluate(trigger)

    def handle_tts_event(
        self, conversation_id: str, event: TTSExecutionEvent
    ) -> tuple[dict, ...]:
        return self.for_conversation(conversation_id).handle_tts_event(event)

    def clear(self) -> None:
        with self._lock:
            self._services.clear()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


_clock = _utc_now
web_playback_service = ConversationPlaybackRegistry(
    voice_runtime_sessions,
    clock=_clock,
)
