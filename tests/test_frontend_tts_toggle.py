import unittest
from pathlib import Path


FRONTEND = Path(__file__).resolve().parent.parent / "web" / "frontend"


class FrontendTtsToggleTests(unittest.TestCase):
    def test_persistent_tts_setting_has_one_owner(self):
        model_settings = (FRONTEND / "settings.js").read_text(encoding="utf-8")
        tts_settings = (FRONTEND / "tts_settings.js").read_text(encoding="utf-8")

        self.assertNotIn("settings-tts", model_settings)
        self.assertNotIn("tts_enabled:", model_settings)
        self.assertIn('id="tts-enabled"', tts_settings)
        self.assertIn("tts_enabled: el('tts-enabled').checked", tts_settings)
        self.assertIn('id="speak-record-ack"', tts_settings)
        self.assertIn("speak_record_ack: el('speak-record-ack').checked", tts_settings)

    def test_saved_tts_setting_updates_runtime_flag(self):
        source = (FRONTEND / "tts_settings.js").read_text(encoding="utf-8")

        self.assertIn("window.ttsEnabled = !!payload().tts_enabled", source)

    def test_avatar_mute_remains_an_immediate_local_override(self):
        avatar = (FRONTEND / "avatar.js").read_text(encoding="utf-8")
        player = (FRONTEND / "local_tts.js").read_text(encoding="utf-8")
        client = (FRONTEND / "voice_delivery_client.js").read_text(encoding="utf-8")

        self.assertIn("window.ttsMuted = !(window.ttsMuted === true)", avatar)
        self.assertIn("if (window.ttsMuted) window.stopSpeech?.()", avatar)
        self.assertIn("event.target.closest('button, input, select, textarea, a')", avatar)
        self.assertIn("if (window.ttsMuted === true) return", player)
        self.assertIn("if (window.ttsMuted === true) return false", client)


if __name__ == "__main__":
    unittest.main()
