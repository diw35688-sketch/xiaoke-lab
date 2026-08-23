import unittest
from datetime import datetime, timezone

from src.core.playback_context import PlaybackSessionPhase
from src.core.playback_context_factory import PlaybackContextFactory
from src.core.presentation_intent import MessagePriority
from src.core.voice_runtime_state import (
    VoiceRuntimeEvent,
    VoiceRuntimeEventType,
    VoiceRuntimeState,
    VoiceStateCoordinator,
)


OBSERVED_AT = datetime(2026, 8, 23, 11, 30, tzinfo=timezone.utc)


def _factory(state=None, *, clock=lambda: OBSERVED_AT):
    coordinator = VoiceStateCoordinator(state)
    return PlaybackContextFactory(coordinator, clock), coordinator


class PlaybackContextFactoryTests(unittest.TestCase):
    def test_idle_runtime_is_copied_with_injected_time_and_phase(self):
        factory, _ = _factory()

        context = factory.create(session_phase=PlaybackSessionPhase.ACTIVE)

        self.assertEqual(context.observed_at, OBSERVED_AT)
        self.assertEqual(context.session_phase, PlaybackSessionPhase.ACTIVE)
        self.assertFalse(context.user_speaking)
        self.assertFalse(context.voice_input_busy)
        self.assertFalse(context.tts_playing)

    def test_open_segment_maps_to_voice_input_busy_during_short_pause(self):
        state = VoiceRuntimeState(segment_capturing=True)
        factory, _ = _factory(state)

        context = factory.create(session_phase=PlaybackSessionPhase.ACTIVE)

        self.assertFalse(context.user_speaking)
        self.assertTrue(context.voice_input_busy)

    def test_asr_processing_maps_to_voice_input_busy_after_segment_finalized(self):
        state = VoiceRuntimeState(asr_processing=True)
        factory, _ = _factory(state)

        context = factory.create(session_phase=PlaybackSessionPhase.ACTIVE)

        self.assertTrue(context.voice_input_busy)

    def test_input_window_stays_closed_when_capture_and_asr_overlap(self):
        state = VoiceRuntimeState(segment_capturing=True, asr_processing=True)
        factory, _ = _factory(state)

        context = factory.create(session_phase=PlaybackSessionPhase.ACTIVE)

        self.assertTrue(context.voice_input_busy)

    def test_tts_fact_and_priority_are_copied_together(self):
        state = VoiceRuntimeState(
            tts_playing=True,
            active_tts_priority=MessagePriority.DIRECT_ACK,
        )
        factory, _ = _factory(state)

        context = factory.create(session_phase=PlaybackSessionPhase.CLOSING)

        self.assertTrue(context.tts_playing)
        self.assertEqual(
            context.active_tts_priority, MessagePriority.DIRECT_ACK
        )

    def test_created_context_does_not_change_after_runtime_changes(self):
        factory, coordinator = _factory()
        context = factory.create(session_phase=PlaybackSessionPhase.ACTIVE)

        coordinator.consume(
            VoiceRuntimeEvent(
                event_type=VoiceRuntimeEventType.USER_SPEECH_STARTED
            )
        )

        self.assertFalse(context.user_speaking)
        self.assertFalse(context.voice_input_busy)
        updated = factory.create(session_phase=PlaybackSessionPhase.ACTIVE)
        self.assertTrue(updated.user_speaking)
        self.assertTrue(updated.voice_input_busy)

    def test_clock_is_called_once_per_snapshot(self):
        calls = []

        def clock():
            calls.append("called")
            return OBSERVED_AT

        factory, _ = _factory(clock=clock)

        factory.create(session_phase=PlaybackSessionPhase.ACTIVE)

        self.assertEqual(calls, ["called"])

    def test_invalid_clock_result_is_rejected_by_context_contract(self):
        factory, _ = _factory(clock=lambda: datetime(2026, 8, 23, 11, 30))

        with self.assertRaisesRegex(ValueError, "时区"):
            factory.create(session_phase=PlaybackSessionPhase.ACTIVE)

    def test_invalid_dependencies_and_phase_are_rejected(self):
        with self.assertRaisesRegex(TypeError, "coordinator"):
            PlaybackContextFactory(object(), lambda: OBSERVED_AT)
        with self.assertRaisesRegex(TypeError, "clock"):
            PlaybackContextFactory(VoiceStateCoordinator(), OBSERVED_AT)

        factory, _ = _factory()
        with self.assertRaisesRegex(TypeError, "session_phase"):
            factory.create(session_phase="active")

    def test_factory_has_no_state_write_decision_queue_or_device_api(self):
        factory, _ = _factory()

        for name in (
            "consume",
            "decide",
            "evaluate",
            "enqueue",
            "defer",
            "play",
            "stop",
            "transcribe",
        ):
            with self.subTest(name=name):
                self.assertFalse(hasattr(factory, name))


if __name__ == "__main__":
    unittest.main()
