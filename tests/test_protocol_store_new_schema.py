import json
import tempfile
import unittest
from pathlib import Path

from src.storage.protocol_store import ProtocolStore


class ProtocolStoreNewSchemaTests(unittest.TestCase):
    def test_loads_protocol_values_and_must_record(self):
        data = {
            "protocols": [
                {
                    "protocol_id": "new-schema",
                    "title": "新语义",
                    "source": "测试",
                    "version": "1.0",
                    "schema_version": 1,
                    "steps": [
                        {
                            "step_number": 1,
                            "title": "称量",
                            "instruction": "称取目标质量并记录实测质量。",
                            "protocol_values": {"amount_value": "3.58"},
                            "must_record": ["amount_value"],
                            "field_prompts": {"amount_value": "实际称量多少？"},
                            "terms": [],
                            "hazard_note": None,
                        }
                    ],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "protocols.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

            step = ProtocolStore(path).list_all()[0].steps[0]

        self.assertEqual(step.protocol_values["amount_value"], "3.58")
        self.assertEqual(step.must_record, ("amount_value",))
        self.assertEqual(step.field_prompts["amount_value"], "实际称量多少？")

    def test_seed_steps_have_explicit_new_fields(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "data"
            / "protocols"
            / "undergraduate_basic_protocols.json"
        )

        protocols = ProtocolStore(path).list_all()

        self.assertGreaterEqual(len(protocols), 3)
        self.assertTrue(all(hasattr(step, "protocol_values") for protocol in protocols for step in protocol.steps))
        self.assertTrue(all(hasattr(step, "must_record") for protocol in protocols for step in protocol.steps))
        self.assertTrue(all(set(step.must_record) <= set(step.field_prompts) for protocol in protocols for step in protocol.steps))


if __name__ == "__main__":
    unittest.main()
