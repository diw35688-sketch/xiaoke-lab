import unittest

from src.core.protocol import ExperimentProtocol, ProtocolStep, FieldValueSource
from src.core.protocol_segment_evaluation import evaluate_segment
from src.core.protocol_selection import ProtocolSelection
from src.core.protocol_session import ProtocolSessionState
from src.llm.schemas import ExperimentEntities


def make_state(*, field_prompts=None):
    step = ProtocolStep(
        step_number=1,
        title="称量",
        instruction="称取目标质量并记录实测值。",
        protocol_values={"action": "称量", "amount_unit": "g", "amount_value": "3.58"},
        must_record=("amount_value", "observation"),
        terms=(),
        hazard_note=None,
        field_prompts=field_prompts or {},
    )
    protocol = ExperimentProtocol(
        protocol_id="evaluation-demo",
        title="评估方案",
        source="测试",
        version="1.0",
        steps=(step,),
        schema_version=1,
    )
    return ProtocolSessionState.start(ProtocolSelection.selected(protocol))


class SegmentEvaluationTests(unittest.TestCase):
    def test_all_missing_uses_specific_prompts(self):
        result = evaluate_segment(
            make_state(field_prompts={
                "amount_value": "实际称了多少克？",
                "observation": "称量后看到什么？",
            }),
            ExperimentEntities(),
        )

        self.assertEqual(result.missing_fields, ("amount_value", "observation"))
        self.assertEqual(result.follow_up_question, "实际称了多少克？ 称量后看到什么？")
        self.assertTrue(result.follow_up_required)
        self.assertEqual(result.deviations, ())
        self.assertEqual(result.sourced_values["action"].source, FieldValueSource.PROTOCOL_DEFAULT)

    def test_partial_missing_only_asks_for_remaining_field(self):
        result = evaluate_segment(
            make_state(field_prompts={"observation": "称量后看到什么？"}),
            ExperimentEntities(amount_value="3.61"),
        )

        self.assertEqual(result.missing_fields, ("observation",))
        self.assertEqual(result.follow_up_question, "称量后看到什么？")
        self.assertEqual(len(result.deviations), 1)

    def test_all_provided_has_no_follow_up(self):
        result = evaluate_segment(
            make_state(field_prompts={
                "amount_value": "实际称了多少克？",
                "observation": "称量后看到什么？",
            }),
            ExperimentEntities(amount_value="3.58", observation="白色粉末"),
        )

        self.assertEqual(result.missing_fields, ())
        self.assertIsNone(result.follow_up_question)
        self.assertFalse(result.follow_up_required)
        self.assertEqual(result.deviations, ())

    def test_protocol_value_deviation_is_returned_without_follow_up(self):
        result = evaluate_segment(
            make_state(field_prompts={"observation": "称量后看到什么？"}),
            ExperimentEntities(amount_value="3.61", observation="白色粉末"),
        )

        self.assertFalse(result.follow_up_required)
        self.assertIsNone(result.follow_up_question)
        self.assertEqual(result.deviations[0].field_name, "amount_value")
        self.assertEqual(result.deviations[0].protocol_value, "3.58")
        self.assertEqual(result.deviations[0].actual_value, "3.61")

    def test_missing_prompt_uses_explicit_field_name_fallback(self):
        result = evaluate_segment(make_state(), ExperimentEntities())

        self.assertEqual(
            result.follow_up_question,
            "请补充现场记录：amount_value。 请补充现场记录：observation。",
        )

    def test_free_mode_never_generates_protocol_follow_up_or_deviation(self):
        result = evaluate_segment(
            ProtocolSessionState.start(ProtocolSelection.free_mode()),
            ExperimentEntities(amount_value="3.61", observation="白色粉末"),
        )

        self.assertEqual(result.missing_fields, ())
        self.assertIsNone(result.follow_up_question)
        self.assertEqual(result.deviations, ())
        self.assertEqual(dict(result.sourced_values), {})
        self.assertFalse(result.follow_up_required)


if __name__ == "__main__":
    unittest.main()
