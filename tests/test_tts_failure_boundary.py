import unittest
from datetime import datetime, timedelta, timezone

from src.core.deferred_playback_queue import DeferredPlaybackQueue
from src.core.playback_context import PlaybackSessionPhase
from src.core.playback_context_factory import PlaybackContextFactory
from src.core.playback_gate import PlaybackGate
from src.core.playback_request import PlaybackRequest
from src.core.playback_scheduler import PlaybackScheduleAction, PlaybackScheduler
from src.core.presentation_intent import MessageKind, MessagePriority
from src.core.tts_adapter import TTSAdapter, TTSExecutionEventType
from src.core.tts_failure_boundary import (
    TTSFailureBoundary,
    TTSFailureStage,
)
from src.core.voice_runtime_state import VoiceStateCoordinator


NOW = datetime(2026, 8, 23, 17, 0, tzinfo=timezone.utc)


def _request():
    return PlaybackRequest(
        intent_id="voice-failure",
        kind=MessageKind.CLARIFICATION,
        priority=MessagePriority.ACTIVE_QUESTION,
        voice_text="离心时间是多少？",
        created_at=NOW,
        ttl=timedelta(seconds=20),
    )


class FakeDriver:
    def __init__(self):
        self.play_calls = 0
        self.stop_calls = 0
        self.report = None

    def play(self, request, report):
        self.play_calls += 1
        self.report = report

    def stop(self):
        self.stop_calls += 1


class TTSFailureBoundaryTests(unittest.TestCase):
    def test_start_failure_retries_once_then_returns_permanent_evidence(self):
        boundary = TTSFailureBoundary(max_start_retries=1)
        calls = []

        def fail():
            calls.append("play")
            raise RuntimeError("device unavailable")

        outcome = boundary.execute_start(_request(), fail)

        self.assertFalse(outcome.accepted)
        self.assertEqual(calls, ["play", "play"])
        self.assertEqual([item.attempt for item in outcome.failures], [1, 2])
        self.assertEqual(
            [item.will_retry for item in outcome.failures], [True, False]
        )

    def test_transient_start_failure_succeeds_on_only_retry(self):
        boundary = TTSFailureBoundary(max_start_retries=1)
        calls = []

        def command():
            calls.append("play")
            if len(calls) == 1:
                raise RuntimeError("temporary")

        outcome = boundary.execute_start(_request(), command)

        self.assertTrue(outcome.accepted)
        self.assertEqual(outcome.attempts, 2)
        self.assertEqual(len(outcome.failures), 1)

    def test_active_failure_is_recorded_once_and_never_replayed(self):
        boundary = TTSFailureBoundary()
        coordinator = VoiceStateCoordinator()
        driver = FakeDriver()
        scheduler_holder = []

        def sink(event):
            scheduler_holder[0].handle_tts_event(
                event, session_phase=PlaybackSessionPhase.ACTIVE
            )

        adapter = TTSAdapter(driver, coordinator, sink, boundary)
        scheduler = PlaybackScheduler(
            PlaybackContextFactory(coordinator, lambda: NOW),
            PlaybackGate(),
            DeferredPlaybackQueue(),
            adapter,
            boundary,
        )
        scheduler_holder.append(scheduler)
        scheduler.schedule(
            _request(), session_phase=PlaybackSessionPhase.ACTIVE
        )
        driver.report(TTSExecutionEventType.STARTED, None)

        driver.report(TTSExecutionEventType.FAILED, "speaker disconnected")

        self.assertEqual(driver.play_calls, 1)
        self.assertFalse(coordinator.snapshot().tts_playing)
        active_failures = [
            item
            for item in boundary.snapshot()
            if item.stage is TTSFailureStage.ACTIVE_PLAYBACK
        ]
        self.assertEqual(len(active_failures), 1)
        self.assertFalse(active_failures[0].will_retry)

    def test_event_sink_failure_isolated_after_runtime_fact_update(self):
        boundary = TTSFailureBoundary()
        coordinator = VoiceStateCoordinator()
        driver = FakeDriver()

        def broken_sink(event):
            raise RuntimeError("observer unavailable")

        adapter = TTSAdapter(driver, coordinator, broken_sink, boundary)
        adapter.play(_request())

        driver.report(TTSExecutionEventType.STARTED, None)

        self.assertTrue(coordinator.snapshot().tts_playing)
        self.assertEqual(len(boundary.snapshot()), 1)
        self.assertIs(
            boundary.snapshot()[0].stage, TTSFailureStage.EVENT_DELIVERY
        )
        self.assertFalse(boundary.snapshot()[0].will_retry)

    def test_failed_schedule_keeps_original_request_as_screen_evidence(self):
        class AlwaysFailPort:
            def play(self, request):
                raise RuntimeError("no audio device")

            def stop(self):
                raise AssertionError("stop must not be called")

        coordinator = VoiceStateCoordinator()
        scheduler = PlaybackScheduler(
            PlaybackContextFactory(coordinator, lambda: NOW),
            PlaybackGate(),
            DeferredPlaybackQueue(),
            AlwaysFailPort(),
            TTSFailureBoundary(max_start_retries=0),
        )
        request = _request()

        result = scheduler.schedule(
            request, session_phase=PlaybackSessionPhase.ACTIVE
        )

        self.assertEqual(result.action, PlaybackScheduleAction.PLAYBACK_FAILED)
        self.assertIs(result.request, request)
        self.assertEqual(result.request.voice_text, "离心时间是多少？")

    def test_non_start_failure_cannot_be_marked_retryable(self):
        boundary = TTSFailureBoundary()

        with self.assertRaisesRegex(ValueError, "只有 START_COMMAND"):
            boundary.record(
                intent_id="voice-failure",
                stage=TTSFailureStage.ACTIVE_PLAYBACK,
                error="failed",
                will_retry=True,
            )


if __name__ == "__main__":
    unittest.main()
