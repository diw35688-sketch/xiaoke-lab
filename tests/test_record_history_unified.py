import sys
import unittest
from pathlib import Path
from unittest import mock

WEB = Path(__file__).resolve().parent.parent / "web"
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

from api import record as record_api  # noqa: E402


class _LedgerStore:
    def load_experiment_ledger(self, conversation_id, lab_session_id):
        return {
            "conversation_id": conversation_id,
            "lab_session_id": lab_session_id,
            "revision": 7,
            "records": [{
                "segment_id": 1,
                "transcript": "溶液透明",
                "entities": {"observation": "溶液透明"},
                "evaluation": {},
                "step": {"step": {"number": 1}},
                "at": "2026-08-27T00:00:00",
            }],
            "reply_coordinator": {
                "clarifications": [{
                    "clarification_id": "q1",
                    "display_number": 1,
                    "source_segment_id": 1,
                    "source_raw_text": "保存样品",
                    "question": "保存条件是什么？",
                    "missing_fields": [],
                    "requires_confirmation": False,
                    "status": "resolved",
                    "revision": 4,
                    "reply_pending": False,
                    "last_updated_segment_id": 3,
                    "protocol_id": "p1",
                    "protocol_version": "1",
                    "protocol_step_number": 1,
                }],
                "next_display_number": 2,
                "current_clarification_id": None,
            },
            "protocol_execution": {
                "protocol_id": "p1",
                "protocol_version": "1",
                "current_step_number": 2,
                "steps": {"1": {}, "2": {}},
                "statuses": {"1": "completed", "2": "in_progress"},
            },
            "clarification_answers": {"q1": [{
                "request_id": "r-answer",
                "raw_text": "室温保存",
                "committed_at": "2026-08-27T00:02:00",
                "written_fields": [{
                    "field": "condition",
                    "value": "室温",
                    "protocol_step_number": 1,
                }],
            }]},
        }


class UnifiedRecordHistoryTests(unittest.TestCase):
    def test_joint_identity_returns_records_questions_and_protocol_progress(self):
        with mock.patch("api.turn.turn_store", _LedgerStore()):
            result = record_api.history("c1", "lab1")

        self.assertEqual(result["source"], "unified_turn")
        self.assertEqual(result["session_id"], "lab1")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["clarifications"][0]["status"], "resolved")
        self.assertEqual(
            result["clarifications"][0]["protocol_step_number"], 1
        )
        self.assertEqual(result["protocol"]["current_step_number"], 2)
        self.assertEqual(
            result["protocol"]["step_statuses"]["1"], "completed"
        )
        self.assertEqual(
            result["clarifications"][0]["answers"][0]["raw_text"], "室温保存"
        )
        self.assertEqual(
            result["clarifications"][0]["answers"][0]["written_fields"][0],
            {"field": "condition", "value": "室温", "protocol_step_number": 1},
        )

    def test_partial_joint_identity_is_rejected(self):
        with self.assertRaises(record_api.HTTPException) as raised:
            record_api.history("c1", None)
        self.assertEqual(raised.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
