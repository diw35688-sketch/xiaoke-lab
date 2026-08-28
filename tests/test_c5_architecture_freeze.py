import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "src" / "core"
WEB = ROOT / "web"
FRONTEND = WEB / "frontend"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class C5ArchitectureFreezeTests(unittest.TestCase):
    """Executable ownership rules for the completed C5 delivery pipeline."""

    def test_delivery_plan_has_no_runtime_or_tts_dependency(self):
        source = _source(CORE / "presentation_delivery.py")

        for forbidden in (
            "playback_gate",
            "playback_scheduler",
            "voice_runtime_state",
            "tts_adapter",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_playback_gate_remains_a_pure_decision_boundary(self):
        source = _source(CORE / "playback_gate.py")

        self.assertIn("return decide_playback(request, context)", source)
        self.assertNotIn("DeferredPlaybackQueue", source)
        self.assertNotIn("TTSAdapter", source)
        self.assertNotIn(".play(", source)
        self.assertNotIn(".stop(", source)

    def test_web_producers_share_scheduler_adapter_and_never_call_tts(self):
        record = _source(WEB / "api" / "record.py")
        chat = _source(WEB / "api" / "chat.py")

        self.assertIn("web_playback_service.authorize(", record)
        self.assertIn("completed.voice_items", record)
        self.assertIn("conversation_id=", record)
        self.assertIn("web_playback_service.authorize(", chat)
        self.assertIn("completed.voice_items", chat)
        self.assertIn("turn_application_service.submit(turn)", chat)
        self.assertIn("conversation_id=conversation_id", chat)
        for source in (record, chat):
            with self.subTest(source=source[:20]):
                self.assertNotIn("enqueueSpeech", source)
                self.assertNotIn("window.speak", source)
                self.assertNotIn("TTSAdapter", source)

    def test_stream_clients_have_no_text_or_done_tts_bypass(self):
        for name in ("streaming_chat_v2.js", "streaming_chat.js"):
            source = _source(FRONTEND / name)
            with self.subTest(name=name):
                self.assertIn("consumeVoiceDelivery?.(data)", source)
                self.assertNotIn("enqueueSpeech", source)
                self.assertNotIn("speechBuffer", source)
                self.assertNotIn("takeCompletedSentences", source)

    def test_record_clients_do_not_speak_from_messages(self):
        desktop = _source(FRONTEND / "voice_asr.js")
        mobile = _source(FRONTEND / "mobile.js")

        for source in (desktop, mobile):
            self.assertIn("consumeVoiceDelivery?.(", source)
            self.assertNotIn("labSpeakMessages(d.messages", source)
            self.assertNotIn("if (m.voice_text)", source)

    def test_only_authorized_voice_client_executes_migration_playback(self):
        client = _source(FRONTEND / "voice_delivery_client.js")

        self.assertIn("authorization !== 'READY'", client)
        self.assertIn("authorization !== 'PREEMPT'", client)
        self.assertIn("window.enqueueSpeech", client)
        self.assertIn("window.stopSpeech", client)

    def test_background_task_notification_is_an_explicit_separate_exception(self):
        task_panel = _source(FRONTEND / "task_panel.js")

        self.assertIn("deliverResults", task_panel)
        self.assertIn("window.enqueueSpeech?.(text)", task_panel)


if __name__ == "__main__":
    unittest.main()
