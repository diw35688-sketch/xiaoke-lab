import unittest
from datetime import datetime, timedelta, timezone

from src.core.deferred_playback_queue import DeferredPlaybackQueue
from src.core.playback_context import PlaybackContext, PlaybackSessionPhase
from src.core.playback_decision import (
    PlaybackDecision,
    PlaybackDisposition,
    PlaybackReason,
)
from src.core.playback_reevaluation import (
    ReevaluationTrigger,
    reevaluate_deferred,
)
from src.core.playback_request import PlaybackRequest
from src.core.presentation_intent import MessageKind, MessagePriority


NOW = datetime(2026, 8, 23, 14, 0, tzinfo=timezone.utc)


def _request(intent_id="ask-1"):
    return PlaybackRequest(
        intent_id=intent_id,
        kind=MessageKind.CLARIFICATION,
        priority=MessagePriority.ACTIVE_QUESTION,
        voice_text="温度是多少？",
        created_at=NOW - timedelta(seconds=2),
        ttl=timedelta(seconds=20),
    )


def _decision(reason):
    return PlaybackDecision(PlaybackDisposition.DEFERRED, reason)


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


class PlaybackReevaluationTests(unittest.TestCase):
    def test_user_stopped_speaking_releases_deferred_item_as_ready(self):
        queue = DeferredPlaybackQueue()
        entry = queue.defer(
            _request(),
            _decision(PlaybackReason.USER_SPEAKING),
        )

        batch = reevaluate_deferred(
            queue,
            trigger=ReevaluationTrigger.USER_STOPPED_SPEAKING,
            context=_context(),
        )

        self.assertEqual(batch.trigger, ReevaluationTrigger.USER_STOPPED_SPEAKING)
        self.assertEqual(batch.outcomes[0].entry, entry)
        self.assertEqual(
            batch.outcomes[0].decision.disposition,
            PlaybackDisposition.READY,
        )
        self.assertEqual(queue.snapshot(), ())

    def test_asr_end_can_leave_item_deferred_for_tts_busy(self):
        queue = DeferredPlaybackQueue()
        request = _request()
        queue.defer(request, _decision(PlaybackReason.VOICE_INPUT_BUSY))

        batch = reevaluate_deferred(
            queue,
            trigger=ReevaluationTrigger.VOICE_INPUT_BECAME_IDLE,
            context=_context(
                tts_playing=True,
                active_tts_priority=MessagePriority.DIRECT_ACK,
            ),
        )

        self.assertEqual(
            batch.outcomes[0].decision.reason,
            PlaybackReason.TTS_BUSY,
        )
        retained = queue.snapshot()
        self.assertEqual(len(retained), 1)
        self.assertEqual(retained[0].request, request)
        self.assertEqual(retained[0].decision.reason, PlaybackReason.TTS_BUSY)

    def test_tts_end_releases_all_existing_items_in_fifo_order(self):
        queue = DeferredPlaybackQueue()
        queue.defer(_request("ask-1"), _decision(PlaybackReason.TTS_BUSY))
        queue.defer(_request("ask-2"), _decision(PlaybackReason.TTS_BUSY))

        batch = reevaluate_deferred(
            queue,
            trigger=ReevaluationTrigger.TTS_PLAYBACK_ENDED,
            context=_context(),
        )

        self.assertEqual(
            tuple(item.entry.request.intent_id for item in batch.outcomes),
            ("ask-1", "ask-2"),
        )
        self.assertTrue(all(
            item.decision.disposition == PlaybackDisposition.READY
            for item in batch.outcomes
        ))
        self.assertEqual(len(queue), 0)

    def test_empty_queue_produces_empty_batch(self):
        batch = reevaluate_deferred(
            DeferredPlaybackQueue(),
            trigger=ReevaluationTrigger.USER_STOPPED_SPEAKING,
            context=_context(),
        )

        self.assertEqual(batch.outcomes, ())

    def test_trigger_must_match_new_context_without_mutating_queue(self):
        cases = (
            (
                ReevaluationTrigger.USER_STOPPED_SPEAKING,
                _context(user_speaking=True),
                "user_speaking=False",
            ),
            (
                ReevaluationTrigger.VOICE_INPUT_BECAME_IDLE,
                _context(voice_input_busy=True),
                "voice_input_busy=False",
            ),
            (
                ReevaluationTrigger.TTS_PLAYBACK_ENDED,
                _context(
                    tts_playing=True,
                    active_tts_priority=MessagePriority.DIRECT_ACK,
                ),
                "tts_playing=False",
            ),
        )
        for trigger, context, message in cases:
            with self.subTest(trigger=trigger):
                queue = DeferredPlaybackQueue()
                queue.defer(_request(), _decision(PlaybackReason.USER_SPEAKING))
                with self.assertRaisesRegex(ValueError, message):
                    reevaluate_deferred(queue, trigger=trigger, context=context)
                self.assertEqual(len(queue), 1)

    def test_reevaluation_has_no_playback_execution_api(self):
        batch = reevaluate_deferred(
            DeferredPlaybackQueue(),
            trigger=ReevaluationTrigger.TTS_PLAYBACK_ENDED,
            context=_context(),
        )

        for name in ("play", "speak", "stop", "execute"):
            with self.subTest(name=name):
                self.assertFalse(hasattr(batch, name))


if __name__ == "__main__":
    unittest.main()
