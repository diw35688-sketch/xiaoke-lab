import json
import unittest
from dataclasses import FrozenInstanceError

from src.asr.schemas import ASRResult
from src.core.conversation_turn import (
    ExperimentContext,
    InputSource,
    InteractionMode,
)
from src.core.experiment_turn_input import ExperimentTurnInput


def _asr_result(text="加入了 5 毫升缓冲液", *, is_final=True):
    return ASRResult(
        asr_transcript=text,
        asr_model_raw_text=f"<|zh|>{text}",
        audio_path="audio/segment-7.wav",
        audio_duration_seconds=1.25,
        recognition_seconds=0.31,
        model="SenseVoiceSmall",
        language="zh",
        is_final=is_final,
    )


def _input(**overrides):
    values = {
        "conversation_id": "conversation-7",
        "request_id": "request-21",
        "turn_id": "turn-12",
        "interaction_mode": InteractionMode.EXPERIMENT,
        "experiment_context": ExperimentContext.FREE,
        "mode_version": 4,
        "input_source": InputSource.TEXT,
        "raw_text": "加入了 5 毫升缓冲液",
        "asr_result": None,
    }
    values.update(overrides)
    return ExperimentTurnInput(**values)


class ExperimentTurnInputContractTests(unittest.TestCase):
    def test_text_input_preserves_identity_mode_source_and_original_text(self):
        request = _input()

        self.assertEqual(request.conversation_id, "conversation-7")
        self.assertEqual(request.request_id, "request-21")
        self.assertEqual(request.turn_id, "turn-12")
        self.assertEqual(request.interaction_mode, InteractionMode.EXPERIMENT)
        self.assertEqual(request.experiment_context, ExperimentContext.FREE)
        self.assertEqual(request.mode_version, 4)
        self.assertEqual(request.input_source, InputSource.TEXT)
        self.assertEqual(request.raw_text, "加入了 5 毫升缓冲液")
        self.assertIsNone(request.asr_result)

    def test_each_voice_source_requires_matching_final_asr_evidence(self):
        for source in (
            InputSource.SINGLE_RECORDING,
            InputSource.CONTINUOUS_CALL,
        ):
            with self.subTest(source=source):
                evidence = _asr_result()
                request = _input(input_source=source, asr_result=evidence)

                self.assertIs(request.asr_result, evidence)
                self.assertEqual(request.raw_text, evidence.asr_transcript)

    def test_text_input_cannot_claim_asr_evidence(self):
        with self.assertRaisesRegex(ValueError, "文字输入不能携带 ASR"):
            _input(asr_result=_asr_result())

    def test_voice_input_cannot_omit_asr_evidence(self):
        with self.assertRaisesRegex(ValueError, "语音输入必须携带 ASR"):
            _input(input_source=InputSource.SINGLE_RECORDING)

    def test_voice_input_rejects_non_final_or_mismatched_asr_evidence(self):
        with self.assertRaisesRegex(ValueError, "最终 ASR"):
            _input(
                input_source=InputSource.CONTINUOUS_CALL,
                asr_result=_asr_result(is_final=False),
            )
        with self.assertRaisesRegex(ValueError, "必须与 ASR 忠实转写一致"):
            _input(
                input_source=InputSource.SINGLE_RECORDING,
                raw_text="修改后的文字",
                asr_result=_asr_result(),
            )

    def test_contract_only_accepts_experiment_mode_with_free_or_protocol_context(self):
        with self.assertRaisesRegex(ValueError, "只接受实验模式"):
            _input(
                interaction_mode=InteractionMode.CHAT,
                experiment_context=ExperimentContext.NONE,
            )
        with self.assertRaisesRegex(ValueError, "free 或 protocol"):
            _input(experiment_context=ExperimentContext.NONE)

    def test_identity_text_source_and_mode_version_are_strictly_validated(self):
        with self.assertRaisesRegex(ValueError, "conversation_id"):
            _input(conversation_id=" ")
        with self.assertRaisesRegex(ValueError, "raw_text"):
            _input(raw_text=" ")
        with self.assertRaisesRegex(TypeError, "input_source"):
            _input(input_source="text")
        with self.assertRaisesRegex(TypeError, "正整数"):
            _input(mode_version=True)
        with self.assertRaisesRegex(ValueError, "正整数"):
            _input(mode_version=0)

    def test_contract_is_immutable_and_wire_payload_is_json_safe(self):
        request = _input(
            input_source=InputSource.SINGLE_RECORDING,
            asr_result=_asr_result(),
        )

        with self.assertRaises(FrozenInstanceError):
            request.raw_text = "changed"
        wire = request.to_wire()
        self.assertEqual(json.loads(json.dumps(wire)), wire)
        self.assertEqual(wire["asr_result"]["schema_version"], 2)

    def test_contract_has_no_business_side_effect_methods(self):
        request = _input()

        for forbidden in ("understand", "save", "execute", "route", "speak"):
            self.assertFalse(hasattr(request, forbidden))


if __name__ == "__main__":
    unittest.main()
