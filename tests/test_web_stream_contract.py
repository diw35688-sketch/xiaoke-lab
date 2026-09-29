import sys
import unittest
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from stream_contract import (  # noqa: E402
    VoiceDeliveryItem,
    agent_chunk_event,
    agent_output_event,
    screen_delta_event,
    voice_delivery_event,
)
from tool_presentation import ToolVoiceDeliveryBatch  # noqa: E402
from src.core.presentation_intent import MessageKind, MessagePriority  # noqa: E402


def _voice(intent_id, kind, text):
    return VoiceDeliveryItem(
        intent_id=intent_id,
        kind=kind,
        priority=MessagePriority.DIRECT_ACK,
        voice_text=text,
    )


class ScreenDeltaContractTests(unittest.TestCase):
    def test_screen_delta_contains_no_voice_permission(self):
        event = screen_delta_event("模型正在流式回答")
        self.assertEqual(
            event,
            {"type": "screen_delta", "text": "模型正在流式回答"},
        )
        self.assertNotIn("voice_text", event)

    def test_screen_delta_rejects_empty_text(self):
        with self.assertRaisesRegex(ValueError, "非空字符串"):
            screen_delta_event("")

    def test_ordinary_agent_chunk_is_explicitly_screen_only(self):
        event = agent_chunk_event("已记录实验步骤 2。")

        self.assertEqual(
            event,
            {"type": "screen_delta", "text": "已记录实验步骤 2。"},
        )
        self.assertNotIn("voice_text", event)

    def test_legacy_control_markers_stay_out_of_screen_delta(self):
        think = agent_chunk_event("[[LABTHINK]]分析中")
        card = agent_chunk_event("[[LABCARD]]{}")

        self.assertEqual(think["type"], "delta")
        self.assertEqual(card["type"], "delta")

    def test_agent_chunk_rejects_empty_text(self):
        with self.assertRaisesRegex(ValueError, "非空字符串"):
            agent_chunk_event("")


class VoiceDeliveryContractTests(unittest.TestCase):
    def test_assistant_reply_is_voice_eligible_and_preserved(self):
        from src.core.presentation_delivery import build_delivery_plan
        from src.core.presentation_intent import PresentationIntent, ScreenTarget

        plan = build_delivery_plan((PresentationIntent(
            intent_id="chat-reply-1",
            kind=MessageKind.ASSISTANT_REPLY,
            args={"text": "这是普通聊天回复，应在完整回答后交给播放调度器。第二句保留在屏幕。"},
            priority=MessagePriority.REVIEW,
            screen_target=ScreenTarget.DIALOGUE,
        ),), ui_mode="user")

        self.assertEqual(len(plan.voice_items), 1)
        self.assertEqual(plan.voice_items[0].kind, MessageKind.ASSISTANT_REPLY)
        self.assertEqual(plan.voice_items[0].priority, MessagePriority.REVIEW)
        # 不再截断——完整保留回复文本
        self.assertTrue(plan.voice_items[0].voice_text.endswith("。"))
        self.assertIn("第二句", plan.voice_items[0].voice_text)

    def test_serializes_explicit_voice_permission(self):
        event = voice_delivery_event((
            _voice("ack-1", MessageKind.CONFIRMATION_ACK, "已确认问题一。"),
            _voice("ask-1", MessageKind.CLARIFICATION, "离心时间是多少？"),
        ))
        self.assertEqual(event["type"], "voice_delivery")
        self.assertEqual(event["authorization"], "CONTENT_ELIGIBLE")
        self.assertEqual(len(event["items"]), 2)
        self.assertEqual(event["items"][1]["kind"], "clarification")
        self.assertEqual(event["items"][1]["priority"], "DIRECT_ACK")
        self.assertEqual(event["items"][1]["voice_text"], "离心时间是多少？")
        self.assertNotIn("text", event["items"][1])

    def test_serializes_scheduler_authorization_and_reason(self):
        event = voice_delivery_event(
            (_voice("ask-1", MessageKind.CLARIFICATION, "离心时间是多少？"),),
            authorization="READY",
            reason="playback_window_open",
        )

        self.assertEqual(event["authorization"], "READY")
        self.assertEqual(event["reason"], "playback_window_open")

    def test_rejects_unknown_scheduler_authorization(self):
        with self.assertRaisesRegex(ValueError, "authorization"):
            voice_delivery_event(
                (_voice("ask-1", MessageKind.CLARIFICATION, "离心时间是多少？"),),
                authorization="PLAY_NOW",
            )

    def test_accepts_more_than_two_items(self):
        """语音预算已放宽，不再限制最多 2 条。"""
        items = tuple(
            _voice(f"issue-{index}", MessageKind.SYSTEM_ISSUE, "请重试。")
            for index in range(3)
        )
        event = voice_delivery_event(items)
        self.assertEqual(len(event["items"]), 3)

    def test_accepts_multiple_questions(self):
        """不再限制最多一个问题——模型可以连续追问。"""
        items = (
            _voice("ask-1", MessageKind.CLARIFICATION, "温度是多少？"),
            _voice("ask-2", MessageKind.CLARIFICATION, "时间是多少？"),
        )
        event = voice_delivery_event(items)
        self.assertEqual(len(event["items"]), 2)

    def test_accepts_long_voice_text(self):
        """单条语音不再限制 25 字——长回复完整交给 TTS。"""
        long_text = "请确认以下步骤是否正确执行：" + "步骤描述内容。" * 5
        item = _voice("ask-1", MessageKind.CLARIFICATION, long_text)
        self.assertEqual(item.voice_text, long_text)

    def test_rejects_empty_delivery(self):
        with self.assertRaisesRegex(ValueError, "至少需要一条"):
            voice_delivery_event(())

    def test_typed_agent_voice_batch_maps_to_delivery_event(self):
        batch = ToolVoiceDeliveryBatch((
            _voice("ask-1", MessageKind.CLARIFICATION, "离心时间是多少？"),
        ))

        event = agent_output_event(batch)

        self.assertEqual(event["type"], "voice_delivery")
        self.assertEqual(event["authorization"], "CONTENT_ELIGIBLE")
        self.assertEqual(event["items"][0]["intent_id"], "ask-1")
        self.assertNotIn("text", event)

    def test_agent_output_rejects_unknown_type(self):
        with self.assertRaisesRegex(TypeError, "类型不受支持"):
            agent_output_event({"text": "not typed"})


if __name__ == "__main__":
    unittest.main()
