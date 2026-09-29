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

    def test_constrain_preserves_full_text_and_shape(self):
        """constrain_voice_text 只去掉代码/URL/Markdown，不再硬截断长度。"""
        text = constrain_voice_text("这是一个非常非常长的追问内容，你能回答吗？")
        # 不截断——完整保留
        self.assertTrue(text.endswith("？"))
        self.assertIn("追问内容", text)

    def test_turn_budget_passes_through_all_speakable_items(self):
        """apply_turn_budget 不再限制条数，全部保留。"""
        items = (
            (_intent("a", MessageKind.CONFIRMATION_ACK), "已确认问题一。"),
            (_intent("b", MessageKind.SYSTEM_ISSUE), "请靠近麦克风。"),
            (_intent("c", MessageKind.SYSTEM_ISSUE), "第三条也朗读。"),
        )
        self.assertEqual(
            apply_turn_budget(items),
            ("已确认问题一。", "请靠近麦克风。", "第三条也朗读。"),
        )


if __name__ == "__main__":
    unittest.main()
