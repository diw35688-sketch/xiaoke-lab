import unittest
from datetime import datetime, timedelta, timezone

from src.core.deferred_playback_queue import DeferredPlaybackQueue
from src.core.playback_context import PlaybackSessionPhase
from src.core.playback_context_factory import PlaybackContextFactory
from src.core.playback_decision import PlaybackDisposition, PlaybackReason
from src.core.playback_gate import PlaybackGate
from src.core.playback_request import PlaybackRequest
from src.core.playback_scheduler import PlaybackScheduleAction, PlaybackScheduler
from src.core.presentation_intent import MessageKind, MessagePriority
from src.core.tts_adapter import TTSAdapter, TTSExecutionEventType
from src.core.tts_adapter import TTSExecutionEvent
from src.core.voice_runtime_state import VoiceStateCoordinator


NOW = datetime(2026, 8, 23, 16, 0, tzinfo=timezone.utc)


class FakeTTSDriver:
    def __init__(self):
        self.play_calls = []
        self.stop_calls = 0
        self._report = None

    def play(self, request, report):
        self.play_calls.append(request)
        self._report = report

    def stop(self):
        self.stop_calls += 1

    def emit(self, event_type, error=None):
        self._report(event_type, error)


def _request(intent_id, priority, *, ttl=timedelta(seconds=20)):
    return PlaybackRequest(
        intent_id=intent_id,
        kind=MessageKind.SAFETY_ALERT,
        priority=priority,
        voice_text=f"voice {intent_id}",
        created_at=NOW,
        ttl=ttl,
    )


class PlaybackPreemptionTests(unittest.TestCase):
    def _system(self):
        current_time = [NOW]
        current_phase = [PlaybackSessionPhase.ACTIVE]
        coordinator = VoiceStateCoordinator()
        driver = FakeTTSDriver()
        resumed_results = []
        scheduler_holder = []

        def sink(event):
            result = scheduler_holder[0].handle_tts_event(
                event, session_phase=current_phase[0]
            )
            if result is not None:
                resumed_results.append(result)

        adapter = TTSAdapter(driver, coordinator, sink)
        scheduler = PlaybackScheduler(
            PlaybackContextFactory(coordinator, lambda: current_time[0]),
            PlaybackGate(),
            DeferredPlaybackQueue(),
            adapter,
        )
        scheduler_holder.append(scheduler)
        return (
            scheduler,
            driver,
            coordinator,
            current_time,
            current_phase,
            resumed_results,
        )

    def _start_low_priority(self, scheduler, driver):
        old = _request("old", MessagePriority.DIRECT_ACK)
        result = scheduler.schedule(
            old, session_phase=PlaybackSessionPhase.ACTIVE
        )
        self.assertEqual(result.action, PlaybackScheduleAction.HANDED_TO_TTS)
        driver.emit(TTSExecutionEventType.STARTED)
        return old

    def test_critical_waits_for_matching_stopped_then_revalidates_and_plays(self):
        scheduler, driver, coordinator, _, _, resumed = self._system()
        self._start_low_priority(scheduler, driver)
        critical = _request("critical", MessagePriority.CRITICAL)

        requested = scheduler.schedule(
            critical, session_phase=PlaybackSessionPhase.ACTIVE
        )

        self.assertEqual(
            requested.action,
            PlaybackScheduleAction.PREEMPT_STOP_REQUESTED,
        )
        self.assertEqual(driver.stop_calls, 1)
        self.assertEqual([item.intent_id for item in driver.play_calls], ["old"])
        self.assertTrue(coordinator.snapshot().tts_playing)

        driver.emit(TTSExecutionEventType.STOPPED)

        self.assertEqual(len(resumed), 1)
        self.assertEqual(
            resumed[0].action, PlaybackScheduleAction.HANDED_TO_TTS
        )
        self.assertEqual(
            [item.intent_id for item in driver.play_calls],
            ["old", "critical"],
        )

    def test_expired_critical_is_dropped_after_stopped_revalidation(self):
        scheduler, driver, _, current_time, _, resumed = self._system()
        self._start_low_priority(scheduler, driver)
        critical = _request(
            "critical", MessagePriority.CRITICAL, ttl=timedelta(seconds=1)
        )
        scheduler.schedule(
            critical, session_phase=PlaybackSessionPhase.ACTIVE
        )
        current_time[0] = NOW + timedelta(seconds=1)

        driver.emit(TTSExecutionEventType.STOPPED)

        self.assertEqual(resumed[0].action, PlaybackScheduleAction.DROPPED)
        self.assertEqual(resumed[0].decision.reason, PlaybackReason.EXPIRED)
        self.assertEqual([item.intent_id for item in driver.play_calls], ["old"])

    def test_ended_session_drops_critical_after_stopped_revalidation(self):
        scheduler, driver, _, _, current_phase, resumed = self._system()
        self._start_low_priority(scheduler, driver)
        scheduler.schedule(
            _request("critical", MessagePriority.CRITICAL),
            session_phase=PlaybackSessionPhase.ACTIVE,
        )
        current_phase[0] = PlaybackSessionPhase.ENDED

        driver.emit(TTSExecutionEventType.STOPPED)

        self.assertEqual(resumed[0].decision.disposition, PlaybackDisposition.DROP)
        self.assertEqual(
            resumed[0].decision.reason, PlaybackReason.SESSION_ENDED
        )

    def test_ordinary_request_never_calls_stop(self):
        scheduler, driver, _, _, _, _ = self._system()
        self._start_low_priority(scheduler, driver)

        result = scheduler.schedule(
            _request("ordinary", MessagePriority.ACTIVE_QUESTION),
            session_phase=PlaybackSessionPhase.ACTIVE,
        )

        self.assertEqual(result.action, PlaybackScheduleAction.QUEUED)
        self.assertEqual(result.decision.reason, PlaybackReason.TTS_BUSY)
        self.assertEqual(driver.stop_calls, 0)

    def test_unrelated_stopped_event_cannot_resume_pending_preemption(self):
        scheduler, driver, _, _, _, resumed = self._system()
        self._start_low_priority(scheduler, driver)
        scheduler.schedule(
            _request("critical", MessagePriority.CRITICAL),
            session_phase=PlaybackSessionPhase.ACTIVE,
        )

        unrelated = scheduler.handle_tts_event(
            TTSExecutionEvent(
                TTSExecutionEventType.STOPPED,
                "another-playback",
                MessagePriority.DIRECT_ACK,
            ),
            session_phase=PlaybackSessionPhase.ACTIVE,
        )

        self.assertIsNone(unrelated)
        self.assertEqual(resumed, [])
        self.assertEqual([item.intent_id for item in driver.play_calls], ["old"])

        driver.emit(TTSExecutionEventType.STOPPED)
        self.assertEqual(resumed[0].action, PlaybackScheduleAction.HANDED_TO_TTS)

    def test_same_priority_critical_does_not_preempt(self):
        scheduler, driver, _, _, _, _ = self._system()
        critical = _request("old-critical", MessagePriority.CRITICAL)
        scheduler.schedule(
            critical, session_phase=PlaybackSessionPhase.ACTIVE
        )
        driver.emit(TTSExecutionEventType.STARTED)

        result = scheduler.schedule(
            _request("new-critical", MessagePriority.CRITICAL),
            session_phase=PlaybackSessionPhase.ACTIVE,
        )

        self.assertEqual(result.action, PlaybackScheduleAction.QUEUED)
        self.assertEqual(driver.stop_calls, 0)


if __name__ == "__main__":
    unittest.main()
