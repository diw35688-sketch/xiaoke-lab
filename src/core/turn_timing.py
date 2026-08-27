"""Monotonic timing recorder for one Turn without business side effects."""
from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter
from typing import Callable


class TurnTimingRecorder:
    def __init__(
        self,
        *,
        monotonic: Callable[[], float] = perf_counter,
        wall_clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._monotonic = monotonic
        self._wall_clock = wall_clock or (lambda: datetime.now(timezone.utc))
        self._started = monotonic()
        self._marks: dict[str, dict[str, object]] = {}
        self.mark("request_received")

    def mark(self, phase: str) -> dict[str, object]:
        if not isinstance(phase, str) or not phase.strip():
            raise ValueError("计时 phase 必须是非空字符串。")
        if phase in self._marks:
            return dict(self._marks[phase])
        mark = {
            "at": self._wall_clock().isoformat(timespec="milliseconds"),
            "elapsed_ms": round((self._monotonic() - self._started) * 1000),
        }
        self._marks[phase] = mark
        return dict(mark)

    def snapshot(self) -> dict[str, dict[str, object]]:
        return {name: dict(value) for name, value in self._marks.items()}
