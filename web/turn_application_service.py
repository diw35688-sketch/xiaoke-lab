"""Single orchestration boundary for every committed Web conversation Turn."""

from __future__ import annotations

import hashlib
import logging
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from threading import Condition, Lock
from typing import Mapping

from asr_application_service import ASRApplicationService
from database.turn_store import TurnRequestConflictError, TurnStore, canonical_request_hash
from src.core.conversation_turn import InteractionMode
from src.core.turn_input import TurnInput
from src.core.turn_request_envelope import TurnRequestEnvelope
from src.core.turn_timing import TurnTimingRecorder
from turn_processors import PreparedTurn, TurnProcessor


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TurnExecutionResult:
    result: Mapping[str, object]
    voice_items: tuple[object, ...]
    replayed: bool


class TurnProgress:
    """Replayable phase history shared by reconnecting SSE consumers."""

    def __init__(self) -> None:
        self._condition = Condition()
        self._phases: list[str] = []
        self._finished = False

    def publish(self, phase: str) -> None:
        with self._condition:
            if not self._phases or self._phases[-1] != phase:
                self._phases.append(phase)
            self._condition.notify_all()

    def finish(self) -> None:
        with self._condition:
            self._finished = True
            self._condition.notify_all()

    def wait(self, index: int, timeout: float = 0.25) -> tuple[tuple[str, ...], bool]:
        with self._condition:
            if index >= len(self._phases) and not self._finished:
                self._condition.wait(timeout)
            return tuple(self._phases[index:]), self._finished


@dataclass(frozen=True)
class TurnSubmission:
    future: Future[TurnExecutionResult]
    replayed: bool
    attempt: int
    progress: TurnProgress


@dataclass(frozen=True)
class _ActiveSubmission:
    request_hash: str
    future: Future[TurnExecutionResult]
    attempt: int
    progress: TurnProgress


class TurnApplicationService:
    """Reserve, dispatch, atomically commit, and forget in-process Futures."""

    def __init__(self, *, store: TurnStore, chat_processor: TurnProcessor,
                 experiment_processor: TurnProcessor, max_chat_workers: int = 4) -> None:
        self.store = store
        self._chat_processor = chat_processor
        self._experiment_processor = experiment_processor
        self._chat_executor = ThreadPoolExecutor(
            max_workers=max_chat_workers, thread_name_prefix="turn-chat"
        )
        self._experiment_executors: dict[tuple[str, str], ThreadPoolExecutor] = {}
        self._submissions: dict[str, _ActiveSubmission] = {}
        self._lock = Lock()

    def recover_after_restart(self) -> int:
        return self.store.recover_processing()

    def submit(self, turn: TurnInput, *, request_hash: str | None = None,
               asr_evidence: Mapping[str, object] | None = None) -> TurnSubmission:
        digest = request_hash or canonical_request_hash(turn.to_wire())
        with self._lock:
            active = self._active_or_conflict(turn.request_id, digest)
            if active is not None:
                return TurnSubmission(active.future, True, active.attempt, active.progress)
            reservation = self.store.reserve(turn, digest)
            replay = self._committed_submission(reservation)
            if replay is not None:
                return replay
            if reservation.disposition == "processing":
                raise RuntimeError("请求已在处理，但本进程没有对应 Future；请稍后重试。")
            progress = TurnProgress()
            future = self._executor_for(turn).submit(
                self._execute, turn, asr_evidence, progress
            )
            return self._register(turn.request_id, digest, future,
                                  reservation.attempt, progress)

    def submit_audio(self, envelope: TurnRequestEnvelope, payload: bytes, *,
                     asr_service: ASRApplicationService) -> TurnSubmission:
        if envelope.input_source.value not in {"single_recording", "continuous_call"}:
            raise ValueError("/turn/audio 只接受 single_recording 或 continuous_call。")
        digest = canonical_request_hash({
            **envelope.to_wire(),
            "audio_sha256": hashlib.sha256(payload).hexdigest(),
        })
        with self._lock:
            active = self._active_or_conflict(envelope.request_id, digest)
            if active is not None:
                return TurnSubmission(active.future, True, active.attempt, active.progress)
            reservation = self.store.reserve_envelope(envelope, digest)
            replay = self._committed_submission(reservation)
            if replay is not None:
                return replay
            if reservation.disposition == "processing":
                raise RuntimeError("音频请求已在处理，但本进程没有对应 Future。")
            progress = TurnProgress()
            future = self._executor_for(envelope).submit(
                self._execute_audio, envelope, payload, asr_service, progress
            )
            return self._register(envelope.request_id, digest, future,
                                  reservation.attempt, progress)

    def _active_or_conflict(self, request_id: str, digest: str):
        active = self._submissions.get(request_id)
        if active is not None and active.request_hash != digest:
            raise TurnRequestConflictError("同一 request_id 的处理中请求内容冲突。")
        return active

    @staticmethod
    def _committed_submission(reservation):
        if reservation.disposition != "committed":
            return None
        future: Future[TurnExecutionResult] = Future()
        future.set_result(TurnExecutionResult(reservation.result or {}, (), True))
        progress = TurnProgress()
        progress.finish()
        return TurnSubmission(future, True, reservation.attempt, progress)

    def _register(self, request_id: str, digest: str,
                  future: Future[TurnExecutionResult], attempt: int,
                  progress: TurnProgress) -> TurnSubmission:
        self._submissions[request_id] = _ActiveSubmission(digest, future, attempt, progress)
        future.add_done_callback(
            lambda completed, rid=request_id: self._forget(rid, completed)
        )
        return TurnSubmission(future, False, attempt, progress)

    def _executor_for(self, turn) -> ThreadPoolExecutor:
        if turn.interaction_mode == InteractionMode.CHAT:
            return self._chat_executor
        key = (turn.conversation_id, turn.lab_session_id or "")
        executor = self._experiment_executors.get(key)
        if executor is None:
            executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="turn-experiment")
            self._experiment_executors[key] = executor
        return executor

    def _execute(self, turn: TurnInput, asr_evidence, progress: TurnProgress):
        timing = TurnTimingRecorder()
        timing.mark("request_received")
        try:
            return self._execute_prepared(turn, asr_evidence, timing, progress)
        finally:
            progress.finish()

    def _execute_audio(self, envelope: TurnRequestEnvelope, payload: bytes,
                       asr_service: ASRApplicationService, progress: TurnProgress):
        timing = TurnTimingRecorder()
        timing.mark("request_received")
        recognized = None
        try:
            def phase(name: str) -> None:
                timing.mark(name)
                progress.publish("asr" if name.startswith("asr_") else name)

            recognized = asr_service.recognize_upload(
                payload, conversation_id=envelope.conversation_id,
                request_id=envelope.request_id, lab_session_id=envelope.lab_session_id,
                retain=True, on_phase=phase,
            )
            turn = TurnInput(
                envelope.conversation_id, envelope.request_id, envelope.turn_id,
                envelope.lab_session_id, envelope.interaction_mode,
                envelope.experiment_context, envelope.mode_version,
                envelope.input_source, recognized.result.asr_transcript, recognized.result,
            )
            return self._execute_prepared(turn, recognized.evidence(), timing, progress)
        except Exception as error:
            timing.mark("failed")
            self.store.fail(envelope.request_id, code=type(error).__name__.upper(),
                            detail=str(error), timings=timing.snapshot())
            if recognized is not None:
                asr_service.delete_audio(recognized.audio_rel_path)
            raise
        finally:
            progress.finish()

    def _execute_prepared(self, turn: TurnInput, asr_evidence,
                          timing: TurnTimingRecorder, progress: TurnProgress):
        timing.mark("dispatch_started")
        progress.publish("dispatching")
        processor = (self._chat_processor if turn.interaction_mode == InteractionMode.CHAT
                     else self._experiment_processor)
        try:
            progress.publish("understanding")
            prepared: PreparedTurn = processor.prepare(turn, timing)
            timing.mark("validation_completed")
            progress.publish("validating")
            timing.mark("result_built")
            result = {"turn": prepared.turn.to_wire(),
                      "business": dict(prepared.business),
                      "timing": timing.snapshot()}
            timing.mark("persistence_started")
            progress.publish("saving")
            self.store.commit(
                turn=turn, result=result, timings=timing.snapshot(),
                messages=prepared.messages, lab_record=prepared.lab_record,
                asr_evidence=asr_evidence,
                experiment_events=prepared.experiment_events,
                session_state=prepared.session_state,
            )
            timing.mark("persistence_committed")
            result["timing"] = timing.snapshot()
            try:
                self.store.update_committed_result(
                    turn.request_id, result=result, timings=result["timing"]
                )
            except Exception:
                # Business rows are already committed. A diagnostic-only follow-up
                # failure must not turn success into an error or delete committed WAV.
                logger.exception(
                    "turn_post_commit_timing_update_failed request_id=%s",
                    turn.request_id,
                )
            return TurnExecutionResult(result, prepared.voice_items, False)
        except Exception as error:
            timing.mark("failed")
            self.store.fail(turn.request_id, code=type(error).__name__.upper(),
                            detail=str(error), timings=timing.snapshot())
            raise

    def _forget(self, request_id: str, completed: Future) -> None:
        with self._lock:
            active = self._submissions.get(request_id)
            if active is not None and active.future is completed:
                self._submissions.pop(request_id, None)

    def close(self) -> None:
        self._chat_executor.shutdown(wait=True)
        with self._lock:
            executors = tuple(self._experiment_executors.values())
            self._experiment_executors.clear()
        for executor in executors:
            executor.shutdown(wait=True)
