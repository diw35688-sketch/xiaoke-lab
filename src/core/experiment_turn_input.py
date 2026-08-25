"""Source-truthful input contract for one experiment-mode turn.

This module only validates and carries immutable input evidence.  It does not
invoke understanding, route commands, save records, mutate clarification
state, or produce user-visible output.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.asr.schemas import ASRResult
from src.core.conversation_turn import (
    ExperimentContext,
    InputSource,
    InteractionMode,
)


def _require_non_blank(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} 必须是字符串。")
    if not value.strip():
        raise ValueError(f"{field_name} 必须是非空字符串。")


@dataclass(frozen=True)
class ExperimentTurnInput:
    """One immutable experiment request plus truthful source evidence.

    Keyboard input carries only its original text.  Recording inputs must
    carry the final ``ASRResult`` that produced the exact submitted text, so a
    later adapter cannot silently manufacture ASR evidence for typed text or
    detach a transcript from its audio-recognition evidence.
    """

    conversation_id: str
    request_id: str
    turn_id: str
    interaction_mode: InteractionMode
    experiment_context: ExperimentContext
    mode_version: int
    input_source: InputSource
    raw_text: str
    asr_result: ASRResult | None = None

    def __post_init__(self) -> None:
        for field_name in ("conversation_id", "request_id", "turn_id"):
            _require_non_blank(getattr(self, field_name), field_name)
        _require_non_blank(self.raw_text, "raw_text")

        if not isinstance(self.interaction_mode, InteractionMode):
            raise TypeError("interaction_mode 必须是 InteractionMode。")
        if self.interaction_mode != InteractionMode.EXPERIMENT:
            raise ValueError("ExperimentTurnInput 只接受实验模式。")
        if not isinstance(self.experiment_context, ExperimentContext):
            raise TypeError("experiment_context 必须是 ExperimentContext。")
        if self.experiment_context not in {
            ExperimentContext.FREE,
            ExperimentContext.PROTOCOL,
        }:
            raise ValueError("实验模式必须选择 free 或 protocol 上下文。")
        if not isinstance(self.mode_version, int) or isinstance(
            self.mode_version, bool
        ):
            raise TypeError("mode_version 必须是正整数。")
        if self.mode_version <= 0:
            raise ValueError("mode_version 必须是正整数。")
        if not isinstance(self.input_source, InputSource):
            raise TypeError("input_source 必须是 InputSource。")
        if self.asr_result is not None and not isinstance(
            self.asr_result, ASRResult
        ):
            raise TypeError("asr_result 必须是 ASRResult 或 None。")

        if self.input_source == InputSource.TEXT:
            if self.asr_result is not None:
                raise ValueError("文字输入不能携带 ASR 证据。")
            return

        if self.asr_result is None:
            raise ValueError("语音输入必须携带 ASR 证据。")
        if not self.asr_result.is_final:
            raise ValueError("语音输入必须携带最终 ASR 证据。")
        if self.raw_text != self.asr_result.asr_transcript:
            raise ValueError("语音 raw_text 必须与 ASR 忠实转写一致。")

    def to_wire(self) -> dict[str, object]:
        """Return a JSON-safe snapshot without changing the evidence."""

        return {
            "conversation_id": self.conversation_id,
            "request_id": self.request_id,
            "turn_id": self.turn_id,
            "interaction_mode": self.interaction_mode.value,
            "experiment_context": self.experiment_context.value,
            "mode_version": self.mode_version,
            "input_source": self.input_source.value,
            "raw_text": self.raw_text,
            "asr_result": (
                self.asr_result.to_dict()
                if self.asr_result is not None
                else None
            ),
        }
