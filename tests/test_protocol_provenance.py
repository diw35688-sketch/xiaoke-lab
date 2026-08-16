import unittest
from dataclasses import FrozenInstanceError

from src.core.protocol import (
    FieldValueSource,
    ProtocolStep,
    SourcedFieldValue,
    materialize_field_values,
)
from src.llm.schemas import ExperimentEntities


def make_step(**changes):
    values = {
        "step_number": 1,
        "title": "称量试剂",
        "instruction": "称取方案规定质量的试剂。",
        "protocol_values": {
            "action": "称量",
            "amount_value": "3.58",
            "amount_unit": "g",
        },
        "must_record": ("amount_value",),
        "terms": (),
        "hazard_note": None,
    }
    values.update(changes)
    return ProtocolStep(**values)


class SourcedFieldValueTests(unittest.TestCase):
    def test_value_is_immutable_and_keeps_source(self):
        value = SourcedFieldValue(
            field_name="amount_value",
            value="3.58",
            source=FieldValueSource.PROTOCOL_DEFAULT,
        )

        self.assertEqual(value.source, FieldValueSource.PROTOCOL_DEFAULT)
        with self.assertRaises(FrozenInstanceError):
            value.value = "3.61"

    def test_rejects_unknown_field(self):
        with self.assertRaisesRegex(ValueError, "未知实体字段"):
            SourcedFieldValue(
                field_name="ph_value",
                value="7.4",
                source=FieldValueSource.SPOKEN,
            )

    def test_spoken_value_wins_over_protocol_default(self):
        values = materialize_field_values(
            make_step(),
            ExperimentEntities(amount_value="3.61"),
        )

        self.assertEqual(values["action"].value, "称量")
        self.assertEqual(
            values["action"].source,
            FieldValueSource.PROTOCOL_DEFAULT,
        )
        self.assertEqual(values["amount_value"].value, "3.61")
        self.assertEqual(
            values["amount_value"].source,
            FieldValueSource.DEVIATION,
        )

    def test_matching_spoken_value_is_not_protocol_default(self):
        values = materialize_field_values(
            make_step(),
            ExperimentEntities(amount_value="3.58"),
        )

        self.assertEqual(
            values["amount_value"].source,
            FieldValueSource.SPOKEN,
        )


if __name__ == "__main__":
    unittest.main()
