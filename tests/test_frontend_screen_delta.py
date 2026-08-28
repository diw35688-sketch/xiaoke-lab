import unittest
from pathlib import Path


FRONTEND = (
    Path(__file__).resolve().parent.parent
    / "web"
    / "frontend"
    / "streaming_chat_v2.js"
)
LEGACY_FRONTEND = FRONTEND.with_name("streaming_chat.js")
TASK_PANEL = FRONTEND.with_name("task_panel.js")
VOICE_CLIENT = FRONTEND.with_name("voice_delivery_client.js")
APP = FRONTEND.parent.parent / "app.py"
CHAT_API = Path(__file__).resolve().parent.parent / "web" / "api" / "chat.py"
RECORD_API = CHAT_API.with_name("record.py")
VOICE_ASR = FRONTEND.with_name("voice_asr.js")
MOBILE = FRONTEND.with_name("mobile.js")
MOBILE_HTML = FRONTEND.with_name("mobile.html")


class FrontendScreenDeltaTests(unittest.TestCase):
    def test_screen_delta_branch_only_updates_screen(self):
        source = FRONTEND.read_text(encoding="utf-8")
        start = source.index("data.type === 'screen_delta'")
        end = source.index("data.type === 'delta'", start)
        branch = source[start:end]

        self.assertIn("publishAnswer(answer)", branch)
        self.assertNotIn("enqueueSpeech", branch)
        self.assertNotIn("window.speak", branch)

    def test_delta_branch_keeps_display_but_has_no_direct_tts(self):
        source = FRONTEND.read_text(encoding="utf-8")
        start = source.index("data.type === 'delta'")
        end = source.index("data.type === 'task_queued'", start)
        delta_branch = source[start:end]

        self.assertIn("publishAnswer(answer)", delta_branch)
        self.assertNotIn("enqueueSpeech", delta_branch)
        self.assertNotIn("window.speak", delta_branch)

    def test_inactive_legacy_file_cannot_restore_delta_tts(self):
        source = LEGACY_FRONTEND.read_text(encoding="utf-8")
        start = source.index("data.type === 'delta'")
        end = source.index("data.type === 'task_queued'", start)
        delta_branch = source[start:end]

        self.assertIn("reply.textContent = answer", delta_branch)
        self.assertNotIn("enqueueSpeech", delta_branch)

    def test_task_queued_stays_visible_without_direct_tts(self):
        source = FRONTEND.read_text(encoding="utf-8")
        start = source.index("data.type === 'task_queued'")
        end = source.index("data.type === 'done'", start)
        branch = source[start:end]

        self.assertIn("publishAnswer(answer)", branch)
        self.assertIn("localStorage.setItem", branch)
        self.assertIn("avatar('listening')", branch)
        self.assertIn("refreshTaskPanel", branch)
        self.assertNotIn("enqueueSpeech", branch)
        self.assertNotIn("window.speak", branch)

    def test_inactive_legacy_task_queued_cannot_restore_tts(self):
        source = LEGACY_FRONTEND.read_text(encoding="utf-8")
        start = source.index("data.type === 'task_queued'")
        end = source.index("data.type === 'done'", start)
        branch = source[start:end]

        self.assertIn("reply.textContent = answer", branch)
        self.assertIn("refreshTaskPanel", branch)
        self.assertNotIn("enqueueSpeech", branch)

    def test_background_task_result_tts_is_outside_this_item(self):
        source = TASK_PANEL.read_text(encoding="utf-8")

        self.assertIn("deliverResults", source)
        self.assertIn("window.enqueueSpeech?.(text)", source)

    def test_legacy_chat_routes_through_unified_turn_service(self):
        source = CHAT_API.read_text(encoding="utf-8")

        self.assertIn("from api.turn import turn_application_service", source)
        self.assertIn("turn_application_service.submit(turn).future.result()", source)
        self.assertNotIn("add_message(conversation_id, \"user\"", source)

    def test_legacy_chat_voice_uses_shared_playback_service(self):
        source = CHAT_API.read_text(encoding="utf-8")
        self.assertIn("web_playback_service.authorize(", source)
        self.assertIn("completed.voice_items", source)
        self.assertIn("conversation_id=conversation_id", source)
        self.assertIn("if not completed.replayed", source)

    def test_plain_chat_compatibility_returns_final_screen_delta(self):
        source = CHAT_API.read_text(encoding="utf-8")

        self.assertIn("screen_delta_event(answer)", source)
        self.assertIn("_assistant_text(completed.result)", source)

    def test_record_voice_uses_the_same_shared_playback_service(self):
        source = RECORD_API.read_text(encoding="utf-8")
        self.assertIn("web_playback_service.authorize(", source)
        self.assertIn("completed.voice_items", source)
        self.assertIn("conversation_id=", source)

    def test_record_frontends_only_consume_scheduler_events(self):
        desktop = VOICE_ASR.read_text(encoding="utf-8")
        mobile = MOBILE.read_text(encoding="utf-8")
        mobile_html = MOBILE_HTML.read_text(encoding="utf-8")
        self.assertIn("consumeVoiceDelivery?.(", desktop)
        self.assertNotIn("labSpeakMessages(d.messages", desktop)
        self.assertIn("consumeVoiceDelivery?.(", mobile)
        self.assertNotIn("if (m.voice_text)", mobile)
        self.assertLess(mobile_html.index("voice_delivery_client.js"), mobile_html.index("mobile.js"))

    def test_record_frontends_stream_status_before_final_result(self):
        desktop = VOICE_ASR.read_text(encoding="utf-8")
        mobile = MOBILE.read_text(encoding="utf-8")
        for source in (desktop, mobile):
            self.assertIn("/record/stream", source)
            self.assertIn("record_status", source)
            self.assertIn("record_result", source)
            self.assertIn("response.body.getReader()", source)

    def test_stream_clients_delegate_voice_events_to_shared_boundary(self):
        active = FRONTEND.read_text(encoding="utf-8")
        legacy = LEGACY_FRONTEND.read_text(encoding="utf-8")

        self.assertIn("data.type === 'voice_delivery'", active)
        self.assertIn("consumeVoiceDelivery?.(data)", active)
        self.assertIn("data.type === 'voice_delivery'", legacy)
        self.assertIn("consumeVoiceDelivery?.(data)", legacy)

    def test_voice_client_is_loaded_before_active_stream_consumer(self):
        source = APP.read_text(encoding="utf-8")

        voice_index = source.index("voice_delivery_client.js")
        stream_index = source.index("streaming_chat_v2.js")
        self.assertLess(voice_index, stream_index)

    def test_voice_client_only_authorizes_ready_and_preempt(self):
        source = VOICE_CLIENT.read_text(encoding="utf-8")

        self.assertIn("authorization === 'CONTENT_ELIGIBLE'", source)
        self.assertIn("authorization === 'DEFERRED'", source)
        self.assertIn("authorization === 'DROP'", source)
        self.assertIn("authorization !== 'READY'", source)
        self.assertIn("authorization !== 'PREEMPT'", source)


if __name__ == "__main__":
    unittest.main()
