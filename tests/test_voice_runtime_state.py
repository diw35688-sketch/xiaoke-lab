import unittest

from src.core.presentation_intent import MessagePriority
from src.core.voice_runtime_state import (
    VoiceRuntimeEvent,
    VoiceRuntimeEventType,
    VoiceRuntimeState,
    VoiceStateCoordinator,
)


def _event(event_type, *, priority=None):
    return VoiceRuntimeEvent(event_type=event_type, tts_priority=priority)


class VoiceRuntimeStateTests(unittest.TestCase):
    def test_default_state_is_idle_and_immutable(self):
        state = VoiceRuntimeState()

        self.assertFalse(state.user_speaking)
        self.assertFalse(state.segment_capturing)
        self.assertFalse(state.asr_processing)
        self.assertFalse(state.tts_playing)
        with self.assertRaises(AttributeError):
            state.user_speaking = True

    def test_state_rejects_impossible_speech_without_capture(self):
        with self.assertRaisesRegex(ValueError, "片段采集"):
            VoiceRuntimeState(user_speaking=True)

    def test_state_rejects_stale_or_missing_tts_priority(self):
        with self.assertRaisesRegex(ValueError, "同时"):
            VoiceRuntimeState(tts_playing=True)
        with self.assertRaisesRegex(ValueError, "同时"):
            VoiceRuntimeState(active_tts_priority=MessagePriority.DIRECT_ACK)

    def test_short_pause_keeps_segment_open_and_resume_uses_same_segment(self):
        coordinator = VoiceStateCoordinator()
        coordinator.consume(_event(VoiceRuntimeEventType.USER_SPEECH_STARTED))

        paused = coordinator.consume(
            _event(VoiceRuntimeEventType.USER_SPEECH_PAUSED)
        )
        resumed = coordinator.consume(
            _event(VoiceRuntimeEventType.USER_SPEECH_RESUMED)
        )

        self.assertFalse(paused.user_speaking)
        self.assertTrue(paused.segment_capturing)
        self.assertTrue(resumed.user_speaking)
        self.assertTrue(resumed.segment_capturing)

    def test_segment_must_pause_before_finalize(self):
        coordinator = VoiceStateCoordinator()
        speaking = coordinator.consume(
            _event(VoiceRuntimeEventType.USER_SPEECH_STARTED)
        )

        with self.assertRaisesRegex(ValueError, "停顿"):
            coordinator.consume(_event(VoiceRuntimeEventType.SEGMENT_FINALIZED))

        self.assertIs(coordinator.snapshot(), speaking)

    def test_finalized_segment_can_enter_and_leave_asr_processing(self):
        coordinator = VoiceStateCoordinator()
        for kind in (
            VoiceRuntimeEventType.USER_SPEECH_STARTED,
            VoiceRuntimeEventType.USER_SPEECH_PAUSED,
            VoiceRuntimeEventType.SEGMENT_FINALIZED,
        ):
            coordinator.consume(_event(kind))

        processing = coordinator.consume(
            _event(VoiceRuntimeEventType.ASR_PROCESSING_STARTED)
        )
        finished = coordinator.consume(
            _event(VoiceRuntimeEventType.ASR_PROCESSING_FINISHED)
        )

        self.assertTrue(processing.asr_processing)
        self.assertFalse(finished.asr_processing)

    def test_asr_failure_also_clears_processing_fact(self):
        coordinator = VoiceStateCoordinator(
            VoiceRuntimeState(asr_processing=True)
        )

        state = coordinator.consume(
            _event(VoiceRuntimeEventType.ASR_PROCESSING_FAILED)
        )

        self.assertFalse(state.asr_processing)

    def test_tts_lifecycle_tracks_priority_and_all_terminal_events(self):
        for terminal in (
            VoiceRuntimeEventType.TTS_FINISHED,
            VoiceRuntimeEventType.TTS_STOPPED,
            VoiceRuntimeEventType.TTS_FAILED,
        ):
            with self.subTest(terminal=terminal):
                coordinator = VoiceStateCoordinator()
                playing = coordinator.consume(
                    _event(
                        VoiceRuntimeEventType.TTS_STARTED,
                        priority=MessagePriority.DIRECT_ACK,
                    )
                )
                ended = coordinator.consume(_event(terminal))

                self.assertTrue(playing.tts_playing)
                self.assertEqual(
                    playing.active_tts_priority, MessagePriority.DIRECT_ACK
                )
                self.assertFalse(ended.tts_playing)
                self.assertIsNone(ended.active_tts_priority)

    def test_tts_start_requires_priority_and_other_events_reject_it(self):
        with self.assertRaisesRegex(ValueError, "必须携带"):
            _event(VoiceRuntimeEventType.TTS_STARTED)
        with self.assertRaisesRegex(ValueError, "只有 TTS_STARTED"):
            _event(
                VoiceRuntimeEventType.TTS_FINISHED,
                priority=MessagePriority.DIRECT_ACK,
            )

    def test_invalid_event_order_does_not_mutate_state(self):
        coordinator = VoiceStateCoordinator()
        original = coordinator.snapshot()

        with self.assertRaisesRegex(ValueError, "没有正在播放"):
            coordinator.consume(_event(VoiceRuntimeEventType.TTS_FINISHED))

        self.assertIs(coordinator.snapshot(), original)

    def test_user_speech_started_ends_old_tts_occupancy_for_barge_in(self):
        coordinator = VoiceStateCoordinator()
        coordinator.consume(
            _event(
                VoiceRuntimeEventType.TTS_STARTED,
                priority=MessagePriority.DIRECT_ACK,
            )
        )

        state = coordinator.consume(
            _event(VoiceRuntimeEventType.USER_SPEECH_STARTED)
        )

        self.assertTrue(state.user_speaking)
        self.assertTrue(state.segment_capturing)
        self.assertFalse(state.tts_playing)
        self.assertIsNone(state.active_tts_priority)

    def test_user_speech_resumed_ends_old_tts_occupancy_for_barge_in(self):
        coordinator = VoiceStateCoordinator(
            VoiceRuntimeState(
                segment_capturing=True,
                tts_playing=True,
                active_tts_priority=MessagePriority.DIRECT_ACK,
            )
        )

        state = coordinator.consume(
            _event(VoiceRuntimeEventType.USER_SPEECH_RESUMED)
        )

        self.assertTrue(state.user_speaking)
        self.assertTrue(state.segment_capturing)
        self.assertFalse(state.tts_playing)
        self.assertIsNone(state.active_tts_priority)

    def test_coordinator_has_no_device_context_or_decision_api(self):
        coordinator = VoiceStateCoordinator()

        for name in (
            "record",
            "transcribe",
            "play",
            "stop",
            "create_context",
            "decide",
            "enqueue",
        ):
            with self.subTest(name=name):
                self.assertFalse(hasattr(coordinator, name))

    def test_contract_objects_reject_raw_values(self):
        with self.assertRaisesRegex(TypeError, "event_type"):
            VoiceRuntimeEvent(event_type="tts_started")
        with self.assertRaisesRegex(TypeError, "event"):
            VoiceStateCoordinator().consume("tts_started")
        with self.assertRaisesRegex(TypeError, "user_speaking"):
            VoiceRuntimeState(user_speaking=1, segment_capturing=True)


if __name__ == "__main__":
    unittest.main()
