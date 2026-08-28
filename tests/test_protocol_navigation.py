import unittest

from src.core.pending_clarification import ClarificationStatus, PendingClarification
from src.core.protocol_execution_state import ProtocolExecutionState
from src.core.protocol_navigation import decide_protocol_move


def question(status, fields=("condition",)):
    return PendingClarification(
        clarification_id="q1",
        display_number=1,
        source_segment_id=1,
        source_raw_text="保存样品",
        question="请补充保存条件。",
        missing_fields=fields,
        status=status,
        reply_pending=status == ClarificationStatus.ACTIVE,
        protocol_id="p1",
        protocol_version="1",
        protocol_step_number=1,
    )


class ProtocolNavigationTests(unittest.TestCase):
    def setUp(self):
        self.state = ProtocolExecutionState.start(
            protocol_id="p1", protocol_version="1"
        )

    def test_active_question_blocks_next(self):
        decision = decide_protocol_move(
            state=self.state,
            action="next",
            total_steps=3,
            evaluation={"missing_fields": ["condition"]},
            unresolved=(question(ClarificationStatus.ACTIVE),),
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.blocking_question_numbers, (1,))

    def test_deferred_question_allows_next_with_pending_status(self):
        decision = decide_protocol_move(
            state=self.state,
            action="next",
            total_steps=3,
            evaluation={"missing_fields": ["condition"]},
            unresolved=(question(ClarificationStatus.DEFERRED),),
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.state.current_step_number, 2)
        self.assertEqual(decision.state.statuses[1].value, "left_with_pending")

    def test_uncovered_missing_field_blocks_next(self):
        decision = decide_protocol_move(
            state=self.state,
            action="next",
            total_steps=3,
            evaluation={"missing_fields": ["condition", "duration"]},
            unresolved=(question(ClarificationStatus.DEFERRED),),
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.missing_fields, ("duration",))

    def test_complete_step_moves_and_marks_completed(self):
        decision = decide_protocol_move(
            state=self.state,
            action="next",
            total_steps=3,
            evaluation={"missing_fields": []},
            unresolved=(),
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.state.statuses[1].value, "completed")

    def test_backward_jump_is_allowed_but_forward_skip_is_rejected(self):
        on_two = self.state.move_to(
            2, leaving_status=self.state.statuses[1]
        )
        back = decide_protocol_move(
            state=on_two, action="jump", target_step_number=1,
            total_steps=3, evaluation={"missing_fields": []}, unresolved=(),
        )
        forward = decide_protocol_move(
            state=self.state, action="jump", target_step_number=3,
            total_steps=3, evaluation={"missing_fields": []}, unresolved=(),
        )
        self.assertTrue(back.allowed)
        self.assertFalse(forward.allowed)


if __name__ == "__main__":
    unittest.main()
