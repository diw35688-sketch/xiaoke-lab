import unittest
from datetime import datetime, timedelta, timezone

from src.core.deferred_playback_queue import DeferredPlaybackQueue
from src.core.playback_decision import (
    PlaybackDecision,
    PlaybackDisposition,
    PlaybackReason,
)
from src.core.playback_request import PlaybackRequest
from src.core.playback_supersession import supersede_deferred
from src.core.presentation_intent import MessageKind, MessagePriority


NOW = datetime(2026, 8, 23, 16, 0, tzinfo=timezone.utc)


def _request(intent_id, key="clarification:current"):
    return PlaybackRequest(
        intent_id=intent_id,
        kind=MessageKind.CLARIFICATION,
        priority=MessagePriority.ACTIVE_QUESTION,
        voice_text=f"问题 {intent_id}？",
        created_at=NOW,
        ttl=timedelta(seconds=20),
        supersession_key=key,
    )


def _deferred(reason=PlaybackReason.USER_SPEAKING):
    return PlaybackDecision(PlaybackDisposition.DEFERRED, reason)


class PlaybackSupersessionTests(unittest.TestCase):
    def test_replacement_drops_all_old_entries_with_same_key(self):
        queue = DeferredPlaybackQueue()
        old_1 = queue.defer(_request("old-1"), _deferred())
        old_2 = queue.defer(_request("old-2"), _deferred())

        result = supersede_deferred(
            queue,
            replacement=_request("new"),
            decision=_deferred(PlaybackReason.VOICE_INPUT_BUSY),
        )

        self.assertEqual(
            tuple(item.entry for item in result.superseded),
            (old_1, old_2),
        )
        self.assertTrue(all(
            item.decision.disposition == PlaybackDisposition.DROP
            and item.decision.reason == PlaybackReason.SUPERSEDED
            for item in result.superseded
        ))
        self.assertEqual(
            tuple(item.request.intent_id for item in queue.snapshot()),
            ("new",),
        )

    def test_unrelated_entries_keep_order_and_replacement_goes_to_tail(self):
        queue = DeferredPlaybackQueue()
        queue.defer(_request("keep-1", "summary:stage"), _deferred())
        queue.defer(_request("old", "clarification:current"), _deferred())
        queue.defer(
            _request("keep-2", "alert:safety"),
            _deferred(PlaybackReason.TTS_BUSY),
        )

        supersede_deferred(
            queue,
            replacement=_request("new", "clarification:current"),
            decision=_deferred(),
        )

        entries = queue.snapshot()
        self.assertEqual(
            tuple(item.request.intent_id for item in entries),
            ("keep-1", "keep-2", "new"),
        )
        self.assertEqual(entries[1].decision.reason, PlaybackReason.TTS_BUSY)

    def test_no_existing_match_just_queues_replacement(self):
        queue = DeferredPlaybackQueue()
        queue.defer(_request("keep", "summary:stage"), _deferred())

        result = supersede_deferred(
            queue,
            replacement=_request("new", "clarification:current"),
            decision=_deferred(),
        )

        self.assertEqual(result.superseded, ())
        self.assertEqual(
            tuple(item.request.intent_id for item in queue.snapshot()),
            ("keep", "new"),
        )

    def test_missing_key_is_rejected_before_queue_mutation(self):
        queue = DeferredPlaybackQueue()
        existing = queue.defer(_request("keep"), _deferred())

        with self.assertRaisesRegex(ValueError, "supersession_key"):
            supersede_deferred(
                queue,
                replacement=_request("new", None),
                decision=_deferred(),
            )

        self.assertEqual(queue.snapshot(), (existing,))

    def test_non_deferred_replacement_is_rejected_before_mutation(self):
        queue = DeferredPlaybackQueue()
        existing = queue.defer(_request("old"), _deferred())
        ready = PlaybackDecision(
            PlaybackDisposition.READY,
            PlaybackReason.PLAYBACK_WINDOW_OPEN,
        )

        with self.assertRaisesRegex(ValueError, "只接受 DEFERRED"):
            supersede_deferred(
                queue,
                replacement=_request("new"),
                decision=ready,
            )

        self.assertEqual(queue.snapshot(), (existing,))

    def test_duplicate_replacement_intent_is_rejected_before_mutation(self):
        queue = DeferredPlaybackQueue()
        existing = queue.defer(_request("same"), _deferred())

        with self.assertRaisesRegex(ValueError, "已在延后队列"):
            supersede_deferred(
                queue,
                replacement=_request("same"),
                decision=_deferred(),
            )

        self.assertEqual(queue.snapshot(), (existing,))

    def test_result_has_no_playback_or_cancel_api(self):
        result = supersede_deferred(
            DeferredPlaybackQueue(),
            replacement=_request("new"),
            decision=_deferred(),
        )

        for name in ("play", "speak", "stop", "cancel"):
            with self.subTest(name=name):
                self.assertFalse(hasattr(result, name))


if __name__ == "__main__":
    unittest.main()
