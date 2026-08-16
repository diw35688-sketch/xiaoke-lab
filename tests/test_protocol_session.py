import unittest
from dataclasses import FrozenInstanceError

from src.core.protocol import ExperimentProtocol, ProtocolStep
from src.core.protocol_selection import ProtocolSelection
from src.core.protocol_session import ProtocolSessionState


def make_protocol(step_count=3):
    return ExperimentProtocol(
        protocol_id="session-demo",
        title="会话方案",
        source="测试",
        version="1.0",
        steps=tuple(
            ProtocolStep(
                step_number=i,
                title=f"步骤{i}",
                instruction="执行步骤。",
                protocol_values={},
                must_record=(),
                terms=(),
                hazard_note=None,
            )
            for i in range(1, step_count + 1)
        ),
        schema_version=1,
    )


class ProtocolSessionStateTests(unittest.TestCase):
    def test_start_selected_protocol_creates_cursor_at_first_step(self):
        protocol = make_protocol()
        state = ProtocolSessionState.start(ProtocolSelection.selected(protocol))

        self.assertEqual(state.step_number, 1)
        self.assertIs(state.current_step(), protocol.steps[0])

    def test_navigation_returns_new_state_without_mutating_previous(self):
        state = ProtocolSessionState.start(ProtocolSelection.selected(make_protocol()))

        next_state = state.next()
        jumped_state = next_state.jump_to(3)
        previous_state = jumped_state.prev()

        self.assertEqual(state.step_number, 1)
        self.assertEqual(next_state.step_number, 2)
        self.assertEqual(jumped_state.step_number, 3)
        self.assertEqual(previous_state.step_number, 2)
        self.assertIsNot(state, next_state)

    def test_navigation_boundaries_use_cursor_errors(self):
        state = ProtocolSessionState.start(ProtocolSelection.selected(make_protocol()))

        with self.assertRaisesRegex(ValueError, "第一步"):
            state.prev()
        with self.assertRaisesRegex(ValueError, "最后一步"):
            state.jump_to(3).next()
        with self.assertRaisesRegex(ValueError, "超出范围"):
            state.jump_to(0)

    def test_free_mode_is_first_class_for_all_methods(self):
        state = ProtocolSessionState.start(ProtocolSelection.free_mode())

        self.assertIsNone(state.cursor)
        self.assertIsNone(state.current_step())
        self.assertIsNone(state.step_number)
        self.assertIsNot(state, state.next())
        self.assertIsNone(state.next().current_step())
        self.assertIsNone(state.prev().current_step())
        self.assertIsNone(state.jump_to(999).current_step())

    def test_state_is_frozen(self):
        state = ProtocolSessionState.start(ProtocolSelection.free_mode())

        with self.assertRaises(FrozenInstanceError):
            state.cursor = None


if __name__ == "__main__":
    unittest.main()
