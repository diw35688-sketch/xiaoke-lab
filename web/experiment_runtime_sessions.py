"""Per-conversation and lab-session ownership for experiment runtime state."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from threading import Lock, RLock
from typing import Callable

from src.core.experiment_turn_input import ExperimentTurnInput
from src.core.reply_coordinator import ReplyCoordinator
from src.core.session_context import SessionContext


class ExperimentSubmissionConflictError(RuntimeError):
    """One request identity was reused with different immutable content."""


class ExperimentSessionBackpressureError(RuntimeError):
    """The named session already owns its allowed amount of pending work."""


@dataclass(frozen=True)
class ExperimentSubmission:
    """One ordered submission or an idempotent view of an earlier one."""

    sequence: int
    replayed: bool
    future: Future[object]


@dataclass(frozen=True)
class _SubmissionRecord:
    request: ExperimentTurnInput
    sequence: int
    future: Future[object]


class ExperimentRuntimeSession:
    """Own mutable understanding state and one FIFO worker for a named pair.

    The single-worker executor is the only mutation entrance for the session's
    ``ReplyCoordinator`` and ``SessionContext``.  Different named sessions own
    different executors and can therefore progress independently.
    """

    def __init__(
        self,
        *,
        conversation_id: str,
        lab_session_id: str,
        max_pending_tasks: int,
        context_max_events: int,
    ) -> None:
        _require_id(conversation_id, "conversation_id")
        _require_id(lab_session_id, "lab_session_id")
        if not isinstance(max_pending_tasks, int) or isinstance(
            max_pending_tasks, bool
        ):
            raise TypeError("max_pending_tasks 必须是正整数。")
        if max_pending_tasks <= 0:
            raise ValueError("max_pending_tasks 必须是正整数。")
        if not isinstance(context_max_events, int) or isinstance(
            context_max_events, bool
        ):
            raise TypeError("context_max_events 必须是正整数。")
        if context_max_events <= 0:
            raise ValueError("context_max_events 必须是正整数。")

        self.conversation_id = conversation_id
        self.lab_session_id = lab_session_id
        self._max_pending_tasks = max_pending_tasks
        self._coordinator = ReplyCoordinator()
        self._context = SessionContext(max_events=context_max_events)
        self._state_lock = RLock()
        self._submission_lock = Lock()
        self._submissions: dict[str, _SubmissionRecord] = {}
        self._next_sequence = 1
        self._closed = False
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="experiment-session",
        )

    def submit(
        self,
        request: ExperimentTurnInput,
        operation: Callable[[ReplyCoordinator, SessionContext], object],
    ) -> ExperimentSubmission:
        """Submit new work in FIFO order or reuse an exact request retry."""

        if not isinstance(request, ExperimentTurnInput):
            raise TypeError("request 必须是 ExperimentTurnInput。")
        if request.conversation_id != self.conversation_id:
            raise ValueError("request conversation_id 不一致。")
        if not callable(operation):
            raise TypeError("operation 必须可调用。")

        with self._submission_lock:
            if self._closed:
                raise RuntimeError("实验运行会话已经关闭。")

            existing = self._submissions.get(request.request_id)
            if existing is not None:
                if existing.request != request:
                    raise ExperimentSubmissionConflictError(
                        "同一 request_id 的请求内容冲突。"
                    )
                return ExperimentSubmission(
                    sequence=existing.sequence,
                    replayed=True,
                    future=existing.future,
                )

            pending_count = sum(
                not record.future.done()
                for record in self._submissions.values()
            )
            if pending_count >= self._max_pending_tasks:
                raise ExperimentSessionBackpressureError(
                    "实验运行会话的待处理任务已满。"
                )

            sequence = self._next_sequence
            self._next_sequence += 1
            future = self._executor.submit(self._run_operation, operation)
            self._submissions[request.request_id] = _SubmissionRecord(
                request=request,
                sequence=sequence,
                future=future,
            )
            return ExperimentSubmission(
                sequence=sequence,
                replayed=False,
                future=future,
            )

    def pending_count(self) -> int:
        with self._submission_lock:
            return sum(
                not record.future.done()
                for record in self._submissions.values()
            )

    def context_snapshot(self) -> tuple[str, ...]:
        with self._state_lock:
            return self._context.as_prompt_context()

    def active_clarifications(self):
        with self._state_lock:
            return self._coordinator.active_clarifications()

    def close(self) -> None:
        """Finish accepted work and permanently close this runtime instance."""

        with self._submission_lock:
            if self._closed:
                return
            self._closed = True
        self._executor.shutdown(wait=True)

    def _run_operation(
        self,
        operation: Callable[[ReplyCoordinator, SessionContext], object],
    ) -> object:
        with self._state_lock:
            return operation(self._coordinator, self._context)


class ExperimentRuntimeSessionRegistry:
    """Create exactly one experiment runtime for each named ownership pair."""

    def __init__(
        self,
        *,
        max_pending_tasks: int = 4,
        context_max_events: int = 8,
    ) -> None:
        if not isinstance(max_pending_tasks, int) or isinstance(
            max_pending_tasks, bool
        ):
            raise TypeError("max_pending_tasks 必须是正整数。")
        if max_pending_tasks <= 0:
            raise ValueError("max_pending_tasks 必须是正整数。")
        if not isinstance(context_max_events, int) or isinstance(
            context_max_events, bool
        ):
            raise TypeError("context_max_events 必须是正整数。")
        if context_max_events <= 0:
            raise ValueError("context_max_events 必须是正整数。")
        self._max_pending_tasks = max_pending_tasks
        self._context_max_events = context_max_events
        self._sessions: dict[
            tuple[str, str], ExperimentRuntimeSession
        ] = {}
        self._lock = Lock()

    def session(
        self,
        conversation_id: str,
        lab_session_id: str,
    ) -> ExperimentRuntimeSession:
        _require_id(conversation_id, "conversation_id")
        _require_id(lab_session_id, "lab_session_id")
        key = (conversation_id, lab_session_id)
        with self._lock:
            runtime = self._sessions.get(key)
            if runtime is None:
                runtime = ExperimentRuntimeSession(
                    conversation_id=conversation_id,
                    lab_session_id=lab_session_id,
                    max_pending_tasks=self._max_pending_tasks,
                    context_max_events=self._context_max_events,
                )
                self._sessions[key] = runtime
            return runtime

    def close(self, conversation_id: str, lab_session_id: str) -> bool:
        _require_id(conversation_id, "conversation_id")
        _require_id(lab_session_id, "lab_session_id")
        with self._lock:
            runtime = self._sessions.pop(
                (conversation_id, lab_session_id), None
            )
        if runtime is None:
            return False
        runtime.close()
        return True

    def clear(self) -> None:
        """Close all runtimes; primarily used for app shutdown and tests."""

        with self._lock:
            runtimes = tuple(self._sessions.values())
            self._sessions.clear()
        for runtime in runtimes:
            runtime.close()


def _require_id(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 必须是非空字符串。")


experiment_runtime_sessions = ExperimentRuntimeSessionRegistry()
