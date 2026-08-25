"""Single orchestration boundary for playback decisions and their effects."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Protocol, runtime_checkable

from src.core.deferred_playback_queue import (
    DeferredPlaybackEntry,
    DeferredPlaybackQueue,
)
from src.core.playback_context import PlaybackContext, PlaybackSessionPhase
from src.core.playback_context_factory import PlaybackContextFactory
from src.core.playback_decision import PlaybackDecision, PlaybackDisposition
from src.core.playback_gate import PlaybackGate
from src.core.playback_request import PlaybackRequest
from src.core.playback_reevaluation import ReevaluationTrigger, reevaluate_deferred
from src.core.tts_adapter import TTSExecutionEvent, TTSExecutionEventType
from src.core.tts_failure_boundary import (
    TTSFailureBoundary,
    TTSFailureRecord,
    TTSFailureStage,
)


@runtime_checkable
class PlaybackExecutionPort(Protocol):
    """Playback commands required by the scheduler."""

    def play(self, request: PlaybackRequest) -> None: ...

    def stop(self) -> None: ...


class PlaybackScheduleAction(str, Enum):
    HANDED_TO_TTS = "handed_to_tts"
    QUEUED = "queued"
    DROPPED = "dropped"
    PREEMPT_STOP_REQUESTED = "preempt_stop_requested"
    PLAYBACK_FAILED = "playback_failed"


@dataclass(frozen=True)
class PlaybackScheduleResult:
    request: PlaybackRequest
    context: PlaybackContext
    decision: PlaybackDecision
    action: PlaybackScheduleAction
    deferred_entry: DeferredPlaybackEntry | None = None
    failure: TTSFailureRecord | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.request, PlaybackRequest):
            raise TypeError("request 必须是 PlaybackRequest。")
        if not isinstance(self.context, PlaybackContext):
            raise TypeError("context 必须是 PlaybackContext。")
        if not isinstance(self.decision, PlaybackDecision):
            raise TypeError("decision 必须是 PlaybackDecision。")
        if not isinstance(self.action, PlaybackScheduleAction):
            raise TypeError("action 必须是 PlaybackScheduleAction。")

        expected_actions = {
            PlaybackDisposition.READY: frozenset({
                PlaybackScheduleAction.HANDED_TO_TTS,
                PlaybackScheduleAction.PLAYBACK_FAILED,
            }),
            PlaybackDisposition.DEFERRED: PlaybackScheduleAction.QUEUED,
            PlaybackDisposition.DROP: PlaybackScheduleAction.DROPPED,
            PlaybackDisposition.PREEMPT:
                PlaybackScheduleAction.PREEMPT_STOP_REQUESTED,
        }[self.decision.disposition]
        if not isinstance(expected_actions, frozenset):
            expected_actions = frozenset({expected_actions})
        if self.action not in expected_actions:
            raise ValueError("action 必须与 playback decision 一致。")
        if self.action is PlaybackScheduleAction.QUEUED:
            if self.deferred_entry is None:
                raise ValueError("QUEUED 结果必须携带 deferred_entry。")
            if self.deferred_entry.request != self.request:
                raise ValueError("deferred_entry 必须属于当前 request。")
        elif self.deferred_entry is not None:
            raise ValueError("只有 QUEUED 结果可以携带 deferred_entry。")
        if self.action is PlaybackScheduleAction.PLAYBACK_FAILED:
            if self.failure is None:
                raise ValueError("PLAYBACK_FAILED 必须携带 failure。")
            if self.failure.intent_id != self.request.intent_id:
                raise ValueError("failure 必须属于当前 request。")
        elif self.failure is not None:
            raise ValueError("只有 PLAYBACK_FAILED 可以携带 failure。")


class PlaybackScheduler:
    """Create context, evaluate once, then execute exactly one outcome path."""

    def __init__(
        self,
        context_factory: PlaybackContextFactory,
        gate: PlaybackGate,
        deferred_queue: DeferredPlaybackQueue,
        execution_port: PlaybackExecutionPort,
        failure_boundary: TTSFailureBoundary | None = None,
    ) -> None:
        if not isinstance(context_factory, PlaybackContextFactory):
            raise TypeError("context_factory 必须是 PlaybackContextFactory。")
        if not isinstance(gate, PlaybackGate):
            raise TypeError("gate 必须是 PlaybackGate。")
        if not isinstance(deferred_queue, DeferredPlaybackQueue):
            raise TypeError("deferred_queue 必须是 DeferredPlaybackQueue。")
        if not isinstance(execution_port, PlaybackExecutionPort):
            raise TypeError("execution_port 必须实现 PlaybackExecutionPort。")
        self._context_factory = context_factory
        self._gate = gate
        self._deferred_queue = deferred_queue
        self._execution_port = execution_port
        if failure_boundary is not None and not isinstance(
            failure_boundary, TTSFailureBoundary
        ):
            raise TypeError("failure_boundary 必须是 TTSFailureBoundary 或 None。")
        self._failure_boundary = failure_boundary or TTSFailureBoundary()
        self._active_tts_intent_id: str | None = None
        self._pending_preemption: _PendingPreemption | None = None
        self._lock = Lock()

    def schedule(
        self,
        request: PlaybackRequest,
        *,
        session_phase: PlaybackSessionPhase,
    ) -> PlaybackScheduleResult:
        if not isinstance(request, PlaybackRequest):
            raise TypeError("request 必须是 PlaybackRequest。")

        context = self._context_factory.create(session_phase=session_phase)
        decision = self._gate.evaluate(request, context)
        return self._route(request, context, decision, session_phase)

    def handle_tts_event(
        self,
        event: TTSExecutionEvent,
        *,
        session_phase: PlaybackSessionPhase,
    ) -> PlaybackScheduleResult | None:
        """Observe TTS facts and resume only a matching stopped preemption."""

        if not isinstance(event, TTSExecutionEvent):
            raise TypeError("event 必须是 TTSExecutionEvent。")
        if not isinstance(session_phase, PlaybackSessionPhase):
            raise TypeError("session_phase 必须是 PlaybackSessionPhase。")

        if event.event_type is TTSExecutionEventType.FAILED:
            self._failure_boundary.record(
                intent_id=event.intent_id,
                stage=TTSFailureStage.ACTIVE_PLAYBACK,
                error=event.error or "TTS playback failed",
            )

        pending: _PendingPreemption | None = None
        with self._lock:
            if event.event_type is TTSExecutionEventType.STARTED:
                self._active_tts_intent_id = event.intent_id
                return None

            if event.intent_id == self._active_tts_intent_id:
                self._active_tts_intent_id = None

            if (
                event.event_type is TTSExecutionEventType.STOPPED
                and self._pending_preemption is not None
                and event.intent_id
                == self._pending_preemption.preempted_intent_id
            ):
                pending = self._pending_preemption
                self._pending_preemption = None

        if pending is None:
            return None

        context = self._context_factory.create(session_phase=session_phase)
        decision = self._gate.evaluate(pending.request, context)
        return self._route(pending.request, context, decision, session_phase)

    def reevaluate(
        self,
        trigger: ReevaluationTrigger,
        *,
        session_phase: PlaybackSessionPhase,
    ) -> tuple[PlaybackScheduleResult, ...]:
        """Reevaluate queued requests after an explicit runtime transition."""
        context = self._context_factory.create(session_phase=session_phase)
        batch = reevaluate_deferred(
            self._deferred_queue,
            trigger=trigger,
            context=context,
        )
        results = []
        for outcome in batch.outcomes:
            if outcome.decision.disposition is PlaybackDisposition.DEFERRED:
                continue
            results.append(
                self._route(
                    outcome.entry.request,
                    context,
                    outcome.decision,
                    session_phase,
                )
            )
        return tuple(results)

    def _route(
        self,
        request: PlaybackRequest,
        context: PlaybackContext,
        decision: PlaybackDecision,
        session_phase: PlaybackSessionPhase,
    ) -> PlaybackScheduleResult:

        if decision.disposition is PlaybackDisposition.READY:
            outcome = self._failure_boundary.execute_start(
                request,
                lambda: self._execution_port.play(request),
            )
            if not outcome.accepted:
                return PlaybackScheduleResult(
                    request,
                    context,
                    decision,
                    PlaybackScheduleAction.PLAYBACK_FAILED,
                    failure=outcome.failures[-1],
                )
            return PlaybackScheduleResult(
                request,
                context,
                decision,
                PlaybackScheduleAction.HANDED_TO_TTS,
            )

        if decision.disposition is PlaybackDisposition.DEFERRED:
            entry = self._deferred_queue.defer(request, decision)
            return PlaybackScheduleResult(
                request,
                context,
                decision,
                PlaybackScheduleAction.QUEUED,
                deferred_entry=entry,
            )

        if decision.disposition is PlaybackDisposition.DROP:
            return PlaybackScheduleResult(
                request,
                context,
                decision,
                PlaybackScheduleAction.DROPPED,
            )

        with self._lock:
            if self._pending_preemption is not None:
                raise RuntimeError("已有待完成的抢占请求。")
            if self._active_tts_intent_id is None:
                raise RuntimeError("未观察到可匹配的 TTS STARTED 事件。")
            pending = _PendingPreemption(
                request=request,
                preempted_intent_id=self._active_tts_intent_id,
            )
            self._pending_preemption = pending

        try:
            self._execution_port.stop()
        except Exception:
            with self._lock:
                if self._pending_preemption is pending:
                    self._pending_preemption = None
            raise

        return PlaybackScheduleResult(
            request,
            context,
            decision,
            PlaybackScheduleAction.PREEMPT_STOP_REQUESTED,
        )


@dataclass(frozen=True)
class _PendingPreemption:
    request: PlaybackRequest
    preempted_intent_id: str
