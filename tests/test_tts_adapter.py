import unittest
from datetime import datetime, timedelta, timezone

from src.core.playback_context import PlaybackSessionPhase
from src.core.playback_context_factory import PlaybackContextFactory
from src.core.playback_gate import PlaybackGate
from src.core.playback_request import PlaybackRequest
from src.core.playback_scheduler import PlaybackScheduleAction, PlaybackScheduler
from src.core.deferred_playback_queue import DeferredPlaybackQueue
from src.core.presentation_intent import MessageKind, MessagePriority
from src.core.tts_adapter import (
    TTSAdapter,
    TTSExecutionEvent,
    TTSExecutionEventType,
)
from src.core.voice_runtime_state import VoiceStateCoordinator


NOW = datetime(2026, 8, 23, 15, 0, tzinfo=timezone.utc)


def _request(intent_id="voice-1"):
    return PlaybackRequest(
        intent_id=intent_id,
        kind=MessageKind.CLARIFICATION,
        priority=MessagePriority.ACTIVE_QUESTION,
        voice_text="离心时间是多少？",
        created_at=NOW,
        ttl=timedelta(seconds=20),
    )


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

    def emit(self, signal, error=None):
        self._report(signal, error)


def _adapter():
    driver = FakeTTSDriver()
    coordinator = VoiceStateCoordinator()
    events = []
    adapter = TTSAdapter(driver, coordinator, events.append)
    return adapter, driver, coordinator, events


class TTSAdapterTests(unittest.TestCase):
    def test_play_command_waits_for_started_fact(self):
        adapter, driver, coordinator, events = _adapter()
        request = _request()

        adapter.play(request)

        self.assertEqual(driver.play_calls, [request])
        self.assertFalse(coordinator.snapshot().tts_playing)
        self.assertEqual(events, [])

        driver.emit(TTSExecutionEventType.STARTED)
        self.assertTrue(coordinator.snapshot().tts_playing)
        self.assertEqual(
            events,
            [
                TTSExecutionEvent(
                    TTSExecutionEventType.STARTED,
                    request.intent_id,
                    request.priority,
                )
            ],
        )

    def test_finished_clears_runtime_and_reports_same_intent(self):
        adapter, driver, coordinator, events = _adapter()
        request = _request()
        adapter.play(request)
        driver.emit(TTSExecutionEventType.STARTED)

        driver.emit(TTSExecutionEventType.FINISHED)

        self.assertFalse(coordinator.snapshot().tts_playing)
        self.assertEqual(events[-1].event_type, TTSExecutionEventType.FINISHED)
        self.assertEqual(events[-1].intent_id, request.intent_id)

    def test_stop_command_waits_for_stopped_fact(self):
        adapter, driver, coordinator, events = _adapter()
        adapter.play(_request())
        driver.emit(TTSExecutionEventType.STARTED)

        adapter.stop()

        self.assertEqual(driver.stop_calls, 1)
        self.assertTrue(coordinator.snapshot().tts_playing)
        self.assertEqual(events[-1].event_type, TTSExecutionEventType.STARTED)

        driver.emit(TTSExecutionEventType.STOPPED)
        self.assertFalse(coordinator.snapshot().tts_playing)
        self.assertEqual(events[-1].event_type, TTSExecutionEventType.STOPPED)

    def test_failed_requires_error_and_clears_active_playback(self):
        adapter, driver, coordinator, events = _adapter()
        adapter.play(_request())
        driver.emit(TTSExecutionEventType.STARTED)

        driver.emit(TTSExecutionEventType.FAILED, "speaker unavailable")

        self.assertFalse(coordinator.snapshot().tts_playing)
        self.assertEqual(events[-1].event_type, TTSExecutionEventType.FAILED)
        self.assertEqual(events[-1].error, "speaker unavailable")

    def test_terminal_signal_before_started_is_rejected_without_event(self):
        adapter, driver, coordinator, events = _adapter()
        adapter.play(_request())

        with self.assertRaisesRegex(RuntimeError, "没有 STARTED"):
            driver.emit(TTSExecutionEventType.FINISHED)

        self.assertFalse(coordinator.snapshot().tts_playing)
        self.assertEqual(events, [])

    def test_second_play_is_rejected_while_pending_or_active(self):
        adapter, driver, _, _ = _adapter()
        adapter.play(_request("first"))
        with self.assertRaisesRegex(RuntimeError, "已有"):
            adapter.play(_request("second"))

        driver.emit(TTSExecutionEventType.STARTED)
        with self.assertRaisesRegex(RuntimeError, "已有"):
            adapter.play(_request("second"))

    def test_stop_requires_started_playback(self):
        adapter, _, _, _ = _adapter()

        with self.assertRaisesRegex(RuntimeError, "没有已 STARTED"):
            adapter.stop()

    def test_event_contract_rejects_ambiguous_error_fields(self):
        with self.assertRaisesRegex(ValueError, "必须携带"):
            TTSExecutionEvent(
                TTSExecutionEventType.FAILED,
                "voice-1",
                MessagePriority.ACTIVE_QUESTION,
            )
        with self.assertRaisesRegex(ValueError, "只有 FAILED"):
            TTSExecutionEvent(
                TTSExecutionEventType.FINISHED,
                "voice-1",
                MessagePriority.ACTIVE_QUESTION,
                "unexpected",
            )

    def test_adapter_satisfies_scheduler_playback_port(self):
        adapter, driver, _, _ = _adapter()
        coordinator = VoiceStateCoordinator()
        scheduler = PlaybackScheduler(
            PlaybackContextFactory(coordinator, lambda: NOW),
            PlaybackGate(),
            DeferredPlaybackQueue(),
            adapter,
        )

        result = scheduler.schedule(
            _request(), session_phase=PlaybackSessionPhase.ACTIVE
        )

        self.assertEqual(result.action, PlaybackScheduleAction.HANDED_TO_TTS)
        self.assertEqual(driver.play_calls, [_request()])


if __name__ == "__main__":
    unittest.main()
