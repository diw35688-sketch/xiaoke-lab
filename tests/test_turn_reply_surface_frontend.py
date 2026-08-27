import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class TurnReplySurfaceFrontendTests(unittest.TestCase):
    def test_streaming_chat_has_safe_fallback_when_helper_script_is_absent(self):
        source = (ROOT / "web/frontend/streaming_chat_v2.js").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "typeof window.settleTurnReplySurface === 'function'", source
        )
        self.assertIn("messageRow(reply)?.remove?.()", source)
        self.assertIn(
            "settleCommittedReply(reply, assistant, publishAnswer)", source
        )

    def test_normal_page_loads_helper_before_streaming_chat(self):
        source = (ROOT / "web/app.py").read_text(encoding="utf-8")
        self.assertLess(
            source.index("turn_reply_surface.js"),
            source.index("streaming_chat_v2.js"),
        )


if __name__ == "__main__":
    unittest.main()
