import unittest
from pathlib import Path
import sys

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from src.core.presentation_delivery import build_delivery_plan  # noqa: E402
from src.core.presentation_intent import (  # noqa: E402
    MessageKind,
    MessagePriority,
    PresentationIntent,
    ScreenTarget,
)
from tool_presentation import (  # noqa: E402
    ToolVoiceDeliveryBatch,
    merge_tool_plans,
    render_tool_plan,
    tool_reply_text,
)


def _intent(kind, args, priority, target, intent_id):
    return PresentationIntent(
        intent_id=intent_id,
        kind=kind,
        args=args,
        priority=priority,
        screen_target=target,
        source_segment_id=3,
    )


class ToolPresentationTests(unittest.TestCase):
    def test_record_ack_uses_shared_copy_and_stays_voice_silent(self):
        intent = _intent(
            MessageKind.RECORD_ACK,
            {"result": "recorded", "step_number": 2},
            MessagePriority.ROUTINE,
            ScreenTarget.RECORD_TIMELINE,
            "ack-1",
        )
        plan = build_delivery_plan((intent,), ui_mode="user")

        payloads = render_tool_plan(plan)

        self.assertEqual(payloads[0]["text"], "已记录实验步骤 2。")
        self.assertIsNone(payloads[0]["voice_text"])
        self.assertEqual(tool_reply_text(plan), "已记录实验步骤 2。")

    def test_follow_up_reply_comes_from_copy_and_delivery_plan(self):
        intent = _intent(
            MessageKind.CLARIFICATION,
            {"question": "加热了多长时间？"},
            MessagePriority.ACTIVE_QUESTION,
            ScreenTarget.CURRENT_QUESTION,
            "ask-1",
        )
        plan = build_delivery_plan((intent,), ui_mode="user")

        payloads = render_tool_plan(plan)

        self.assertEqual(payloads[0]["text"], "小科：加热了多长时间？")
        self.assertEqual(payloads[0]["voice_text"], "加热了多长时间？")
        self.assertEqual(tool_reply_text(plan), "小科：加热了多长时间？")

    def test_empty_plan_cannot_be_reported_as_successful_reply(self):
        plan = build_delivery_plan((), ui_mode="user")

        with self.assertRaisesRegex(ValueError, "没有可显示文案"):
            tool_reply_text(plan)

    def test_merge_reapplies_one_question_budget_across_plans(self):
        first = build_delivery_plan((
            _intent(
                MessageKind.CLARIFICATION,
                {"question": "温度是多少？"},
                MessagePriority.ACTIVE_QUESTION,
                ScreenTarget.CURRENT_QUESTION,
                "ask-1",
            ),
        ), ui_mode="user")
        second = build_delivery_plan((
            _intent(
                MessageKind.CLARIFICATION,
                {"question": "时间是多少？"},
                MessagePriority.ACTIVE_QUESTION,
                ScreenTarget.CURRENT_QUESTION,
                "ask-2",
            ),
        ), ui_mode="user")

        merged = merge_tool_plans((first, second))

        self.assertEqual(len(merged.screen_intents), 2)
        self.assertEqual(len(merged.voice_items), 1)
        self.assertEqual(merged.voice_items[0].intent_id, "ask-1")

    def test_voice_batch_rejects_empty_items(self):
        with self.assertRaisesRegex(ValueError, "至少需要一条"):
            ToolVoiceDeliveryBatch(())


if __name__ == "__main__":
    unittest.main()
