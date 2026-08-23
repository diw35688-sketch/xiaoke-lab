import unittest

from src.core.presentation_intent import (
    MessageKind,
    MessagePriority,
    PresentationIntent,
    ScreenTarget,
)
from src.core.voice_delivery import apply_turn_budget, constrain_voice_text


def _intent(intent_id, kind):
    return PresentationIntent(
        intent_id=intent_id,
        kind=kind,
        args={},
        priority=MessagePriority.DIRECT_ACK,
        screen_target=ScreenTarget.DIALOGUE,
    )


class VoiceDeliveryTests(unittest.TestCase):
    def test_removes_code_url_and_markdown(self):
        text = constrain_voice_text("**先看** https://example.com ```print(1)``` 再回答。")
        self.assertEqual(text, "先看 再回答。")

    def test_hard_truncation_preserves_question_shape(self):
        text = constrain_voice_text("这是一个非常非常长而且必须被确定性截断的追问内容，你能回答吗？")
        self.assertLessEqual(len(text), 25)
        self.assertTrue(text.endswith("？"))

    def test_turn_budget_is_two_items_and_fifty_chars(self):
        items = (
            (_intent("a", MessageKind.CONFIRMATION_ACK), "已确认问题一。"),
            (_intent("b", MessageKind.SYSTEM_ISSUE), "请靠近麦克风。"),
            (_intent("c", MessageKind.SYSTEM_ISSUE), "第三条不应朗读。"),
        )
        self.assertEqual(
            apply_turn_budget(items),
            ("已确认问题一。", "请靠近麦克风。", None),
        )


if __name__ == "__main__":
    unittest.main()
