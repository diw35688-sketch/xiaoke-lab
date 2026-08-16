"""不可变、显式推进的实验方案步骤游标。"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.protocol import ExperimentProtocol, ProtocolError, ProtocolStep


class ProtocolStepCursorError(ProtocolError):
    """步骤游标推进或跳转越界。"""


@dataclass(frozen=True)
class ProtocolStepCursor:
    protocol: ExperimentProtocol
    current_step_number: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.protocol, ExperimentProtocol):
            raise ProtocolStepCursorError("protocol必须是ExperimentProtocol。")
        self._validate_step_number(self.current_step_number)

    @classmethod
    def start(cls, protocol: ExperimentProtocol) -> "ProtocolStepCursor":
        return cls(protocol=protocol, current_step_number=1)

    @property
    def current_step(self) -> ProtocolStep:
        return self.protocol.steps[self.current_step_number - 1]

    def next(self) -> "ProtocolStepCursor":
        if self.current_step_number == len(self.protocol.steps):
            raise ProtocolStepCursorError("已经是最后一步，不能next。")
        return self.jump_to(self.current_step_number + 1)

    def prev(self) -> "ProtocolStepCursor":
        if self.current_step_number == 1:
            raise ProtocolStepCursorError("已经是第一步，不能prev。")
        return self.jump_to(self.current_step_number - 1)

    def jump_to(self, step_number: int) -> "ProtocolStepCursor":
        self._validate_step_number(step_number)
        return type(self)(self.protocol, step_number)

    def _validate_step_number(self, step_number: int) -> None:
        if (
            not isinstance(step_number, int)
            or isinstance(step_number, bool)
            or not 1 <= step_number <= len(self.protocol.steps)
        ):
            raise ProtocolStepCursorError(
                f"步骤号超出范围：{step_number}，有效范围是1-{len(self.protocol.steps)}。"
            )
