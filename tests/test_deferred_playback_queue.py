import unittest
from datetime import datetime, timedelta, timezone

from src.core.deferred_playback_queue import (
    DeferredPlaybackEntry,
    DeferredPlaybackQueue,
)
from src.core.playback_decision import (
    PlaybackDecision,
    PlaybackDisposition,
    PlaybackReason,
)
from src.core.playback_request import PlaybackRequest
from src.core.presentation_intent import MessageKind, MessagePriority


NOW = datetime(2026, 8, 23, 13, 0, tzinfo=timezone.utc)


def _request(intent_id="ask-1"):
    return PlaybackRequest(
        intent_id=intent_id,
        kind=MessageKind.CLARIFICATION,
        priority=MessagePriority.ACTIVE_QUESTION,
        voice_text="离心时间是多少？",
        created_at=NOW,
        ttl=timedelta(seconds=20),
    )


def _deferred(reason=PlaybackReason.USER_SPEAKING):
    return PlaybackDecision(PlaybackDisposition.DEFERRED, reason)


class DeferredPlaybackQueueTests(unittest.TestCase):
    def test_deferred_request_is_retained_without_immediate_playback(self):
        queue = DeferredPlaybackQueue()
        request = _request()
        decision = _deferred()

        entry = queue.defer(request, decision)

        self.assertEqual(entry, DeferredPlaybackEntry(request, decision))
        self.assertEqual(queue.snapshot(), (entry,))
        self.assertEqual(len(queue), 1)
        for name in ("play", "speak", "stop"):
            with self.subTest(name=name):
                self.assertFalse(hasattr(queue, name))

    def test_snapshot_is_immutable_and_does_not_remove_entries(self):
        queue = DeferredPlaybackQueue()
        first = queue.defer(_request("ask-1"), _deferred())
        second = queue.defer(
            _request("ask-2"),
            _deferred(PlaybackReason.TTS_BUSY),
        )

        snapshot = queue.snapshot()

        self.assertEqual(snapshot, (first, second))
        self.assertIsInstance(snapshot, tuple)
        self.assertEqual(len(queue), 2)

    def test_take_next_is_fifo_and_empty_returns_none(self):
        queue = DeferredPlaybackQueue()
        first = queue.defer(_request("ask-1"), _deferred())
        second = queue.defer(_request("ask-2"), _deferred())

        self.assertEqual(queue.take_next(), first)
        self.assertEqual(queue.take_next(), second)
        self.assertIsNone(queue.take_next())
        self.assertEqual(len(queue), 0)

    def test_non_deferred_decisions_are_rejected_without_mutation(self):
        queue = DeferredPlaybackQueue()
        invalid = PlaybackDecision(
            PlaybackDisposition.READY,
            PlaybackReason.PLAYBACK_WINDOW_OPEN,
        )

        with self.assertRaisesRegex(ValueError, "只接受 DEFERRED"):
            queue.defer(_request(), invalid)

        self.assertEqual(queue.snapshot(), ())

    def test_duplicate_intent_is_rejected_but_can_return_after_take(self):
        queue = DeferredPlaybackQueue()
        request = _request()
        queue.defer(request, _deferred())

        with self.assertRaisesRegex(ValueError, "已在延后队列"):
            queue.defer(request, _deferred(PlaybackReason.VOICE_INPUT_BUSY))

        self.assertEqual(len(queue), 1)
        queue.take_next()
        queue.defer(request, _deferred(PlaybackReason.VOICE_INPUT_BUSY))
        self.assertEqual(len(queue), 1)

    def test_entry_requires_contract_types(self):
        with self.assertRaisesRegex(TypeError, "PlaybackRequest"):
            DeferredPlaybackEntry(object(), _deferred())
        with self.assertRaisesRegex(TypeError, "PlaybackDecision"):
            DeferredPlaybackEntry(_request(), object())


if __name__ == "__main__":
    unittest.main()
