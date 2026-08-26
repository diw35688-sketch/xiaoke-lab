"""Bounded TTS failure policy and immutable failure evidence."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from threading import Lock

from src.core.playback_request import PlaybackRequest


class TTSFailureStage(str, Enum):
    START_COMMAND = "start_command"
    ACTIVE_PLAYBACK = "active_playback"
    EVENT_DELIVERY = "event_delivery"


@dataclass(frozen=True)
class TTSFailureRecord:
    intent_id: str
    stage: TTSFailureStage
    error: str
    attempt: int
    will_retry: bool

    def __post_init__(self) -> None:
        if not isinstance(self.intent_id, str) or not self.intent_id.strip():
            raise ValueError("intent_id 不能为空。")
        if not isinstance(self.stage, TTSFailureStage):
            raise TypeError("stage 必须是 TTSFailureStage。")
        if not isinstance(self.error, str) or not self.error.strip():
            raise ValueError("error 不能为空。")
        if type(self.attempt) is not int or self.attempt < 1:
            raise ValueError("attempt 必须是大于等于 1 的整数。")
        if type(self.will_retry) is not bool:
            raise TypeError("will_retry 必须是 bool。")
        if self.stage is not TTSFailureStage.START_COMMAND and self.will_retry:
            raise ValueError("只有 START_COMMAND 失败可以自动重试。")


@dataclass(frozen=True)
class TTSStartOutcome:
    accepted: bool
    attempts: int
    failures: tuple[TTSFailureRecord, ...]


class TTSFailureBoundary:
    """Retry only unaccepted start commands and retain all failure evidence."""

    def __init__(self, *, max_start_retries: int = 1) -> None:
        if type(max_start_retries) is not int or max_start_retries < 0:
            raise ValueError("max_start_retries 必须是大于等于 0 的整数。")
        self._max_start_retries = max_start_retries
        self._records: list[TTSFailureRecord] = []
        self._lock = Lock()

    def execute_start(
        self,
        request: PlaybackRequest,
        command: Callable[[], None],
    ) -> TTSStartOutcome:
        if not isinstance(request, PlaybackRequest):
            raise TypeError("request 必须是 PlaybackRequest。")
        if not callable(command):
            raise TypeError("command 必须是可调用对象。")

        failures: list[TTSFailureRecord] = []
        total_attempts = self._max_start_retries + 1
        for attempt in range(1, total_attempts + 1):
            try:
                command()
                return TTSStartOutcome(True, attempt, tuple(failures))
            except Exception as exc:
                record = self.record(
                    intent_id=request.intent_id,
                    stage=TTSFailureStage.START_COMMAND,
                    error=_error_text(exc),
                    attempt=attempt,
                    will_retry=attempt < total_attempts,
                )
                failures.append(record)
        return TTSStartOutcome(False, total_attempts, tuple(failures))

    def record(
        self,
        *,
        intent_id: str,
        stage: TTSFailureStage,
        error: str,
        attempt: int = 1,
        will_retry: bool = False,
    ) -> TTSFailureRecord:
        record = TTSFailureRecord(
            intent_id=intent_id,
            stage=stage,
            error=error,
            attempt=attempt,
            will_retry=will_retry,
        )
        with self._lock:
            self._records.append(record)
        return record

    def snapshot(self) -> tuple[TTSFailureRecord, ...]:
        with self._lock:
            return tuple(self._records)


def _error_text(exc: Exception) -> str:
    text = str(exc).strip()
    return text or type(exc).__name__
