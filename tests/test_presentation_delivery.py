import unittest

from src.core.presentation_delivery import (
    build_delivery_plan,
)
from src.core.presentation_intent import (
    MessageKind,
    MessagePriority,
    PresentationIntent,
    ScreenTarget,
)


def _intent(intent_id, kind, args, target=ScreenTarget.DIALOGUE):
    return PresentationIntent(
        intent_id=intent_id,
        kind=kind,
        args=args,
        priority=MessagePriority.DIRECT_ACK,
        screen_target=target,
    )


class PresentationDeliveryPlanTests(unittest.TestCase):
    def test_record_ack_stays_on_screen_but_plan_is_silent(self):
        intent = _intent(
            "record-1",
            MessageKind.RECORD_ACK,
            {"result": "recorded_no_step"},
            ScreenTarget.STATUS,
        )

        plan = build_delivery_plan((intent,), ui_mode="user")

        self.assertEqual(plan.screen_intents, (intent,))
        self.assertEqual(plan.voice_items, ())

    def test_record_ack_can_be_explicitly_spoken(self):
        intent = _intent(
            "record-1",
            MessageKind.RECORD_ACK,
            {"result": "recorded_no_step"},
            ScreenTarget.STATUS,
        )

        plan = build_delivery_plan(
            (intent,), ui_mode="user", speak_record_ack=True
        )

        self.assertEqual(plan.screen_intents, (intent,))
        self.assertEqual(plan.voice_items[0].voice_text, "本段结构化处理失败，原始记录已保存。")

    def test_record_ack_setting_does_not_speak_degraded_result(self):
        intent = _intent(
            "record-1",
            MessageKind.RECORD_ACK,
            {"result": "degraded"},
            ScreenTarget.STATUS,
        )

        plan = build_delivery_plan(
            (intent,), ui_mode="user", speak_record_ack=True
        )

        self.assertEqual(plan.screen_intents, (intent,))
        self.assertEqual(plan.voice_items, ())

    def test_question_enters_voice_items(self):
        intent = _intent(
            "ask-1",
            MessageKind.CLARIFICATION,
            {"question": "离心时间是多少？"},
            ScreenTarget.CURRENT_QUESTION,
        )

        plan = build_delivery_plan((intent,), ui_mode="user")

        self.assertEqual(plan.voice_items[0].voice_text, "离心时间是多少？")
        self.assertEqual(plan.voice_items[0].priority, MessagePriority.DIRECT_ACK)

    def test_speech_rate_passes_through_to_voice_items(self):
        intent = _intent(
            "ask-1",
            MessageKind.CLARIFICATION,
            {"question": "离心时间是多少？"},
            ScreenTarget.CURRENT_QUESTION,
        )

        plan = build_delivery_plan(
            (intent,), ui_mode="user", speech_rate=1.2
        )

        self.assertEqual(plan.voice_items[0].speech_rate, 1.2)

    def test_plan_exposes_no_playback_timing_decision(self):
        intent = _intent(
            "ask-1", MessageKind.CLARIFICATION,
            {"question": "离心时间是多少？"},
            ScreenTarget.CURRENT_QUESTION,
        )
        plan = build_delivery_plan((intent,), ui_mode="user")
        self.assertFalse(hasattr(plan, "voice_disposition"))
        self.assertFalse(hasattr(plan, "playback_window"))

    def test_plan_enforces_one_question_budget(self):
        intents = tuple(
            _intent(
                f"ask-{index}",
                MessageKind.CLARIFICATION,
                {"question": question},
                ScreenTarget.CURRENT_QUESTION,
            )
            for index, question in enumerate(("温度是多少？", "时间是多少？"), 1)
        )

        plan = build_delivery_plan(intents, ui_mode="user")

        self.assertEqual(len(plan.screen_intents), 2)
        self.assertEqual(len(plan.voice_items), 1)
        self.assertEqual(plan.voice_items[0].voice_text, "温度是多少？")


if __name__ == "__main__":
    unittest.main()
