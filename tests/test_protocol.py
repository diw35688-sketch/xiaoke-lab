import unittest
from dataclasses import FrozenInstanceError, fields
from types import MappingProxyType

from src.core.protocol import (
    EXPERIMENT_ENTITY_FIELD_NAMES,
    ExperimentProtocol,
    ProtocolError,
    ProtocolStep,
)
from src.llm.schemas import ExperimentEntities


def make_step(**changes) -> ProtocolStep:
    values = {
        "step_number": 1,
        "title": "加热溶液",
        "instruction": "将溶液加热到目标温度并保持规定时间。",
        "protocol_values": {"temperature": "60摄氏度"},
        "must_record": ("temperature", "duration"),
        "terms": ("恒温水浴", "加热"),
        "hazard_note": "佩戴隔热手套。",
    }
    values.update(changes)
    return ProtocolStep(**values)


def make_protocol(**changes) -> ExperimentProtocol:
    values = {
        "protocol_id": "heating-demo",
        "title": "加热示例",
        "source": "本科实验教学示例",
        "version": "1.0",
        "steps": (make_step(),),
        "schema_version": 1,
    }
    values.update(changes)
    return ExperimentProtocol(**values)


class ProtocolStepTests(unittest.TestCase):
    def test_accepts_valid_step(self):
        step = make_step(field_prompts={"temperature": "实际温度是多少？"})

        self.assertEqual(step.must_record, ("temperature", "duration"))
        self.assertEqual(step.field_prompts["temperature"], "实际温度是多少？")
        self.assertIsInstance(step.field_prompts, MappingProxyType)

    def test_field_prompts_are_optional_and_read_only(self):
        step = make_step()

        self.assertEqual(step.field_prompts, {})
        with self.assertRaises(TypeError):
            step.field_prompts["duration"] = "保持多久？"

    def test_rejects_field_prompt_for_unknown_entity_field(self):
        with self.assertRaisesRegex(ProtocolError, "未知实体字段"):
            make_step(field_prompts={"ph_value": "pH是多少？"})

    def test_rejects_field_prompt_not_in_must_record(self):
        with self.assertRaisesRegex(ProtocolError, "must_record"):
            make_step(field_prompts={"object": "用了什么对象？"})

    def test_rejects_blank_field_prompt_key(self):
        with self.assertRaises(ProtocolError):
            make_step(field_prompts={" ": "请补充。"})

    def test_rejects_blank_field_prompt_value(self):
        with self.assertRaises(ProtocolError):
            make_step(field_prompts={"temperature": "  "})

    def test_rejects_non_mapping_field_prompts(self):
        with self.assertRaises(ProtocolError):
            make_step(field_prompts=("temperature", "实际温度是多少？"))

    def test_entity_field_whitelist_comes_from_dataclass_fields(self):
        expected = frozenset(
            field_info.name
            for field_info in fields(ExperimentEntities)
        )

        self.assertEqual(EXPERIMENT_ENTITY_FIELD_NAMES, expected)

    def test_accepts_every_current_experiment_entity_field(self):
        step = make_step(
            protocol_values={},
            must_record=tuple(EXPERIMENT_ENTITY_FIELD_NAMES),
        )

        self.assertEqual(
            set(step.must_record),
            EXPERIMENT_ENTITY_FIELD_NAMES,
        )

    def test_rejects_step_number_zero_with_protocol_error(self):
        with self.assertRaises(ProtocolError):
            make_step(step_number=0)

    def test_rejects_boolean_step_number_with_protocol_error(self):
        with self.assertRaises(ProtocolError):
            make_step(step_number=True)

    def test_rejects_unknown_must_record_field(self):
        with self.assertRaisesRegex(ProtocolError, "未知实体字段"):
            make_step(must_record=("temperature", "ph_value"))

    def test_rejects_duplicate_must_record_field(self):
        with self.assertRaisesRegex(ProtocolError, "不能重复"):
            make_step(must_record=("temperature", "temperature"))

    def test_rejects_unknown_protocol_value_key(self):
        with self.assertRaisesRegex(ProtocolError, "未知实体字段"):
            make_step(protocol_values={"ph_value": "7.4"})

    def test_rejects_blank_step_title(self):
        with self.assertRaises(ProtocolError):
            make_step(title="   ")

    def test_rejects_blank_instruction(self):
        with self.assertRaises(ProtocolError):
            make_step(instruction="\t")

    def test_rejects_blank_must_record_field_name(self):
        with self.assertRaises(ProtocolError):
            make_step(must_record=("temperature", " "))

    def test_rejects_blank_protocol_value(self):
        with self.assertRaises(ProtocolError):
            make_step(protocol_values={"temperature": " "})

    def test_rejects_blank_term(self):
        with self.assertRaises(ProtocolError):
            make_step(terms=("恒温水浴", ""))

    def test_rejects_blank_hazard_note(self):
        with self.assertRaises(ProtocolError):
            make_step(hazard_note=" ")

    def test_must_record_must_be_tuple(self):
        with self.assertRaises(ProtocolError):
            make_step(must_record=["temperature"])

    def test_protocol_values_must_be_mapping(self):
        with self.assertRaises(ProtocolError):
            make_step(protocol_values=("temperature", "60摄氏度"))

    def test_protocol_values_are_read_only_after_construction(self):
        step = make_step()

        with self.assertRaises(TypeError):
            step.protocol_values["duration"] = "10分钟"

    def test_frozen_step_rejects_attribute_assignment(self):
        step = make_step()

        with self.assertRaises(FrozenInstanceError):
            step.title = "修改标题"


class ExperimentProtocolTests(unittest.TestCase):
    def test_accepts_continuous_steps(self):
        protocol = make_protocol(
            steps=(
                make_step(step_number=1),
                make_step(step_number=2),
            )
        )

        self.assertEqual(
            tuple(step.step_number for step in protocol.steps),
            (1, 2),
        )

    def test_rejects_duplicate_step_number(self):
        with self.assertRaisesRegex(ProtocolError, "严格连续"):
            make_protocol(
                steps=(
                    make_step(step_number=1),
                    make_step(step_number=1),
                )
            )

    def test_rejects_skipped_step_number(self):
        with self.assertRaisesRegex(ProtocolError, "严格连续"):
            make_protocol(
                steps=(
                    make_step(step_number=1),
                    make_step(step_number=3),
                )
            )

    def test_rejects_steps_starting_after_one(self):
        with self.assertRaisesRegex(ProtocolError, "严格连续"):
            make_protocol(steps=(make_step(step_number=2),))

    def test_rejects_empty_steps(self):
        with self.assertRaisesRegex(ProtocolError, "不能为空"):
            make_protocol(steps=())

    def test_rejects_blank_protocol_id(self):
        with self.assertRaises(ProtocolError):
            make_protocol(protocol_id=" ")

    def test_rejects_blank_protocol_title(self):
        with self.assertRaises(ProtocolError):
            make_protocol(title=" ")

    def test_rejects_blank_source(self):
        with self.assertRaises(ProtocolError):
            make_protocol(source="\n")

    def test_rejects_blank_version(self):
        with self.assertRaises(ProtocolError):
            make_protocol(version="")

    def test_rejects_non_protocol_step(self):
        with self.assertRaises(ProtocolError):
            make_protocol(steps=("步骤一",))

    def test_rejects_non_positive_schema_version(self):
        with self.assertRaises(ProtocolError):
            make_protocol(schema_version=0)

    def test_frozen_protocol_rejects_attribute_assignment(self):
        protocol = make_protocol()

        with self.assertRaises(FrozenInstanceError):
            protocol.title = "修改方案"


if __name__ == "__main__":
    unittest.main()
