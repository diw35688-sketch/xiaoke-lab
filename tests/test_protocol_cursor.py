import unittest

from src.core.protocol import ExperimentProtocol, ProtocolStep
from src.core.protocol_cursor import ProtocolStepCursor, ProtocolStepCursorError


def make_protocol(step_count=3):
    return ExperimentProtocol(
        protocol_id="cursor-demo",
        title="游标示例",
        source="测试",
        version="1.0",
        steps=tuple(
            ProtocolStep(
                step_number=number,
                title=f"步骤{number}",
                instruction="执行步骤。",
                protocol_values={},
                must_record=(),
                terms=(),
                hazard_note=None,
            )
            for number in range(1, step_count + 1)
        ),
        schema_version=1,
    )


class ProtocolStepCursorTests(unittest.TestCase):
    def test_explicit_navigation_returns_new_cursor(self):
        cursor = ProtocolStepCursor.start(make_protocol())

        next_cursor = cursor.next()
        jumped_cursor = next_cursor.jump_to(3)
        previous_cursor = jumped_cursor.prev()

        self.assertEqual(cursor.current_step_number, 1)
        self.assertEqual(next_cursor.current_step_number, 2)
        self.assertEqual(jumped_cursor.current_step_number, 3)
        self.assertEqual(previous_cursor.current_step_number, 2)
        self.assertIsNot(cursor, next_cursor)

    def test_next_at_last_step_is_explicit_error(self):
        cursor = ProtocolStepCursor.start(make_protocol()).jump_to(3)

        with self.assertRaisesRegex(ProtocolStepCursorError, "最后一步"):
            cursor.next()

    def test_prev_at_first_step_is_explicit_error(self):
        cursor = ProtocolStepCursor.start(make_protocol())

        with self.assertRaisesRegex(ProtocolStepCursorError, "第一步"):
            cursor.prev()

    def test_jump_to_rejects_out_of_range_step(self):
        cursor = ProtocolStepCursor.start(make_protocol())

        with self.assertRaisesRegex(ProtocolStepCursorError, "超出范围"):
            cursor.jump_to(0)
        with self.assertRaisesRegex(ProtocolStepCursorError, "超出范围"):
            cursor.jump_to(4)


if __name__ == "__main__":
    unittest.main()
