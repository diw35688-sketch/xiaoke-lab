import unittest
from datetime import datetime, timedelta, timezone

from src.core.deferred_playback_queue import DeferredPlaybackQueue
from src.core.playback_decision import (
    PlaybackDecision,
    PlaybackDisposition,
    PlaybackReason,
)
from src.core.playback_request import PlaybackRequest
from src.core.playback_session_cancel import cancel_deferred_for_session
from src.core.presentation_intent import MessageKind, MessagePriority


NOW = datetime(2026, 8, 23, 17, 0, tzinfo=timezone.utc)


def _request(intent_id):
    return PlaybackRequest(
        intent_id=intent_id,
        kind=MessageKind.CLARIFICATION,
        priority=MessagePriority.ACTIVE_QUESTION,
        voice_text="离心时间是多少？",
        created_at=NOW,
        ttl=timedelta(seconds=20),
        supersession_key="clarification:current",
    )


def _deferred():
    return PlaybackDecision(
        PlaybackDisposition.DEFERRED,
        PlaybackReason.USER_SPEAKING,
    )


class PlaybackSessionCancellationTests(unittest.TestCase):
    def test_session_end_drains_fifo_with_drop_evidence(self):
        queue = DeferredPlaybackQueue()
        first = queue.defer(_request("ask-1"), _deferred())
        second = queue.defer(_request("ask-2"), _deferred())

        result = cancel_deferred_for_session(queue)

        self.assertEqual(
            tuple(item.entry for item in result.cancelled),
            (first, second),
        )
        self.assertTrue(all(
            item.decision.disposition == PlaybackDisposition.DROP
            and item.decision.reason == PlaybackReason.SESSION_ENDED
            for item in result.cancelled
        ))
        self.assertEqual(queue.snapshot(), ())
        self.assertTrue(queue.is_closed)

    def test_closed_queue_rejects_late_deferred_request(self):
        queue = DeferredPlaybackQueue()
        cancel_deferred_for_session(queue)

        with self.assertRaisesRegex(RuntimeError, "已关闭"):
            queue.defer(_request("late"), _deferred())

        self.assertEqual(queue.snapshot(), ())

    def test_repeated_cancel_is_idempotent_and_cannot_restore_entries(self):
        queue = DeferredPlaybackQueue()
        queue.defer(_request("ask-1"), _deferred())

        first = cancel_deferred_for_session(queue)
        second = cancel_deferred_for_session(queue)

        self.assertEqual(len(first.cancelled), 1)
        self.assertEqual(second.cancelled, ())
        self.assertIsNone(queue.take_next())
        self.assertEqual(len(queue), 0)

    def test_empty_queue_closes_successfully(self):
        queue = DeferredPlaybackQueue()

        result = cancel_deferred_for_session(queue)

        self.assertEqual(result.cancelled, ())
        self.assertTrue(queue.is_closed)

    def test_requires_queue_contract(self):
        with self.assertRaisesRegex(TypeError, "DeferredPlaybackQueue"):
            cancel_deferred_for_session(object())

    def test_result_has_no_playback_or_reopen_api(self):
        result = cancel_deferred_for_session(DeferredPlaybackQueue())

        for name in ("play", "speak", "reopen", "retry"):
            with self.subTest(name=name):
                self.assertFalse(hasattr(result, name))


if __name__ == "__main__":
    unittest.main()
