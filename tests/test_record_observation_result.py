import json
import unittest
from dataclasses import FrozenInstanceError

from src.core.record_observation_result import (
    ExtractionSource,
    RecordObservationResult,
    RecordStructureStatus,
)


def _result(**overrides):
    defaults = {
        "session_id": "session-1",
        "segment_id": 2,
        "transcript": "将样品加热到六十摄氏度。",
        "entities": {"temperature": "60摄氏度"},
        "extraction_source": ExtractionSource.RULE,
        "structure_status": RecordStructureStatus.STRUCTURED,
        "missing_fields": ("duration",),
        "follow_up_question": "加热了多长时间？",
        "deviations": ({"field": "temperature", "actual_value": "60"},),
    }
    defaults.update(overrides)
    return RecordObservationResult(**defaults)


class RecordObservationResultTests(unittest.TestCase):
    def test_saved_structured_result_preserves_shared_facts(self):
        result = _result()
        self.assertTrue(result.persisted)
        self.assertEqual(result.session_id, "session-1")
        self.assertEqual(result.segment_id, 2)
        self.assertEqual(result.entities["temperature"], "60摄氏度")
        self.assertEqual(result.missing_fields, ("duration",))
        self.assertEqual(result.follow_up_question, "加热了多长时间？")

    def test_degraded_saved_result_is_explicit(self):
        result = _result(
            entities={},
            extraction_source=ExtractionSource.DEGRADED,
            structure_status=RecordStructureStatus.DEGRADED,
            missing_fields=(),
            follow_up_question=None,
            deviations=(),
        )
        self.assertTrue(result.persisted)
        self.assertEqual(result.structure_status, RecordStructureStatus.DEGRADED)

    def test_rejects_missing_fields_without_question(self):
        with self.assertRaisesRegex(ValueError, "必须提供"):
            _result(follow_up_question=None)

    def test_rejects_inconsistent_degraded_status(self):
        with self.assertRaisesRegex(ValueError, "降级语义一致"):
            _result(
                extraction_source=ExtractionSource.DEGRADED,
                structure_status=RecordStructureStatus.STRUCTURED,
            )

    def test_result_and_nested_mappings_are_immutable(self):
        result = _result()
        with self.assertRaises(FrozenInstanceError):
            result.segment_id = 3
        with self.assertRaises(TypeError):
            result.entities["duration"] = "10分钟"
        with self.assertRaises(TypeError):
            result.deviations[0]["field"] = "duration"

    def test_as_dict_is_json_serializable_and_detached(self):
        result = _result()
        payload = result.as_dict()
        json.dumps(payload, ensure_ascii=False)
        payload["entities"]["temperature"] = "70摄氏度"
        self.assertEqual(result.entities["temperature"], "60摄氏度")


if __name__ == "__main__":
    unittest.main()
