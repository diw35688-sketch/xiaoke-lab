import unittest

from src.core.protocol import ProtocolError, ProtocolStep
from src.core.protocol_missing_fields import compute_missing_fields
from src.llm.schemas import ExperimentEntities


def make_step(**changes) -> ProtocolStep:
    values = {
        "step_number": 1,
        "title": "加热溶液",
        "instruction": "将溶液加热到目标温度并保持规定时间。",
        "protocol_values": {},
        "must_record": ("temperature", "duration"),
        "terms": (),
        "hazard_note": None,
    }
    values.update(changes)
    return ProtocolStep(**values)


class ProtocolMissingFieldsTests(unittest.TestCase):
    def test_protocol_values_are_not_missing_even_when_unprovided(self):
        step = make_step(
            protocol_values={
                "temperature": "60摄氏度",
                "duration": "10分钟",
            },
            must_record=("observation",),
        )

        missing = compute_missing_fields(step, ExperimentEntities())

        # 方案目标值已写死，不应因学生未重复口述而触发追问。
        self.assertEqual(missing, ("observation",))

    def test_all_must_record_fields_provided_returns_empty(self):
        step = make_step()
        missing = compute_missing_fields(step, {"temperature", "duration"})
        self.assertEqual(missing, ())

    def test_no_field_names_provided_returns_all_in_must_record_order(self):
        step = make_step()
        missing = compute_missing_fields(step, set())
        self.assertEqual(missing, ("temperature", "duration"))

    def test_partial_field_names_preserve_must_record_order(self):
        step = make_step(must_record=("temperature", "duration", "condition"))
        missing = compute_missing_fields(step, {"duration"})
        self.assertEqual(missing, ("temperature", "condition"))

    def test_non_blank_entity_values_count_as_provided(self):
        step = make_step()
        entities = ExperimentEntities(temperature="60摄氏度", duration="10分钟")
        self.assertEqual(compute_missing_fields(step, entities), ())

    def test_empty_entity_string_counts_as_missing(self):
        step = make_step()
        entities = ExperimentEntities(temperature="", duration="10分钟")
        self.assertEqual(compute_missing_fields(step, entities), ("temperature",))

    def test_whitespace_entity_string_counts_as_missing(self):
        step = make_step()
        entities = ExperimentEntities(temperature="  	", duration="10分钟")
        self.assertEqual(compute_missing_fields(step, entities), ("temperature",))

    def test_none_entity_value_counts_as_missing(self):
        step = make_step()
        entities = ExperimentEntities(temperature=None, duration="10分钟")
        self.assertEqual(compute_missing_fields(step, entities), ("temperature",))

    def test_unrelated_entity_values_do_not_fill_must_record_fields(self):
        step = make_step()
        entities = ExperimentEntities(observation="溶液变蓝")
        self.assertEqual(compute_missing_fields(step, entities), ("temperature", "duration"))

    def test_empty_must_record_always_returns_empty(self):
        step = make_step(must_record=())
        self.assertEqual(compute_missing_fields(step, object()), ())

    def test_accepts_frozen_field_name_set(self):
        step = make_step()
        self.assertEqual(compute_missing_fields(step, frozenset({"temperature"})), ("duration",))

    def test_rejects_unknown_provided_field_name(self):
        with self.assertRaisesRegex(ProtocolError, "未知实体字段"):
            compute_missing_fields(make_step(), {"ph_value"})

    def test_rejects_non_string_provided_field_name(self):
        with self.assertRaisesRegex(ProtocolError, "必须是字符串"):
            compute_missing_fields(make_step(), {1})

    def test_rejects_non_set_field_collection(self):
        with self.assertRaises(ProtocolError):
            compute_missing_fields(make_step(), ["temperature"])

    def test_rejects_non_protocol_step(self):
        with self.assertRaises(ProtocolError):
            compute_missing_fields("步骤一", set())


if __name__ == "__main__":
    unittest.main()
