import sys
import unittest
from pathlib import Path
from unittest.mock import patch

WEB = Path(__file__).resolve().parent.parent / "web"
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

from api.chat import (  # noqa: E402
    _build_chat_spoken_delivery,
    _prepare_chat_spoken_delivery,
)


class ChatSpokenProductionTests(unittest.TestCase):
    def test_delivery_text_exactly_matches_visible_spoken_block_contract(self):
        text = "人工智能让机器通过数据完成感知、判断和生成任务。"

        item = _build_chat_spoken_delivery(text, "turn-chat-1")

        self.assertEqual(item.voice_text, text)
        self.assertEqual(item.source_block_id, "turn-chat-1:spoken")
        self.assertEqual(item.max_chars, 50)

    def test_over_budget_chat_is_rejected_before_delivery_without_truncation(self):
        text = "甲" * 51

        with self.assertRaisesRegex(ValueError, "禁止截断"):
            _build_chat_spoken_delivery(text, "turn-chat-2")

    @patch("api.chat.refine_chat_answer")
    def test_over_budget_chat_is_regenerated_before_screen_and_voice_publish(
        self, refine
    ):
        original = "甲" * 51
        refine.return_value = "这是一句重新生成的完整短回复。"

        visible, item = _prepare_chat_spoken_delivery(original, "turn-chat-3")

        refine.assert_called_once_with(original, max_chars=50)
        self.assertEqual(visible, refine.return_value)
        self.assertEqual(item.voice_text, visible)
        self.assertEqual(item.source_block_id, "turn-chat-3:spoken")

    @patch("api.chat.refine_chat_answer")
    def test_refinement_is_still_rejected_if_model_ignores_budget(self, refine):
        refine.return_value = "乙" * 51

        with self.assertRaisesRegex(ValueError, "禁止截断"):
            _prepare_chat_spoken_delivery("甲" * 51, "turn-chat-4")

    def test_frontend_uses_same_spoken_block_for_visible_chat_text(self):
        source = (WEB / "frontend" / "streaming_chat_v2.js").read_text(
            encoding="utf-8"
        )

        # The frontend creates an optimistic assistant block before the
        # committed turn arrives; the backend's spoken-block plan replaces it.
        self.assertIn("`${localTurnId}:assistant`", source)
        self.assertIn("type: 'assistant_text'", source)


if __name__ == "__main__":
    unittest.main()
