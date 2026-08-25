"""Request-level interaction-mode snapshot validation without business routing."""

from pydantic import BaseModel, Field, model_validator

from src.core.conversation_turn import ExperimentContext, InputSource, InteractionMode


class ModeSnapshotFields(BaseModel):
    interaction_mode: InteractionMode = InteractionMode.CHAT
    experiment_context: ExperimentContext = ExperimentContext.NONE
    mode_version: int = Field(default=1, ge=1)
    input_source: InputSource = InputSource.TEXT
    request_id: str | None = Field(default=None, min_length=1, max_length=128)
    turn_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_mode_context(self):
        mode = self.interaction_mode
        context = self.experiment_context
        if mode == InteractionMode.CHAT and context != ExperimentContext.NONE:
            raise ValueError("chat 模式的 experiment_context 必须是 none")
        if mode == InteractionMode.EXPERIMENT and context not in {
            ExperimentContext.FREE,
            ExperimentContext.PROTOCOL,
        }:
            raise ValueError("experiment 模式必须选择 free 或 protocol")
        if (self.request_id is None) != (self.turn_id is None):
            raise ValueError("request_id 和 turn_id 必须同时提供或同时省略")
        return self

    def mode_snapshot(self) -> dict[str, object]:
        return {
            "interaction_mode": self.interaction_mode.value,
            "experiment_context": self.experiment_context.value,
            "mode_version": self.mode_version,
            "input_source": self.input_source.value,
        }
