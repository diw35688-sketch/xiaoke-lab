# -*- coding: utf-8 -*-
"""web 渲染器：把呈现意图（PresentationIntent）渲染成前端可消费的结构化 JSON。

三层呈现链的 web 形态：投影层产出"意图"（不含中文），本渲染器把意图变成
前端要的字典——kind/screen_target/priority 供前端上样式与排序，text 是
copy 层生成的最终话（显示 + TTS 朗读）。前端只消费这些字段，不做二次判断
（契约 4/5：前端只画不判，词在后端）。

注意：不实现 CLI pump 的 Renderer 协议（render -> str 给终端），
产出物是 dict（JSON 可序列化），供 web 前端直接消费。
"""

from __future__ import annotations

import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    REPO_ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
else:
    REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.presentation_copy import copy_for_intent  # noqa: E402
from src.core.presentation_delivery import (  # noqa: E402
    PresentationDeliveryPlan,
    build_delivery_plan,
)
from src.core.presentation_intent import PresentationIntent  # noqa: E402


class WebRenderer:
    """意图 → 结构化 JSON；ui_mode 决定文案面向用户还是管理员。"""

    def __init__(self, ui_mode: str = "user") -> None:
        self._ui_mode = ui_mode

    def render(self, intent: PresentationIntent) -> dict:
        """通过统一 DeliveryPlan 渲染一条意图。"""

        return self.render_many((intent,))[0]

    def _render_screen(self, intent: PresentationIntent) -> dict:
        """只渲染屏幕字段，不判断或生成语音内容。

        字段：intent_id（追踪）、kind/screen_target（上样式）、
        priority（排序，转 int 保证 JSON 可序列化）、
        source_segment_id（来源口述，可空）、text（copy 层显示话）。
        args 不透传：前端不应拿意图参数做二次判断。
        """
        return {
            "intent_id": intent.intent_id,
            "kind": intent.kind.value,
            "screen_target": intent.screen_target.value,
            "priority": int(intent.priority),
            "source_segment_id": intent.source_segment_id,
            "text": copy_for_intent(intent, ui_mode=self._ui_mode),
            "voice_text": None,
        }

    def render_many(self, intents) -> list[dict]:
        """先构建统一内容计划，再渲染为 Web JSON。"""

        plan = build_delivery_plan(tuple(intents), ui_mode=self._ui_mode)
        return self.render_plan(plan)

    def render_plan(self, plan: PresentationDeliveryPlan) -> list[dict]:
        """消费已构建的内容计划；不重新执行任何语音政策。"""

        if not isinstance(plan, PresentationDeliveryPlan):
            raise TypeError("plan 必须是 PresentationDeliveryPlan。")
        voice_by_intent_id = {
            item.intent_id: item.voice_text for item in plan.voice_items
        }
        payloads = [
            self._render_screen(intent) for intent in plan.screen_intents
        ]
        for payload in payloads:
            payload["voice_text"] = voice_by_intent_id.get(
                payload["intent_id"]
            )
        return payloads
