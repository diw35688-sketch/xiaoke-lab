# -*- coding: utf-8 -*-
"""Desktop microphone display follows the real recorder state."""

import unittest
from pathlib import Path


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "web" / "frontend"


class WebRecordingButtonStateTests(unittest.TestCase):
    def test_recorder_publishes_started_and_stopped_states(self):
        source = (FRONTEND_DIR / "voice_asr.js").read_text(encoding="utf-8")

        self.assertIn("publishRecordingState(true)", source)
        self.assertIn("publishRecordingState(false)", source)
        self.assertIn("lab:recording-state", source)

    def test_composer_does_not_guess_recording_state_on_click(self):
        source = (FRONTEND_DIR / "composer.js").read_text(encoding="utf-8")

        self.assertIn("document.addEventListener('lab:recording-state'", source)
        self.assertIn("classList.toggle('rec', active)", source)
        self.assertNotIn("classList.toggle('rec');", source)
        self.assertIn("if (!real || real.disabled) return;", source)


if __name__ == "__main__":
    unittest.main()
