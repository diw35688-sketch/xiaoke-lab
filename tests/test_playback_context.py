import unittest
from datetime import datetime, timezone

from src.core.playback_context import PlaybackContext, PlaybackSessionPhase
from src.core.presentation_intent import MessagePriority


OBSERVED_AT = datetime(2026, 8, 23, 10, 15, tzinfo=timezone.utc)


def _context(**overrides):
    values = {
        "observed_at": OBSERVED_AT,
        "user_speaking": False,
        "voice_input_busy": True,
        "tts_playing": False,
        "session_phase": PlaybackSessionPhase.ACTIVE,
        "active_tts_priority": None,
    }
    values.update(overrides)
    return PlaybackContext(**values)


class PlaybackContextContractTests(unittest.TestCase):
    def test_valid_context_is_an_immutable_snapshot(self):
        context = _context()

        self.assertEqual(context.observed_at, OBSERVED_AT)
        self.assertEqual(context.session_phase, PlaybackSessionPhase.ACTIVE)
        with self.assertRaises(AttributeError):
            context.tts_playing = True

    def test_all_session_phases_are_representable(self):
        for phase in PlaybackSessionPhase:
            with self.subTest(phase=phase):
                self.assertEqual(_context(session_phase=phase).session_phase, phase)

    def test_transient_user_and_tts_overlap_is_preserved_as_fact(self):
        context = _context(
            user_speaking=True,
            tts_playing=True,
            active_tts_priority=MessagePriority.DIRECT_ACK,
        )

        self.assertTrue(context.user_speaking)
        self.assertTrue(context.tts_playing)
        self.assertEqual(
            context.active_tts_priority,
            MessagePriority.DIRECT_ACK,
        )

    def test_playing_priority_may_be_unknown_but_not_stale(self):
        self.assertIsNone(_context(tts_playing=True).active_tts_priority)
        with self.assertRaisesRegex(ValueError, "TTS 未播放"):
            _context(active_tts_priority=MessagePriority.DIRECT_ACK)

    def test_playing_priority_rejects_raw_integer(self):
        with self.assertRaisesRegex(TypeError, "MessagePriority"):
            _context(tts_playing=True, active_tts_priority=10)

    def test_observed_at_must_be_timezone_aware(self):
        with self.assertRaisesRegex(ValueError, "时区"):
            _context(observed_at=datetime(2026, 8, 23, 10, 15))

    def test_activity_fields_require_actual_booleans(self):
        for field in ("user_speaking", "voice_input_busy", "tts_playing"):
            with self.subTest(field=field):
                with self.assertRaisesRegex(TypeError, field):
                    _context(**{field: 1})

    def test_session_phase_rejects_raw_string(self):
        with self.assertRaisesRegex(TypeError, "PlaybackSessionPhase"):
            _context(session_phase="active")

    def test_snapshot_has_no_device_control_or_decision_api(self):
        context = _context()

        for name in ("start", "stop", "play", "decide", "enqueue"):
            with self.subTest(name=name):
                self.assertFalse(hasattr(context, name))


if __name__ == "__main__":
    unittest.main()
