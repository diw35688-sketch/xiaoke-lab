import sys
import unittest
from pathlib import Path


WEB = Path(__file__).resolve().parent.parent / "web"
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

import domain  # noqa: E402


class ProtocolDisplayProjectionTests(unittest.TestCase):
    def test_historical_strict_comparison_is_reprojected_without_mutating_source(self):
        record = {
            "entities": {
                "action": "称取",
                "object": "磷酸盐",
                "amount_value": "3.5",
                "amount_unit": "克",
            },
            "evaluation": {"deviations": [
                {"field": name, "protocol_value": "old", "actual_value": "old"}
                for name in ("action", "object", "amount_value", "amount_unit")
            ]},
            "step": {
                "protocol": {
                    "id": "phosphate-buffer-0.1m-ph7.4",
                    "version": "1.2",
                },
                "step": {"number": 1},
            },
        }

        projected = domain.project_record_evaluation(record)

        self.assertEqual(projected["evaluation"]["deviations"], [{
            "field": "amount_value",
            "protocol_value": "3.58",
            "actual_value": "3.5",
        }])
        self.assertEqual(projected["evaluation"]["deviation_rule_version"], 2)
        self.assertEqual(len(projected["evaluation"]["stored_deviations"]), 4)
        self.assertEqual(len(record["evaluation"]["deviations"]), 4)

    def test_version_mismatch_keeps_historical_evaluation(self):
        record = {
            "entities": {"amount_value": "3.5"},
            "evaluation": {"deviations": [{"field": "amount_value"}]},
            "step": {
                "protocol": {
                    "id": "phosphate-buffer-0.1m-ph7.4",
                    "version": "older-version",
                },
                "step": {"number": 1},
            },
        }

        self.assertIs(domain.project_record_evaluation(record), record)


if __name__ == "__main__":
    unittest.main()
