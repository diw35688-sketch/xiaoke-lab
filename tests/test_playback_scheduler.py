import unittest
from datetime import datetime, timedelta, timezone

from src.core.deferred_playback_queue import DeferredPlaybackQueue
from src.core.playback_context import PlaybackSessionPhase
from src.core.playback_context_factory import PlaybackContextFactory
from src.core.playback_decision import PlaybackDisposition, PlaybackReason
from src.core.playback_gate import PlaybackGate
from src.core.playback_request import PlaybackRequest
from src.core.playback_scheduler import (
    PlaybackScheduleAction,
    PlaybackScheduler,
)
from src.core.presentation_intent import MessageKind, MessagePriority
from src.core.voice_runtime_state import VoiceRuntimeState, VoiceStateCoordinator


NOW = datetime(2026, 8, 23, 14, 0, tzinfo=timezone.utc)


class FakeExecutionPort:
    def __init__(self):
        self.played = []
        self.stop_calls = 0

    def play(self, request):
        self.played.append(request)

    def stop(self):
        self.stop_calls += 1


def _request(
    *,
    intent_id="voice-1",
    priority=MessagePriority.ACTIVE_QUESTION,
    created_at=NOW,
):
    return PlaybackRequest(
        intent_id=intent_id,
        kind=MessageKind.CLARIFICATION,
        priority=priority,
        voice_text="离心时间是多少？",
        created_at=created_at,
        ttl=timedelta(seconds=20),
    )


def _scheduler(state=None, *, observed_at=NOW):
    coordinator = VoiceStateCoordinator(state)
    factory = PlaybackContextFactory(coordinator, lambda: observed_at)
    queue = DeferredPlaybackQueue()
    execution = FakeExecutionPort()
    scheduler = PlaybackScheduler(factory, PlaybackGate(), queue, execution)
    return scheduler, queue, execution


class PlaybackSchedulerTests(unittest.TestCase):
    def test_ready_request_is_handed_to_tts_once(self):
        scheduler, queue, execution = _scheduler()
        request = _request()

        result = scheduler.schedule(
            request, session_phase=PlaybackSessionPhase.ACTIVE
        )

        self.assertEqual(result.action, PlaybackScheduleAction.HANDED_TO_TTS)
        self.assertEqual(result.decision.disposition, PlaybackDisposition.READY)
        self.assertEqual(execution.played, [request])
        self.assertEqual(len(queue), 0)

    def test_short_pause_request_is_queued_without_playback(self):
        scheduler, queue, execution = _scheduler(
            VoiceRuntimeState(segment_capturing=True)
        )
        request = _request()

        result = scheduler.schedule(
            request, session_phase=PlaybackSessionPhase.ACTIVE
        )

        self.assertEqual(result.action, PlaybackScheduleAction.QUEUED)
        self.assertEqual(result.decision.reason, PlaybackReason.VOICE_INPUT_BUSY)
        self.assertEqual(queue.snapshot(), (result.deferred_entry,))
        self.assertEqual(execution.played, [])

    def test_drop_returns_evidence_without_queue_or_playback(self):
        scheduler, queue, execution = _scheduler(
            observed_at=NOW + timedelta(seconds=20)
        )
        request = _request()

        result = scheduler.schedule(
            request, session_phase=PlaybackSessionPhase.ACTIVE
        )

        self.assertEqual(result.action, PlaybackScheduleAction.DROPPED)
        self.assertEqual(result.decision.reason, PlaybackReason.EXPIRED)
        self.assertEqual(len(queue), 0)
        self.assertEqual(execution.played, [])

    def test_preempt_requires_observed_started_event(self):
        scheduler, queue, execution = _scheduler(
            VoiceRuntimeState(
                tts_playing=True,
                active_tts_priority=MessagePriority.DIRECT_ACK,
            )
        )
        request = _request(priority=MessagePriority.CRITICAL)

        with self.assertRaisesRegex(RuntimeError, "STARTED"):
            scheduler.schedule(
                request, session_phase=PlaybackSessionPhase.ACTIVE
            )

        self.assertEqual(len(queue), 0)
        self.assertEqual(execution.played, [])
        self.assertEqual(execution.stop_calls, 0)

    def test_each_schedule_uses_the_context_returned_for_its_decision(self):
        scheduler, _, _ = _scheduler()

        result = scheduler.schedule(
            _request(), session_phase=PlaybackSessionPhase.CLOSING
        )

        self.assertIs(result.context.session_phase, PlaybackSessionPhase.CLOSING)
        self.assertEqual(
            result.decision.reason, PlaybackReason.SESSION_NOT_ACTIVE
        )

    def test_closed_deferred_queue_failure_does_not_play(self):
        scheduler, queue, execution = _scheduler(
            VoiceRuntimeState(segment_capturing=True)
        )
        queue.close()

        with self.assertRaisesRegex(RuntimeError, "已关闭"):
            scheduler.schedule(
                _request(), session_phase=PlaybackSessionPhase.ACTIVE
            )

        self.assertEqual(execution.played, [])

    def test_execution_failure_is_bounded_and_not_misreported_as_handed_off(self):
        class FailingExecutionPort:
            def __init__(self):
                self.play_calls = 0

            def play(self, request):
                self.play_calls += 1
                raise RuntimeError("fake tts failed")

            def stop(self):
                raise RuntimeError("fake stop failed")

        coordinator = VoiceStateCoordinator()
        execution = FailingExecutionPort()
        scheduler = PlaybackScheduler(
            PlaybackContextFactory(coordinator, lambda: NOW),
            PlaybackGate(),
            DeferredPlaybackQueue(),
            execution,
        )

        result = scheduler.schedule(
            _request(), session_phase=PlaybackSessionPhase.ACTIVE
        )

        self.assertEqual(result.action, PlaybackScheduleAction.PLAYBACK_FAILED)
        self.assertEqual(result.failure.error, "fake tts failed")
        self.assertEqual(execution.play_calls, 2)

    def test_invalid_dependencies_and_request_are_rejected(self):
        factory = PlaybackContextFactory(VoiceStateCoordinator(), lambda: NOW)
        queue = DeferredPlaybackQueue()
        execution = FakeExecutionPort()

        invalid_cases = (
            (object(), PlaybackGate(), queue, execution, "context_factory"),
            (factory, object(), queue, execution, "gate"),
            (factory, PlaybackGate(), object(), execution, "deferred_queue"),
            (factory, PlaybackGate(), queue, object(), "execution_port"),
        )
        for context_factory, gate, deferred_queue, port, message in invalid_cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(TypeError, message):
                    PlaybackScheduler(
                        context_factory, gate, deferred_queue, port
                    )

        scheduler = PlaybackScheduler(factory, PlaybackGate(), queue, execution)
        with self.assertRaisesRegex(TypeError, "request"):
            scheduler.schedule(
                object(), session_phase=PlaybackSessionPhase.ACTIVE
            )


if __name__ == "__main__":
    unittest.main()
