import unittest

from src.core.protocol import ProtocolStep
from src.core.protocol_missing_fields import compute_missing_fields
from src.llm.schemas import ExperimentEntities


class ProtocolMissingFieldsNewSemanticsTests(unittest.TestCase):
    def test_protocol_value_does_not_count_as_missing_field(self):
        step = ProtocolStep(
            step_number=1,
            title="加热",
            instruction="加热到60摄氏度并保持10分钟。",
            protocol_values={
                "temperature": "60摄氏度",
                "duration": "10分钟",
            },
            must_record=("observation",),
            terms=(),
            hazard_note=None,
        )

        self.assertEqual(
            compute_missing_fields(step, ExperimentEntities()),
            ("observation",),
        )

    def test_actual_measurement_is_required_even_when_protocol_target_exists(self):
        step = ProtocolStep(
            step_number=1,
            title="称量",
            instruction="称取3.58g试剂并记录实际质量。",
            protocol_values={
                "amount_value": "3.58",
                "amount_unit": "g",
            },
            must_record=("amount_value",),
            terms=(),
            hazard_note=None,
        )

        self.assertEqual(
            compute_missing_fields(
                step,
                ExperimentEntities(amount_unit="g"),
            ),
            ("amount_value",),
        )

    def test_spoken_actual_value_fills_must_record(self):
        step = ProtocolStep(
            step_number=1,
            title="滴定",
            instruction="记录实际消耗体积。",
            protocol_values={"amount_unit": "mL"},
            must_record=("amount_value", "observation"),
            terms=(),
            hazard_note=None,
        )

        self.assertEqual(
            compute_missing_fields(
                step,
                ExperimentEntities(
                    amount_value="24.7",
                    observation="浅粉红色",
                ),
            ),
            (),
        )


if __name__ == "__main__":
    unittest.main()
