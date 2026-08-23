"""C5 屏幕与语音交付计划合同。

屏幕意图始终保留，语音项经过确定性渠道政策与认知负担预算筛选。
本模块只回答“显示什么、哪些内容具有语音资格”，不判断当前能否播放，
不调用 TTS、不操作麦克风，也不负责延后、过期或取消调度。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

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

    def __post_init__(self) -> None:
        if not self.intent_id.strip():
            raise ValueError("intent_id 不能为空。")
        if not isinstance(self.kind, MessageKind):
            raise TypeError("kind 必须是 MessageKind。")
        if not isinstance(self.priority, MessagePriority):
            raise TypeError("priority 必须是 MessagePriority。")
        if not isinstance(self.voice_text, str) or not self.voice_text.strip():
            raise ValueError("voice_text 必须是非空字符串。")
        if len(self.voice_text) > MAX_ITEM_CHARS:
            raise ValueError(f"单条 voice_text 不能超过 {MAX_ITEM_CHARS} 字。")

    def as_dict(self) -> dict:
        return {
            "intent_id": self.intent_id,
            "kind": self.kind.value,
            "priority": self.priority.name,
            "voice_text": self.voice_text,
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
) -> PresentationDeliveryPlan:
    """从同一批 Intent 产生屏幕内容与具有语音资格的内容。"""

    screen_intents = tuple(intents)
    candidates = tuple(
        (
            intent,
            voice_text_for_intent(
                intent,
                copy_for_intent(intent, ui_mode=ui_mode, voice=True),
            ),
        )
        for intent in screen_intents
    )
    budgeted = apply_turn_budget(candidates)
    voice_items = tuple(
        VoiceDeliveryItem(intent.intent_id, intent.kind, intent.priority, voice_text)
        for (intent, _), voice_text in zip(candidates, budgeted)
        if voice_text is not None
    )

    return PresentationDeliveryPlan(
        screen_intents=screen_intents,
        voice_items=voice_items,
    )
