import json
import unittest
from datetime import datetime, timezone

from src.asr.schemas import ASRResult
from src.core.conversation_turn import (
    ExperimentContext,
    InputSource,
    InteractionMode,
)
from src.core.turn_input import TurnInput
from src.core.turn_timing import TurnTimingRecorder


def _asr(text="温度八十摄氏度"):
    return ASRResult(
        asr_transcript=text,
        asr_model_raw_text=text,
        audio_path="audio.wav",
        audio_duration_seconds=1.0,
        recognition_seconds=0.1,
        model="fake",
        language="zh",
        is_final=True,
    )


class TurnInputTests(unittest.TestCase):
    def test_chat_text_has_no_lab_session_or_asr(self):
        turn = TurnInput(
            "c1", "r1", "t1", None,
            InteractionMode.CHAT, ExperimentContext.NONE, 1,
            InputSource.TEXT, "你好",
        )
        self.assertIsNone(turn.to_wire()["asr_result"])

    def test_experiment_audio_requires_matching_final_evidence(self):
        turn = TurnInput(
            "c1", "r1", "t1", "lab1",
            InteractionMode.EXPERIMENT, ExperimentContext.FREE, 1,
            InputSource.SINGLE_RECORDING, "温度八十摄氏度", _asr(),
        )
        self.assertEqual(turn.to_wire()["lab_session_id"], "lab1")

    def test_rejects_cross_dimension_conflicts(self):
        with self.assertRaisesRegex(ValueError, "lab_session_id"):
            TurnInput(
                "c1", "r1", "t1", "lab1",
                InteractionMode.CHAT, ExperimentContext.NONE, 1,
                InputSource.TEXT, "你好",
            )
        with self.assertRaisesRegex(ValueError, "ASR"):
            TurnInput(
                "c1", "r1", "t1", "lab1",
                InteractionMode.EXPERIMENT, ExperimentContext.FREE, 1,
                InputSource.SINGLE_RECORDING, "温度八十摄氏度",
            )


class TurnTimingTests(unittest.TestCase):
    def test_marks_are_monotonic_and_idempotent(self):
        ticks = iter([10.0, 10.0, 10.125])
        recorder = TurnTimingRecorder(
            monotonic=lambda: next(ticks),
            wall_clock=lambda: datetime(2026, 8, 26, tzinfo=timezone.utc),
        )
        first = recorder.mark("understanding_started")
        self.assertEqual(first["elapsed_ms"], 125)
        self.assertEqual(recorder.mark("understanding_started"), first)


class TurnStreamContractTests(unittest.TestCase):
    def test_sse_serializes_utf8_and_status(self):
        from web.turn_stream_contract import sse_event, turn_status_event

        encoded = sse_event(turn_status_event("saving", "正在保存…", elapsed_ms=8))
        self.assertTrue(encoded.startswith("data: "))
        payload = json.loads(encoded[6:].strip())
        self.assertEqual(payload["phase"], "saving")
        self.assertEqual(payload["elapsed_ms"], 8)


if __name__ == "__main__":
    unittest.main()
