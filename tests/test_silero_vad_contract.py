import unittest

from src.core.silero_vad_contract import (
    SILERO_FRAME_SAMPLES,
    SileroVadAdapter,
    SileroVadEvent,
    SileroVadEventType,
    SileroVadFailure,
    SileroVadFailureCode,
    SileroVadFallback,
    SileroVadFrame,
    SileroVadResult,
    to_voice_runtime_event,
)
from src.core.voice_runtime_state import VoiceRuntimeEventType


def _samples(value=0.0):
    return (value,) * SILERO_FRAME_SAMPLES


class SileroVadContractTests(unittest.TestCase):
    def test_frame_contract_is_immutable_16k_mono_512_float_samples(self):
        frame = SileroVadFrame(sequence=0, captured_at=1.25, samples=_samples())

        self.assertEqual(frame.sample_rate, 16_000)
        self.assertEqual(len(frame.samples), 512)
        with self.assertRaises(AttributeError):
            frame.sequence = 1

    def test_frame_rejects_wrong_rate_size_and_sample_range(self):
        with self.assertRaisesRegex(ValueError, "16000"):
            SileroVadFrame(0, 0.0, _samples(), sample_rate=48_000)
        with self.assertRaisesRegex(ValueError, "512"):
            SileroVadFrame(0, 0.0, (0.0,))
        with self.assertRaisesRegex(ValueError, "\[-1.0, 1.0\]"):
            SileroVadFrame(0, 0.0, _samples(1.1))

    def test_each_vad_event_maps_to_existing_coordinator_fact(self):
        expected = {
            SileroVadEventType.SPEECH_STARTED: VoiceRuntimeEventType.USER_SPEECH_STARTED,
            SileroVadEventType.SPEECH_PAUSED: VoiceRuntimeEventType.USER_SPEECH_PAUSED,
            SileroVadEventType.SPEECH_RESUMED: VoiceRuntimeEventType.USER_SPEECH_RESUMED,
            SileroVadEventType.SEGMENT_FINALIZED: VoiceRuntimeEventType.SEGMENT_FINALIZED,
        }

        for source, target in expected.items():
            with self.subTest(source=source):
                mapped = to_voice_runtime_event(SileroVadEvent(source, 2.0))
                self.assertIs(mapped.event_type, target)

    def test_failure_always_selects_existing_rms_as_safe_fallback(self):
        for code in SileroVadFailureCode:
            with self.subTest(code=code):
                failure = SileroVadFailure(code=code, detail="detector unavailable")
                self.assertIs(failure.fallback, SileroVadFallback.USE_RMS)

    def test_result_never_mixes_failure_with_state_events(self):
        event = SileroVadEvent(SileroVadEventType.SPEECH_STARTED, 0.5)
        failure = SileroVadFailure(
            SileroVadFailureCode.INFERENCE_FAILED,
            "inference failed",
        )

        self.assertEqual(SileroVadResult(events=(event,)).events, (event,))
        self.assertIs(SileroVadResult(failure=failure).failure, failure)
        with self.assertRaisesRegex(ValueError, "不能同时"):
            SileroVadResult(events=(event,), failure=failure)

    def test_adapter_port_can_be_implemented_without_model_dependency(self):
        class FakeAdapter:
            def accept(self, frame):
                return SileroVadResult()

            def reset(self):
                return None

        self.assertIsInstance(FakeAdapter(), SileroVadAdapter)

    def test_contract_has_no_microphone_model_or_coordinator_mutation_api(self):
        for name in ("start_microphone", "load_model", "consume", "play", "stop"):
            with self.subTest(name=name):
                self.assertFalse(hasattr(SileroVadAdapter, name))


if __name__ == "__main__":
    unittest.main()
