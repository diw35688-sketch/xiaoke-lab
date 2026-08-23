import unittest
from datetime import datetime, timedelta, timezone

from src.core.playback_context import PlaybackContext, PlaybackSessionPhase
from src.core.playback_decision import PlaybackDisposition, PlaybackReason
from src.core.playback_gate import PlaybackGate
from src.core.playback_request import PlaybackRequest
from src.core.presentation_intent import MessageKind, MessagePriority


NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)


def _request(**overrides):
    values = {
        "intent_id": "ask-gate-1",
        "kind": MessageKind.CLARIFICATION,
        "priority": MessagePriority.ACTIVE_QUESTION,
        "voice_text": "温度是多少？",
        "created_at": NOW - timedelta(seconds=1),
        "ttl": timedelta(seconds=20),
    }
    values.update(overrides)
    return PlaybackRequest(**values)


def _context(**overrides):
    values = {
        "observed_at": NOW,
        "user_speaking": False,
        "voice_input_busy": False,
        "tts_playing": False,
        "session_phase": PlaybackSessionPhase.ACTIVE,
        "active_tts_priority": None,
    }
    values.update(overrides)
    return PlaybackContext(**values)


class PlaybackGateTests(unittest.TestCase):
    def test_same_request_and_context_produce_same_decision(self):
        gate = PlaybackGate()
        request = _request()
        context = _context()

        first = gate.evaluate(request, context)
        second = gate.evaluate(request, context)

        self.assertEqual(first, second)
        self.assertEqual(first.disposition, PlaybackDisposition.READY)
        self.assertEqual(first.reason, PlaybackReason.PLAYBACK_WINDOW_OPEN)

    def test_gate_exposes_rules_without_copying_timing_logic(self):
        decision = PlaybackGate.evaluate(
            _request(),
            _context(user_speaking=True),
        )

        self.assertEqual(decision.disposition, PlaybackDisposition.DEFERRED)
        self.assertEqual(decision.reason, PlaybackReason.USER_SPEAKING)

    def test_gate_rejects_non_contract_inputs(self):
        with self.assertRaisesRegex(TypeError, "PlaybackRequest"):
            PlaybackGate.evaluate(object(), _context())
        with self.assertRaisesRegex(TypeError, "PlaybackContext"):
            PlaybackGate.evaluate(_request(), object())

    def test_gate_holds_no_runtime_state_or_execution_api(self):
        gate = PlaybackGate()

        self.assertFalse(hasattr(gate, "__dict__"))
        for name in (
            "queue",
            "deferred",
            "play",
            "stop",
            "enqueue",
            "cancel",
        ):
            with self.subTest(name=name):
                self.assertFalse(hasattr(gate, name))


if __name__ == "__main__":
    unittest.main()
