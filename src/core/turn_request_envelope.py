"""Immutable request identity and mode snapshot available before audio ASR."""

from dataclasses import dataclass

from src.core.conversation_turn import ExperimentContext, InputSource, InteractionMode


def _required(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} 必须是非空字符串。")


@dataclass(frozen=True)
class TurnRequestEnvelope:
    conversation_id: str
    request_id: str
    turn_id: str
    lab_session_id: str | None
    interaction_mode: InteractionMode
    experiment_context: ExperimentContext
    mode_version: int
    input_source: InputSource

    def __post_init__(self) -> None:
        for name in ("conversation_id", "request_id", "turn_id"):
            _required(getattr(self, name), name)
        if not isinstance(self.interaction_mode, InteractionMode):
            raise TypeError("interaction_mode 类型无效。")
        if not isinstance(self.experiment_context, ExperimentContext):
            raise TypeError("experiment_context 类型无效。")
        if not isinstance(self.input_source, InputSource):
            raise TypeError("input_source 类型无效。")
        if not isinstance(self.mode_version, int) or isinstance(self.mode_version, bool):
            raise TypeError("mode_version 必须是正整数。")
        if self.mode_version <= 0:
            raise ValueError("mode_version 必须是正整数。")
        if self.interaction_mode == InteractionMode.CHAT:
            if self.experiment_context != ExperimentContext.NONE:
                raise ValueError("Chat 的 experiment_context 必须是 none。")
            if self.lab_session_id is not None:
                raise ValueError("Chat 不能携带 lab_session_id。")
        else:
            if self.experiment_context not in {ExperimentContext.FREE, ExperimentContext.PROTOCOL}:
                raise ValueError("实验必须选择 free 或 protocol。")
            _required(self.lab_session_id, "lab_session_id")

    def to_wire(self) -> dict[str, object]:
        return {
            "conversation_id": self.conversation_id,
            "request_id": self.request_id,
            "turn_id": self.turn_id,
            "lab_session_id": self.lab_session_id,
            "interaction_mode": self.interaction_mode.value,
            "experiment_context": self.experiment_context.value,
            "mode_version": self.mode_version,
            "input_source": self.input_source.value,
        }
