"""Backward-compatible experiment-only specialization of ``TurnInput``."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.core.conversation_turn import InteractionMode
from src.core.turn_input import TurnInput


@dataclass(frozen=True)
class ExperimentTurnInput(TurnInput):
    """One immutable experiment request plus truthful source evidence.

    Keyboard input carries only its original text.  Recording inputs must
    carry the final ``ASRResult`` that produced the exact submitted text, so a
    later adapter cannot silently manufacture ASR evidence for typed text or
    detach a transcript from its audio-recognition evidence.
    """

    lab_session_id: str | None = field(
        default="legacy-experiment-session", kw_only=True
    )

    def __post_init__(self) -> None:
        if self.interaction_mode != InteractionMode.EXPERIMENT:
            raise ValueError("ExperimentTurnInput 只接受实验模式。")
        super().__post_init__()
