"""Pure visible-spoken Block policy for one conversation turn.

This module creates no model response, persistence, Tool call, playback request,
or TTS audio.  It only selects a deterministic estimated duration budget and
builds one visible text source plus one VOICE reference whose text is derived
from that source.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.core.conversation_turn import (
    BlockType,
    ConversationBlock,
    ExperimentContext,
    InteractionMode,
)
from src.core.presentation_intent import MessagePriority


ESTIMATED_CHARS_PER_SECOND = 5
CHAT_DEFAULT_MAX_CHARS = 10 * ESTIMATED_CHARS_PER_SECOND
EXPERIMENT_TURN_MAX_CHARS = 15 * ESTIMATED_CHARS_PER_SECOND


class ReplyScope(str, Enum):
    DEFAULT = "default"
    CONTINUATION = "continuation"


@dataclass(frozen=True)
class SpokenOutputPolicy:
    interaction_mode: InteractionMode
    experiment_context: ExperimentContext
    reply_scope: ReplyScope
    estimated_max_chars: int | None
    max_voice_blocks: int = 1


@dataclass(frozen=True)
class SpokenBlockPlan:
    """One visible source Block and its text-free VOICE reference."""

    source_block: ConversationBlock
    voice_block: ConversationBlock

    def __post_init__(self) -> None:
        if self.source_block.type != BlockType.ASSISTANT_TEXT:
            raise ValueError("语音来源必须是可见 ASSISTANT_TEXT block。")
        if self.source_block.payload.get("role") != "spoken":
            raise ValueError("语音来源 block 的 role 必须是 spoken。")
        text = self.source_block.payload.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("语音来源 block 必须包含非空可见 text。")
        if self.voice_block.type != BlockType.VOICE:
            raise ValueError("voice_block 必须是 VOICE block。")
        if self.voice_block.source_block_id != self.source_block.block_id:
            raise ValueError("VOICE 必须引用同一计划的可见来源 block。")

    @property
    def voice_text(self) -> str:
        """The only TTS text source: exact visible Block text, never a copy."""

        return self.source_block.payload["text"]  # type: ignore[return-value]

    @property
    def blocks(self) -> tuple[ConversationBlock, ConversationBlock]:
        return (self.source_block, self.voice_block)


def select_spoken_output_policy(
    interaction_mode: InteractionMode,
    experiment_context: ExperimentContext,
    *,
    reply_scope: ReplyScope = ReplyScope.DEFAULT,
) -> SpokenOutputPolicy:
    """Select duration/quantity constraints without producing any output."""

    if not isinstance(reply_scope, ReplyScope):
        raise TypeError("reply_scope 必须是 ReplyScope。")
    if interaction_mode == InteractionMode.CHAT:
        if experiment_context != ExperimentContext.NONE:
            raise ValueError("chat 模式的 experiment_context 必须是 none。")
        return SpokenOutputPolicy(
            interaction_mode,
            experiment_context,
            reply_scope,
            None if reply_scope == ReplyScope.CONTINUATION else CHAT_DEFAULT_MAX_CHARS,
        )
    if interaction_mode != InteractionMode.EXPERIMENT:
        raise TypeError("interaction_mode 必须是 InteractionMode。")
    if experiment_context not in (ExperimentContext.FREE, ExperimentContext.PROTOCOL):
        raise ValueError("experiment 模式必须选择 free 或 protocol。")
    return SpokenOutputPolicy(
        interaction_mode,
        experiment_context,
        reply_scope,
        EXPERIMENT_TURN_MAX_CHARS,
    )


def build_spoken_block_plan(
    *,
    turn_id: str,
    text: str,
    intent_id: str,
    priority: MessagePriority,
    policy: SpokenOutputPolicy,
) -> SpokenBlockPlan:
    """Build exactly one visible spoken Block and one reference-only VOICE."""

    if not isinstance(policy, SpokenOutputPolicy):
        raise TypeError("policy 必须是 SpokenOutputPolicy。")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text 必须是非空字符串。")
    visible_text = text.strip()
    if (
        policy.estimated_max_chars is not None
        and len(visible_text) > policy.estimated_max_chars
    ):
        raise ValueError(
            f"可见语音正文超过估算上限 {policy.estimated_max_chars} 字；"
            "必须在建立 Block 前生成更精炼的完整文本，禁止截断。"
        )
    source = ConversationBlock(
        block_id=f"{turn_id}:spoken",
        type=BlockType.ASSISTANT_TEXT,
        payload={"role": "spoken", "text": visible_text},
    )
    voice = ConversationBlock(
        block_id=f"{turn_id}:voice",
        type=BlockType.VOICE,
        payload={},
        source_block_id=source.block_id,
        intent_id=intent_id,
        priority=priority,
    )
    return SpokenBlockPlan(source, voice)
