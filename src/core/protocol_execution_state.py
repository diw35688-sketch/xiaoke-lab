"""Session-scoped protocol progress with one cumulative fact state per step."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from src.core.protocol_completion_policy import ProtocolStepFactState


class ProtocolStepProgressStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    LEFT_WITH_PENDING = "left_with_pending"
    COMPLETED = "completed"


@dataclass(frozen=True)
class ProtocolExecutionState:
    protocol_id: str
    protocol_version: str
    current_step_number: int
    steps: Mapping[int, ProtocolStepFactState]
    statuses: Mapping[int, ProtocolStepProgressStatus]

    def __post_init__(self) -> None:
        if not self.protocol_id.strip() or not self.protocol_version.strip():
            raise ValueError("方案执行状态必须包含方案身份。")
        if self.current_step_number <= 0:
            raise ValueError("当前方案步骤号必须为正整数。")
        object.__setattr__(self, "steps", MappingProxyType(dict(self.steps)))
        object.__setattr__(self, "statuses", MappingProxyType(dict(self.statuses)))

    @classmethod
    def start(
        cls, *, protocol_id: str, protocol_version: str, step_number: int = 1
    ) -> "ProtocolExecutionState":
        state = ProtocolStepFactState.empty(
            protocol_id=protocol_id,
            protocol_version=protocol_version,
            step_number=step_number,
        )
        return cls(
            protocol_id,
            protocol_version,
            step_number,
            {step_number: state},
            {step_number: ProtocolStepProgressStatus.IN_PROGRESS},
        )

    @classmethod
    def from_snapshot(
        cls,
        snapshot: Mapping[str, object] | None,
        *,
        protocol_id: str,
        protocol_version: str,
        default_step_number: int = 1,
    ) -> "ProtocolExecutionState":
        if not snapshot or (
            snapshot.get("protocol_id") != protocol_id
            or snapshot.get("protocol_version") != protocol_version
        ):
            return cls.start(
                protocol_id=protocol_id,
                protocol_version=protocol_version,
                step_number=default_step_number,
            )

        # Backward compatibility: the previous snapshot was one fact state.
        if "steps" not in snapshot:
            legacy_step = int(snapshot.get("step_number") or default_step_number)
            fact = ProtocolStepFactState.from_snapshot(
                snapshot,
                protocol_id=protocol_id,
                protocol_version=protocol_version,
                step_number=legacy_step,
            )
            return cls(
                protocol_id,
                protocol_version,
                legacy_step,
                {legacy_step: fact},
                {legacy_step: ProtocolStepProgressStatus.IN_PROGRESS},
            )

        current = int(snapshot.get("current_step_number") or default_step_number)
        raw_steps = snapshot.get("steps") or {}
        raw_statuses = snapshot.get("statuses") or {}
        if not isinstance(raw_steps, Mapping) or not isinstance(raw_statuses, Mapping):
            raise TypeError("方案步骤状态快照格式错误。")
        steps = {
            int(number): ProtocolStepFactState.from_snapshot(
                item if isinstance(item, Mapping) else {},
                protocol_id=protocol_id,
                protocol_version=protocol_version,
                step_number=int(number),
            )
            for number, item in raw_steps.items()
        }
        statuses = {
            int(number): ProtocolStepProgressStatus(str(value))
            for number, value in raw_statuses.items()
        }
        if current not in steps:
            steps[current] = ProtocolStepFactState.empty(
                protocol_id=protocol_id,
                protocol_version=protocol_version,
                step_number=current,
            )
        statuses.setdefault(current, ProtocolStepProgressStatus.IN_PROGRESS)
        return cls(protocol_id, protocol_version, current, steps, statuses)

    def step_state(self, step_number: int) -> ProtocolStepFactState:
        return self.steps.get(step_number) or ProtocolStepFactState.empty(
            protocol_id=self.protocol_id,
            protocol_version=self.protocol_version,
            step_number=step_number,
        )

    def with_step(
        self,
        state: ProtocolStepFactState,
        *,
        status: ProtocolStepProgressStatus | None = None,
    ) -> "ProtocolExecutionState":
        steps = dict(self.steps)
        steps[state.step_number] = state
        statuses = dict(self.statuses)
        if status is not None:
            statuses[state.step_number] = status
        return replace(self, steps=steps, statuses=statuses)

    def move_to(
        self,
        step_number: int,
        *,
        leaving_status: ProtocolStepProgressStatus,
    ) -> "ProtocolExecutionState":
        statuses = dict(self.statuses)
        statuses[self.current_step_number] = leaving_status
        statuses.setdefault(step_number, ProtocolStepProgressStatus.IN_PROGRESS)
        steps = dict(self.steps)
        steps.setdefault(step_number, self.step_state(step_number))
        return replace(
            self,
            current_step_number=step_number,
            steps=steps,
            statuses=statuses,
        )

    def to_snapshot(self) -> dict[str, object]:
        return {
            "protocol_id": self.protocol_id,
            "protocol_version": self.protocol_version,
            "current_step_number": self.current_step_number,
            "steps": {
                str(number): state.to_snapshot()
                for number, state in self.steps.items()
            },
            "statuses": {
                str(number): status.value
                for number, status in self.statuses.items()
            },
        }
