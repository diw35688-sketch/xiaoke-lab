# -*- coding: utf-8 -*-
"""web/web_renderer.py 渲染器单测：不依赖网络与真实服务。

覆盖：意图 → JSON 的字段映射（kind/screen_target/priority/text/voice_text/source_segment_id）、
priority 转 int 保证 JSON 可序列化、admin 模式追加来源、copy 不支持的 kind 明确抛错、
以及"降级生产者 → 投影 → WebRenderer"全链路。
"""

import json
import sys
import unittest
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

import degraded_producer  # noqa: E402
import web_renderer  # noqa: E402
from src.core.presentation_copy import RecordAckResult  # noqa: E402
from src.core.presentation_delivery import build_delivery_plan  # noqa: E402
from src.core.presentation_intent import (  # noqa: E402
    MessageKind,
    MessagePriority,
    PresentationIntent,
    ScreenTarget,
)
from src.core.presentation_projection import messages_for_observation  # noqa: E402


def _intent(kind, **overrides):
    defaults = {
        "intent_id": "web-test-1",
        "kind": kind,
        "args": {},
        "priority": MessagePriority.ROUTINE,
        "screen_target": ScreenTarget.STATUS,
    }
    defaults.update(overrides)
    return PresentationIntent(**defaults)


class WebRendererFieldTests(unittest.TestCase):
    """意图 → JSON 字段映射。"""

    def test_clarification_intent_renders_expected_fields(self):
        intent = _intent(
            MessageKind.CLARIFICATION,
            args={"question": "缺时长，请补充"},
            priority=MessagePriority.ACTIVE_QUESTION,
            screen_target=ScreenTarget.CURRENT_QUESTION,
            source_segment_id=3,
        )
        payload = web_renderer.WebRenderer().render(intent)
        self.assertEqual(payload["intent_id"], "web-test-1")
        self.assertEqual(payload["kind"], "clarification")
        self.assertEqual(payload["screen_target"], "current_question")
        self.assertEqual(payload["priority"], 20)  # ACTIVE_QUESTION
        self.assertEqual(payload["source_segment_id"], 3)
        self.assertEqual(payload["text"], "小科：缺时长，请补充")
        self.assertEqual(payload["voice_text"], "缺时长，请补充")

    def test_record_ack_degraded_renders_text(self):
        intent = _intent(
            MessageKind.RECORD_ACK,
            args={"result": RecordAckResult.DEGRADED},
        )
        payload = web_renderer.WebRenderer().render(intent)
        self.assertEqual(payload["kind"], "record_ack")
        self.assertEqual(payload["text"], "原始记录已保存，结构化处理暂时不可用。")
        self.assertIsNone(payload["voice_text"])

    def test_clarification_voice_text_drops_prefix(self):
        intent = _intent(
            MessageKind.CLARIFICATION,
            args={"question": "缺时长，请补充"},
            priority=MessagePriority.ACTIVE_QUESTION,
            screen_target=ScreenTarget.CURRENT_QUESTION,
        )
        payload = web_renderer.WebRenderer().render(intent)
        self.assertEqual(payload["text"], "小科：缺时长，请补充")
        self.assertEqual(payload["voice_text"], "缺时长，请补充")

    def test_record_ack_recorded_renders_step_text(self):
        intent = _intent(
            MessageKind.RECORD_ACK,
            args={"result": RecordAckResult.RECORDED, "step_number": 3},
        )
        payload = web_renderer.WebRenderer().render(intent)
        self.assertEqual(payload["text"], "已记录实验步骤 3。")

    def test_priority_is_int_for_json(self):
        intent = _intent(
            MessageKind.RECORD_ACK,
            args={"result": RecordAckResult.DEGRADED},
        )
        payload = web_renderer.WebRenderer().render(intent)
        self.assertIsInstance(payload["priority"], int)

    def test_source_segment_id_none_when_missing(self):
        intent = _intent(
            MessageKind.RECORD_ACK,
            args={"result": RecordAckResult.DEGRADED},
        )
        payload = web_renderer.WebRenderer().render(intent)
        self.assertIsNone(payload["source_segment_id"])

    def test_payload_is_json_serializable(self):
        intent = _intent(
            MessageKind.CLARIFICATION,
            args={"question": "缺时长，请补充"},
        )
        payload = web_renderer.WebRenderer().render(intent)
        json.dumps(payload)  # 不抛即通过

    def test_admin_mode_appends_source(self):
        intent = _intent(
            MessageKind.RECORD_ACK,
            args={"result": RecordAckResult.DEGRADED},
            source_segment_id=5,
        )
        payload = web_renderer.WebRenderer(ui_mode="admin").render(intent)
        self.assertIn("来源口述 5", payload["text"])

    def test_unsupported_kind_raises_value_error(self):
        intent = _intent(MessageKind.SAFETY_ALERT)
        with self.assertRaises(ValueError):
            web_renderer.WebRenderer().render(intent)

    def test_voice_text_is_filtered_and_hard_limited(self):
        intent = _intent(
            MessageKind.CLARIFICATION,
            args={"question": "请查看 https://example.com 和 `duration` 字段后告诉我需要离心多长时间？"},
            priority=MessagePriority.ACTIVE_QUESTION,
            screen_target=ScreenTarget.CURRENT_QUESTION,
        )
        payload = web_renderer.WebRenderer().render(intent)
        self.assertNotIn("http", payload["voice_text"])
        self.assertNotIn("`", payload["voice_text"])
        self.assertLessEqual(len(payload["voice_text"]), 25)

    def test_render_many_allows_only_one_question(self):
        intents = [
            _intent(
                MessageKind.CLARIFICATION,
                intent_id=f"q-{index}",
                args={"question": question},
                priority=MessagePriority.ACTIVE_QUESTION,
                screen_target=ScreenTarget.CURRENT_QUESTION,
            )
            for index, question in enumerate(("温度是多少？", "时间是多少？"), 1)
        ]
        payloads = web_renderer.WebRenderer().render_many(intents)
        self.assertEqual(payloads[0]["voice_text"], "温度是多少？")
        self.assertIsNone(payloads[1]["voice_text"])

    def test_render_plan_only_uses_preselected_voice_items(self):
        intents = (
            _intent(
                MessageKind.RECORD_ACK,
                intent_id="record-1",
                args={"result": RecordAckResult.RECORDED_NO_STEP},
            ),
            _intent(
                MessageKind.CLARIFICATION,
                intent_id="ask-1",
                args={"question": "时间是多少？"},
                priority=MessagePriority.ACTIVE_QUESTION,
                screen_target=ScreenTarget.CURRENT_QUESTION,
            ),
        )
        plan = build_delivery_plan(intents, ui_mode="user")

        payloads = web_renderer.WebRenderer().render_plan(plan)

        self.assertEqual(payloads[0]["text"], "已记录。")
        self.assertIsNone(payloads[0]["voice_text"])
        self.assertEqual(payloads[1]["voice_text"], "时间是多少？")


class WebRendererChainTests(unittest.TestCase):
    """降级生产者 → 投影 → WebRenderer 全链路。"""

    def test_followup_chain_produces_clarification_json(self):
        observation = degraded_producer.produce_partial_observation(
            request_id="web-1",
            session_id="s",
            segment_id=2,
            evaluation={
                "follow_up_question": "缺时长，请补充",
                "missing_fields": ["duration"],
            },
        )
        messages = messages_for_observation(observation)
        payloads = [web_renderer.WebRenderer().render(m) for m in messages]
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]["kind"], "clarification")
        self.assertEqual(payloads[0]["screen_target"], "current_question")
        self.assertEqual(payloads[0]["text"], "小科：缺时长，请补充")
        self.assertEqual(payloads[0]["voice_text"], "缺时长，请补充")

    def test_record_chain_produces_degraded_json(self):
        observation = degraded_producer.produce_partial_observation(
            request_id="web-1",
            session_id="s",
            segment_id=2,
            evaluation={},
        )
        messages = messages_for_observation(observation)
        payloads = [web_renderer.WebRenderer().render(m) for m in messages]
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]["kind"], "record_ack")
        self.assertEqual(payloads[0]["text"], "原始记录已保存，结构化处理暂时不可用。")


if __name__ == "__main__":
    unittest.main()
