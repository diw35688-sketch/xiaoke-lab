import unittest

from src.core.playback_decision import (
    PlaybackDecision,
    PlaybackDisposition,
    PlaybackReason,
)


class PlaybackDecisionContractTests(unittest.TestCase):
    def test_four_dispositions_are_mutually_named_and_serializable(self):
        cases = (
            (
                PlaybackDisposition.READY,
                PlaybackReason.PLAYBACK_WINDOW_OPEN,
                "ready",
            ),
            (
                PlaybackDisposition.DEFERRED,
                PlaybackReason.USER_SPEAKING,
                "deferred",
            ),
            (
                PlaybackDisposition.DROP,
                PlaybackReason.EXPIRED,
                "drop",
            ),
            (
                PlaybackDisposition.PREEMPT,
                PlaybackReason.CRITICAL_OVER_LOWER_PRIORITY,
                "preempt",
            ),
        )

        self.assertEqual(len(PlaybackDisposition), 4)
        for disposition, reason, wire_value in cases:
            with self.subTest(disposition=disposition):
                decision = PlaybackDecision(disposition, reason)
                self.assertEqual(
                    decision.as_dict(),
                    {"disposition": wire_value, "reason": reason.value},
                )

    def test_every_reason_is_accepted_by_exactly_one_disposition(self):
        for reason in PlaybackReason:
            accepted = []
            for disposition in PlaybackDisposition:
                try:
                    PlaybackDecision(disposition, reason)
                except ValueError:
                    continue
                accepted.append(disposition)

            with self.subTest(reason=reason):
                self.assertEqual(len(accepted), 1)

    def test_reason_from_another_disposition_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "不属于"):
            PlaybackDecision(
                PlaybackDisposition.READY,
                PlaybackReason.EXPIRED,
            )

    def test_raw_strings_are_rejected(self):
        with self.assertRaisesRegex(TypeError, "PlaybackDisposition"):
            PlaybackDecision("ready", PlaybackReason.PLAYBACK_WINDOW_OPEN)
        with self.assertRaisesRegex(TypeError, "PlaybackReason"):
            PlaybackDecision(PlaybackDisposition.READY, "playback_window_open")

    def test_decision_is_immutable_and_has_no_execution_api(self):
        decision = PlaybackDecision(
            PlaybackDisposition.DEFERRED,
            PlaybackReason.TTS_BUSY,
        )

        with self.assertRaises(AttributeError):
            decision.reason = PlaybackReason.USER_SPEAKING
        for name in ("play", "stop", "enqueue", "execute"):
            with self.subTest(name=name):
                self.assertFalse(hasattr(decision, name))


if __name__ == "__main__":
    unittest.main()
