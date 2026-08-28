# -*- coding: utf-8 -*-
"""Deterministic tool-presentation adapter for the chat agent.

This module consumes an already-built PresentationDeliveryPlan.  It does not
ask a model to rewrite acknowledgements and does not grant playback permission.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import settings_store
from src.core.presentation_delivery import (
    PresentationDeliveryPlan,
    VoiceDeliveryItem,
    build_delivery_plan,
)
from web_renderer import WebRenderer


@dataclass(frozen=True)
class ToolVoiceDeliveryBatch:
    """Backend stream output carrying voice-qualified tool presentation items."""

    items: tuple[VoiceDeliveryItem, ...]

    def __post_init__(self) -> None:
        items = tuple(self.items)
        if not items:
            raise ValueError("ToolVoiceDeliveryBatch 至少需要一条语音。")
        if any(not isinstance(item, VoiceDeliveryItem) for item in items):
            raise TypeError("items 只能包含 VoiceDeliveryItem。")
        object.__setattr__(self, "items", items)


def merge_tool_plans(
    plans: Iterable[PresentationDeliveryPlan],
) -> PresentationDeliveryPlan:
    """Merge tool plans and reapply one shared turn-level voice budget."""

    batch = tuple(plans)
    if not batch:
        raise ValueError("至少需要一个工具呈现计划。")
    if any(not isinstance(plan, PresentationDeliveryPlan) for plan in batch):
        raise TypeError("plans 只能包含 PresentationDeliveryPlan。")
    intents = tuple(
        intent for plan in batch for intent in plan.screen_intents
    )
    return build_delivery_plan(
        intents, ui_mode="user",
        speech_rate=settings_store.current().tts_speed,
    )


def render_tool_plan(plan: PresentationDeliveryPlan) -> tuple[dict, ...]:
    """Render one tool plan through the shared copy layer for screen delivery."""

    if not isinstance(plan, PresentationDeliveryPlan):
        raise TypeError("plan 必须是 PresentationDeliveryPlan。")
    return tuple(WebRenderer().render_plan(plan))


def tool_reply_text(plan: PresentationDeliveryPlan) -> str:
    """Return deterministic assistant text without consulting the chat model."""

    payloads = render_tool_plan(plan)
    texts = tuple(
        str(payload["text"]).strip()
        for payload in payloads
        if str(payload.get("text") or "").strip()
    )
    if not texts:
        raise ValueError("工具呈现计划没有可显示文案。")
    return "\n".join(texts)
