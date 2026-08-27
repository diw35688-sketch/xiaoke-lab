import sys
import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

import domain  # noqa: E402
from api import protocols as protocol_api  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from src.core.protocol_execution_state import ProtocolExecutionState  # noqa: E402
from src.core.reply_coordinator import ReplyCoordinator  # noqa: E402


class _StateStore:
    def __init__(self, coordinator):
        protocol = domain.protocols().list_all()[0]
        self.snapshot = ProtocolExecutionState.start(
            protocol_id=protocol.protocol_id,
            protocol_version=protocol.version,
        ).to_snapshot()
        self.coordinator = coordinator
        self.saved = None

    def load_experiment_state(self, conversation_id, lab_session_id):
        return {
            "revision": 4,
            "reply_coordinator": self.coordinator.to_snapshot(),
            "session_context": {},
            "protocol_step_facts": self.snapshot,
            "next_segment_id": 3,
            "experiment_step_count": 1,
        }

    def save_protocol_navigation(self, **values):
        self.saved = values
        return 5


def _coordinator(*, deferred):
    protocol = domain.protocols().list_all()[0]
    coordinator = ReplyCoordinator()
    item = coordinator.register_clarification(
        segment_id=1,
        raw_text="称量磷酸盐",
        question="实际称量值是多少？",
        missing_fields=("amount_value",),
        protocol_id=protocol.protocol_id,
        protocol_version=protocol.version,
        protocol_step_number=1,
    )
    if deferred:
        coordinator.defer_clarification(
            clarification_id=item.clarification_id,
            expected_revision=item.revision,
            segment_id=2,
        )
    return coordinator


class ProtocolNavigationApiTests(unittest.TestCase):
    def setUp(self):
        self.old_store = protocol_api.turn_store
        protocol = domain.protocols().list_all()[0]
        domain.start_session(protocol.protocol_id)

    def tearDown(self):
        protocol_api.turn_store = self.old_store

    def test_active_question_returns_conflict(self):
        protocol_api.turn_store = _StateStore(_coordinator(deferred=False))
        with self.assertRaises(HTTPException) as raised:
            protocol_api.move(protocol_api.MovePayload(
                conversation_id="c1", lab_session_id="lab1", action="next"
            ))
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(
            raised.exception.detail["blocking_question_numbers"], [1]
        )

    def test_deferred_question_moves_and_persists_left_with_pending(self):
        store = _StateStore(_coordinator(deferred=True))
        protocol_api.turn_store = store
        result = protocol_api.move(protocol_api.MovePayload(
            conversation_id="c1", lab_session_id="lab1", action="next"
        ))
        self.assertEqual(result["step"]["number"], 2)
        self.assertEqual(result["move"]["deferred_question_numbers"], [1])
        saved = store.saved["protocol_step_facts"]
        self.assertEqual(saved["statuses"]["1"], "left_with_pending")
        self.assertEqual(saved["current_step_number"], 2)


if __name__ == "__main__":
    unittest.main()
