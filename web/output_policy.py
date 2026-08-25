"""Pure output-policy selection for one frozen interaction-mode snapshot."""

from dataclasses import dataclass
from enum import Enum

from src.core.conversation_turn import ExperimentContext, InteractionMode


class OutputStrategy(str, Enum):
    CHAT = "chat"
    EXPERIMENT_FREE = "experiment_free"
    EXPERIMENT_PROTOCOL = "experiment_protocol"


@dataclass(frozen=True)
class OutputPolicy:
    strategy: OutputStrategy
    save_observation: bool
    allow_record_tool: bool
    max_follow_up_questions: int


def select_output_policy(
    interaction_mode: InteractionMode,
    experiment_context: ExperimentContext,
) -> OutputPolicy:
    """Select behavior only; execute no model, save, Tool, or playback side effect."""

    if interaction_mode == InteractionMode.CHAT:
        if experiment_context != ExperimentContext.NONE:
            raise ValueError("chat 模式的 experiment_context 必须是 none。")
        return OutputPolicy(OutputStrategy.CHAT, False, False, 0)
    if interaction_mode != InteractionMode.EXPERIMENT:
        raise TypeError("interaction_mode 必须是 InteractionMode。")
    if experiment_context == ExperimentContext.FREE:
        return OutputPolicy(OutputStrategy.EXPERIMENT_FREE, True, True, 1)
    if experiment_context == ExperimentContext.PROTOCOL:
        return OutputPolicy(OutputStrategy.EXPERIMENT_PROTOCOL, True, True, 1)
    raise ValueError("experiment 模式必须选择 free 或 protocol。")
