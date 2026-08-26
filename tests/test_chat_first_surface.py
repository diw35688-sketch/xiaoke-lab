import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "web" / "frontend"
APP = ROOT / "web" / "app.py"


class ChatFirstSurfaceTests(unittest.TestCase):
    def test_block_view_and_context_adapters_load_before_stream(self):
        source = APP.read_text(encoding="utf-8")
        stream = source.index("streaming_chat_v2.js")
        self.assertLess(source.index("conversation_block_view.js"), stream)
        self.assertLess(source.index("conversation_context_blocks.js"), stream)

    def test_all_card_types_have_one_view_adapter(self):
        source = (FRONTEND / "conversation_block_view.js").read_text(encoding="utf-8")
        for block_type in (
            "protocol_card", "step_card", "safety_alert", "record_card",
            "tool_card", "confirmation_card", "system_status",
        ):
            with self.subTest(block_type=block_type):
                self.assertIn(f"case '{block_type}'", source)
        self.assertEqual(source.count("function conversationBlockView"), 1)

    def test_protocol_facts_become_timeline_blocks(self):
        source = (FRONTEND / "conversation_context_blocks.js").read_text(encoding="utf-8")
        self.assertIn("/protocols/session/steps", source)
        self.assertIn("type: 'protocol_card'", source)
        self.assertIn("type: 'step_card'", source)
        self.assertIn("type: 'safety_alert'", source)

    def test_record_result_becomes_record_and_confirmation_blocks(self):
        adapter = (FRONTEND / "conversation_context_blocks.js").read_text(encoding="utf-8")
        recorder = (FRONTEND / "voice_asr.js").read_text(encoding="utf-8")
        self.assertIn("type: 'record_card'", adapter)
        self.assertIn("type: 'confirmation_card'", adapter)
        self.assertIn("beginRecordSurface", recorder)
        self.assertIn("publishRecordSurface", recorder)

    def test_chat_subscriber_uses_shared_card_skeleton(self):
        source = (FRONTEND / "streaming_chat_v2.js").read_text(encoding="utf-8")
        self.assertIn("function ensureCardRow", source)
        self.assertIn("blockView?.(block)", source)
        self.assertIn('class="chat-block"', source)
        self.assertNotIn("if (!turn || !activeReply) return", source)

    def test_realtime_run_canvas_is_no_longer_loaded(self):
        source = APP.read_text(encoding="utf-8")
        self.assertNotIn('/static/run_canvas.js', source)

    def test_legacy_lab_panel_is_no_longer_a_second_record_surface(self):
        app = APP.read_text(encoding="utf-8")
        recorder = (FRONTEND / "voice_asr.js").read_text(encoding="utf-8")
        self.assertNotIn('/static/lab_panel.js', app)
        self.assertNotIn('window.labRender', recorder)
        self.assertEqual(recorder.count('window.publishRecordSurface?.(d)'), 1)

    def test_shell_defaults_to_one_chat_surface(self):
        source = (FRONTEND / "shell.js").read_text(encoding="utf-8")
        self.assertNotIn('data-view="run"', source)
        self.assertIn('data-view="chat"', source)
        self.assertIn("var current = 'chat'", source)
        self.assertIn("show('chat')", source)
        self.assertIn("shell.classList.toggle('chat-view', isChat)", source)
        self.assertIn("if (isChat) return", source)
        self.assertNotIn("sh-toggle-chat", source)

    def test_chat_and_management_are_mutually_exclusive(self):
        source = (FRONTEND / "shell.js").read_text(encoding="utf-8")
        self.assertIn("#sh-chat{flex:1;background:var(--n-00);display:none", source)
        self.assertIn("#shell.chat-view #sh-center{display:none}", source)
        self.assertIn("#shell.chat-view #sh-chat{display:flex}", source)

    def test_management_pages_remain_available(self):
        source = (FRONTEND / "shell.js").read_text(encoding="utf-8")
        for view in ("protocols", "reagents", "records", "settings"):
            self.assertIn(f'data-view="{view}"', source)


if __name__ == "__main__":
    unittest.main()
