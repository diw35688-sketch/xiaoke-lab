import unittest

from src.core.pending_clarification import ClarificationStatus
from src.core.reply_coordinator import ReplyCoordinator
from src.core.session_context import SessionContext


class ExperimentStateSnapshotTests(unittest.TestCase):
    def test_reply_coordinator_round_trip_keeps_revision_and_current(self):
        coordinator = ReplyCoordinator()
        created = coordinator.register_clarification(
            segment_id=1, raw_text="加热。", question="温度是多少？",
            missing_fields=("temperature",),
        )
        coordinator.pop_next_reply()
        restored = ReplyCoordinator.from_snapshot(coordinator.to_snapshot())
        active = restored.active_clarifications()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].clarification_id, created.clarification_id)
        self.assertFalse(active[0].reply_pending)
        self.assertEqual(restored.current_clarification(), active[0])

    def test_session_context_round_trip(self):
        context = SessionContext(max_events=3)
        context._items.extend(["[operation] 加热", "[measurement] 80度"])
        restored = SessionContext.from_snapshot(context.to_snapshot())
        self.assertEqual(restored.as_prompt_context(), context.as_prompt_context())
        self.assertEqual(restored.max_events, 3)


if __name__ == "__main__":
    unittest.main()
