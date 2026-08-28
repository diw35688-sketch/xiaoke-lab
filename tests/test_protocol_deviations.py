import unittest

from src.core.protocol import ProtocolStep
from src.core.protocol_deviations import (
    ProtocolDeviation,
    detect_protocol_deviations,
)
from src.llm.schemas import ExperimentEntities


def make_step(**changes):
    values = {
        "step_number": 1,
        "title": "加热溶液",
        "instruction": "加热到60摄氏度并保持10分钟。",
        "protocol_values": {
            "temperature": "60摄氏度",
            "duration": "10分钟",
        },
        "must_record": ("temperature", "duration"),
        "terms": (),
        "hazard_note": None,
    }
    values.update(changes)
    return ProtocolStep(**values)


class ProtocolDeviationTests(unittest.TestCase):
    def test_common_temperature_notation_is_not_a_deviation(self):
        deviations = detect_protocol_deviations(
            make_step(
                protocol_values={
                    "temperature": "60摄氏度",
                    "duration": "10分钟",
                    "condition": "恒温水浴",
                },
                must_record=("temperature", "duration", "condition"),
            ),
            ExperimentEntities(
                temperature="60℃",
                duration="10分钟",
                condition="室温水浴",
            ),
        )

        self.assertEqual(
            deviations,
            (
                ProtocolDeviation(
                    field_name="condition",
                    protocol_value="恒温水浴",
                    actual_value="室温水浴",
                ),
            ),
        )

    def test_common_action_unit_and_numeric_notation_are_normalized(self):
        deviations = detect_protocol_deviations(
            make_step(
                protocol_values={
                    "action": "称量", "amount_unit": "g", "amount_value": "3.50",
                },
                must_record=("amount_value",),
            ),
            ExperimentEntities(action="称取", amount_unit="克", amount_value="3.5"),
        )

        self.assertEqual(deviations, ())

    def test_step_local_alias_applies_only_when_declared_on_that_step(self):
        actual = ExperimentEntities(object="磷酸盐")
        without_alias = make_step(
            protocol_values={"object": "磷酸二氢盐和磷酸氢二盐"},
            must_record=("observation",),
        )
        with_alias = make_step(
            protocol_values={"object": "磷酸二氢盐和磷酸氢二盐"},
            must_record=("observation",),
            value_aliases={"object": ("磷酸盐",)},
        )

        self.assertEqual(len(detect_protocol_deviations(without_alias, actual)), 1)
        self.assertEqual(detect_protocol_deviations(with_alias, actual), ())

    def test_reports_deviation_for_protocol_only_field(self):
        """方案规定了目标值但该字段不在must_record里时，仍必须报告偏差。

        真实场景：方案写明标准液浓度0.1000 mol/L（属于方案已定，学生不必复述），
        学生却报告用了0.1050 mol/L。这类偏差最需要被发现，
        早期实现只遍历must_record会漏报。
        """

        deviations = detect_protocol_deviations(
            make_step(
                protocol_values={
                    "temperature": "60摄氏度",
                    "duration": "10分钟",
                    "concentration": "0.1000 mol/L",
                },
                must_record=("observation",),
            ),
            ExperimentEntities(concentration="0.1050 mol/L"),
        )

        self.assertEqual(
            deviations,
            (
                ProtocolDeviation(
                    field_name="concentration",
                    protocol_value="0.1000 mol/L",
                    actual_value="0.1050 mol/L",
                ),
            ),
        )

    def test_does_not_report_missing_actual_value_as_deviation(self):
        deviations = detect_protocol_deviations(
            make_step(),
            ExperimentEntities(temperature="60摄氏度"),
        )

        self.assertEqual(deviations, ())

    def test_does_not_report_fields_without_protocol_value(self):
        deviations = detect_protocol_deviations(
            make_step(
                protocol_values={"temperature": "60摄氏度"},
                must_record=("temperature", "observation"),
            ),
            ExperimentEntities(
                temperature="60摄氏度",
                observation="溶液变浑浊",
            ),
        )

        self.assertEqual(deviations, ())


if __name__ == "__main__":
    unittest.main()
