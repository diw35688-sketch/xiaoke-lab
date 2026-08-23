import unittest
from datetime import datetime, timedelta, timezone

from src.core.deferred_playback_queue import DeferredPlaybackQueue
from src.core.playback_decision import (
    PlaybackDecision,
    PlaybackDisposition,
    PlaybackReason,
)
from src.core.playback_expiry import drop_expired
from src.core.playback_request import PlaybackRequest
from src.core.presentation_intent import MessageKind, MessagePriority


NOW = datetime(2026, 8, 23, 15, 0, tzinfo=timezone.utc)


def _request(intent_id, *, expires_in):
    return PlaybackRequest(
        intent_id=intent_id,
        kind=MessageKind.CLARIFICATION,
        priority=MessagePriority.ACTIVE_QUESTION,
        voice_text="离心时间是多少？",
        created_at=NOW,
        ttl=timedelta(seconds=expires_in),
    )


def _deferred(reason=PlaybackReason.USER_SPEAKING):
    return PlaybackDecision(PlaybackDisposition.DEFERRED, reason)


class PlaybackExpiryTests(unittest.TestCase):
    def test_request_is_kept_before_expiry_boundary(self):
        queue = DeferredPlaybackQueue()
        entry = queue.defer(_request("ask-1", expires_in=10), _deferred())

        sweep = drop_expired(
            queue,
            observed_at=NOW + timedelta(seconds=9),
        )

        self.assertEqual(sweep.expired, ())
        self.assertEqual(queue.snapshot(), (entry,))

    def test_request_drops_at_exact_expiry_boundary(self):
        queue = DeferredPlaybackQueue()
        entry = queue.defer(_request("ask-1", expires_in=10), _deferred())

        sweep = drop_expired(
            queue,
            observed_at=NOW + timedelta(seconds=10),
        )

        self.assertEqual(sweep.expired[0].entry, entry)
        self.assertEqual(
            sweep.expired[0].decision.disposition,
            PlaybackDisposition.DROP,
        )
        self.assertEqual(
            sweep.expired[0].decision.reason,
            PlaybackReason.EXPIRED,
        )
        self.assertEqual(queue.snapshot(), ())

    def test_mixed_scan_removes_expired_and_preserves_survivor_order(self):
        queue = DeferredPlaybackQueue()
        queue.defer(_request("keep-1", expires_in=30), _deferred())
        queue.defer(_request("drop-1", expires_in=5), _deferred())
        queue.defer(
            _request("keep-2", expires_in=40),
            _deferred(PlaybackReason.TTS_BUSY),
        )
        queue.defer(_request("drop-2", expires_in=10), _deferred())

        sweep = drop_expired(
            queue,
            observed_at=NOW + timedelta(seconds=10),
        )

        self.assertEqual(
            tuple(item.entry.request.intent_id for item in sweep.expired),
            ("drop-1", "drop-2"),
        )
        survivors = queue.snapshot()
        self.assertEqual(
            tuple(item.request.intent_id for item in survivors),
            ("keep-1", "keep-2"),
        )
        self.assertEqual(survivors[1].decision.reason, PlaybackReason.TTS_BUSY)

    def test_empty_queue_returns_empty_sweep(self):
        sweep = drop_expired(DeferredPlaybackQueue(), observed_at=NOW)

        self.assertEqual(sweep.observed_at, NOW)
        self.assertEqual(sweep.expired, ())

    def test_invalid_time_is_rejected_before_queue_mutation(self):
        queue = DeferredPlaybackQueue()
        entry = queue.defer(_request("ask-1", expires_in=10), _deferred())

        with self.assertRaisesRegex(ValueError, "时区"):
            drop_expired(
                queue,
                observed_at=datetime(2026, 8, 23, 15, 0),
            )

        self.assertEqual(queue.snapshot(), (entry,))

    def test_sweep_has_no_playback_or_retry_api(self):
        sweep = drop_expired(DeferredPlaybackQueue(), observed_at=NOW)

        for name in ("play", "speak", "retry", "enqueue"):
            with self.subTest(name=name):
                self.assertFalse(hasattr(sweep, name))


if __name__ == "__main__":
    unittest.main()
