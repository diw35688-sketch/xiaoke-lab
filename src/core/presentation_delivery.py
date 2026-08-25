"""C5 屏幕与语音交付计划合同。

屏幕意图始终保留，语音项经过确定性渠道政策与认知负担预算筛选。
本模块只回答“显示什么、哪些内容具有语音资格”，不判断当前能否播放，
不调用 TTS、不操作麦克风，也不负责延后、过期或取消调度。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from src.core.presentation_copy import copy_for_intent
from src.core.presentation_intent import MessageKind, PresentationIntent
from src.core.presentation_intent import MessagePriority
from src.core.voice_delivery import (
    MAX_ITEM_CHARS,
    apply_turn_budget,
    voice_text_for_intent,
)


@dataclass(frozen=True)
class VoiceDeliveryItem:
    """一条已通过内容政策与认知负担预算的语音项。"""

    intent_id: str
    kind: MessageKind
    priority: MessagePriority
    voice_text: str
    source_block_id: str | None = None
    max_chars: int = MAX_ITEM_CHARS
    speech_rate: float = 1.0

    def __post_init__(self) -> None:
        if not self.intent_id.strip():
            raise ValueError("intent_id 不能为空。")
        if not isinstance(self.kind, MessageKind):
            raise TypeError("kind 必须是 MessageKind。")
        if not isinstance(self.priority, MessagePriority):
            raise TypeError("priority 必须是 MessagePriority。")
        if not isinstance(self.voice_text, str) or not self.voice_text.strip():
            raise ValueError("voice_text 必须是非空字符串。")
        source_block_id = self.source_block_id or f"intent:{self.intent_id}"
        if not isinstance(source_block_id, str) or not source_block_id.strip():
            raise ValueError("source_block_id 必须是非空字符串。")
        object.__setattr__(self, "source_block_id", source_block_id)
        if not isinstance(self.max_chars, int) or isinstance(self.max_chars, bool):
            raise TypeError("max_chars 必须是正整数。")
        if self.max_chars <= 0:
            raise ValueError("max_chars 必须是正整数。")
        if len(self.voice_text) > self.max_chars:
            raise ValueError(f"单条 voice_text 不能超过 {self.max_chars} 字。")
        if not isinstance(self.speech_rate, (int, float)) or isinstance(self.speech_rate, bool):
            raise TypeError("speech_rate 必须是数字。")
        if not 0.5 <= float(self.speech_rate) <= 2.0:
            raise ValueError("speech_rate 必须在 0.5 到 2.0 之间。")
        object.__setattr__(self, "speech_rate", float(self.speech_rate))

    def as_dict(self) -> dict:
        return {
            "intent_id": self.intent_id,
            "kind": self.kind.value,
            "priority": self.priority.name,
            "voice_text": self.voice_text,
            "source_block_id": self.source_block_id,
            "speech_rate": self.speech_rate,
        }


@dataclass(frozen=True)
class PresentationDeliveryPlan:
    """一次呈现轮次的内容计划；不代表已经显示或获准播放。"""

    screen_intents: tuple[PresentationIntent, ...]
    voice_items: tuple[VoiceDeliveryItem, ...]


def build_delivery_plan(
    intents: Iterable[PresentationIntent],
    *,
    ui_mode: str,
    source_block_ids: Mapping[str, str] | None = None,
    speak_record_ack: bool = False,
    speech_rate: float = 1.0,
) -> PresentationDeliveryPlan:
    """从同一批 Intent 产生屏幕内容与具有语音资格的内容。"""

    screen_intents = tuple(intents)
    candidates = tuple(
        (
            intent,
            voice_text_for_intent(
                intent,
                copy_for_intent(intent, ui_mode=ui_mode, voice=True),
                speak_record_ack=speak_record_ack,
            ),
        )
        for intent in screen_intents
    )
    budgeted = apply_turn_budget(candidates)
    voice_items = tuple(
        VoiceDeliveryItem(
            intent.intent_id,
            intent.kind,
            intent.priority,
            voice_text,
            (source_block_ids or {}).get(
                intent.intent_id, f"intent:{intent.intent_id}"
            ),
            speech_rate=speech_rate,
        )
        for (intent, _), voice_text in zip(candidates, budgeted)
        if voice_text is not None
    )

    return PresentationDeliveryPlan(
        screen_intents=screen_intents,
        voice_items=voice_items,
    )


def bind_voice_sources(
    plan: PresentationDeliveryPlan,
    source_block_ids: Mapping[str, str],
) -> PresentationDeliveryPlan:
    """Rebind qualified voice to visible Blocks without re-running policy."""

    if not isinstance(plan, PresentationDeliveryPlan):
        raise TypeError("plan 必须是 PresentationDeliveryPlan。")
    return PresentationDeliveryPlan(
        plan.screen_intents,
        tuple(
            VoiceDeliveryItem(
                item.intent_id,
                item.kind,
                item.priority,
                item.voice_text,
                source_block_ids.get(item.intent_id, item.source_block_id),
                item.max_chars,
                item.speech_rate,
            )
            for item in plan.voice_items
        ),
    )


def bind_voice_items(
    items: Iterable[VoiceDeliveryItem], source_block_id: str
) -> tuple[VoiceDeliveryItem, ...]:
    """Bind a producer batch to one already-visible Block."""

    if not isinstance(source_block_id, str) or not source_block_id.strip():
        raise ValueError("source_block_id 必须是非空字符串。")
    return tuple(
        VoiceDeliveryItem(
            item.intent_id, item.kind, item.priority, item.voice_text,
            source_block_id, item.max_chars,
            item.speech_rate,
        )
        for item in items
    )
