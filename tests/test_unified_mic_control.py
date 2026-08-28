import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "web" / "frontend"


class UnifiedMicControlTests(unittest.TestCase):
    def test_composer_owns_one_mic_and_selects_single_or_continuous_input(self):
        source = (FRONTEND / "composer.js").read_text(encoding="utf-8")

        self.assertEqual(source.count('id="cp-mic"'), 1)
        self.assertIn('id="cp-continuous"', source)
        self.assertIn("window.phoneCallToggle?.();", source)
        self.assertIn("real.click();", source)

    def test_continuous_call_reports_real_active_state_to_composer(self):
        source = (FRONTEND / "phone_call.js").read_text(encoding="utf-8")

        self.assertIn("'lab:continuous-call-state'", source)
        self.assertIn("detail: { active: on }", source)
        self.assertIn("window.phoneCallIsActive = () => active", source)


if __name__ == "__main__":
    unittest.main()
