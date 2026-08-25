import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "web" / "app.py"
FRONTEND = ROOT / "web" / "frontend"


class PhoneCallSileroIntegrationTests(unittest.TestCase):
    def test_adapter_loads_before_phone_call_client(self):
        app = APP.read_text(encoding="utf-8")

        adapter = app.index("call_silero_vad.js")
        phone_call = app.index("phone_call.js")

        self.assertLess(adapter, phone_call)

    def test_adapter_exposes_contract_events_and_fixed_v5_boundaries(self):
        source = (FRONTEND / "call_silero_vad.js").read_text(encoding="utf-8")

        self.assertNotIn("cdn.jsdelivr.net", source)
        self.assertIn('/static/vendor/voice/', source)
        self.assertIn("preloadVoiceStack", source)

        for event in (
            "speech_started",
            "speech_paused",
            "speech_resumed",
            "segment_finalized",
        ):
            with self.subTest(event=event):
                self.assertIn(f'emit("{event}"', source)
        self.assertIn('model: "v5"', source)
        self.assertIn("redemptionMs: 1500", source)
        self.assertIn("preSpeechPadMs: 450", source)
        self.assertIn("minSpeechMs: 1200", source)

    def test_phone_call_uses_silero_first_and_keeps_rms_fallback(self):
        source = (FRONTEND / "phone_call.js").read_text(encoding="utf-8")

        self.assertIn("prepareSileroCapture", source)
        self.assertIn("window.preparePhoneCall", source)
        self.assertIn("void prepareSileroCapture()", source)
        self.assertIn("await startPreferredCapture()", source)
        self.assertIn("window.createCallSileroVad", source)
        self.assertIn("await startRmsCapture()", source)
        self.assertIn("Silero VAD 初始化失败", source)
        self.assertIn("navigator.mediaDevices.getUserMedia", source)


if __name__ == "__main__":
    unittest.main()
