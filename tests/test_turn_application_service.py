import sys
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

from database import db  # noqa: E402
from database.turn_store import TurnRequestConflictError, TurnStore  # noqa: E402
from src.core.conversation_turn import (  # noqa: E402
    BlockType, ConversationBlock, ConversationTurn,
    ExperimentContext, InputSource, InteractionMode,
)
from src.core.turn_input import TurnInput  # noqa: E402
from turn_application_service import TurnApplicationService  # noqa: E402
from turn_processors import PreparedTurn  # noqa: E402


def _turn(request_id="r1", text="你好"):
    return TurnInput(
        "c1", request_id, f"t-{request_id}", None,
        InteractionMode.CHAT, ExperimentContext.NONE, 1,
        InputSource.TEXT, text,
    )


class _Processor:
    def __init__(self, gate=None, fail=False):
        self.calls = 0
        self.gate = gate
        self.fail = fail

    def prepare(self, turn, timing):
        self.calls += 1
        if self.gate is not None:
            self.gate.wait(2)
        if self.fail:
            raise RuntimeError("processor failed")
        user = ConversationBlock(f"{turn.turn_id}:u", BlockType.USER_TEXT, {"text": turn.raw_text})
        assistant = ConversationBlock(f"{turn.turn_id}:a", BlockType.ASSISTANT_TEXT, {"text": "好"})
        return PreparedTurn(
            ConversationTurn(
                turn.conversation_id, turn.request_id, turn.turn_id,
                turn.interaction_mode, turn.experiment_context,
                turn.mode_version, turn.input_source, (user, assistant),
            ),
            {"kind": "chat"},
            messages=(
                {"role": "user", "content": turn.raw_text, "block_id": user.block_id},
                {"role": "assistant", "content": "好", "block_id": assistant.block_id},
            ),
        )


class TurnApplicationServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = db.DATABASE_PATH
        db.DATABASE_PATH = Path(self.temp.name) / "turn.db"
        db.initialize_database()
        self.store = TurnStore(connection_factory=db.get_connection)

    def tearDown(self):
        if hasattr(self, "service"):
            self.service.close()
        db.DATABASE_PATH = self.old
        self.temp.cleanup()

    def test_same_inflight_request_attaches_to_one_future(self):
        gate = threading.Event()
        processor = _Processor(gate)
        self.service = TurnApplicationService(
            store=self.store,
            experiment_processor=processor,
            template_processor=processor, storage_processor=processor,
        )
        first = self.service.submit(_turn())
        second = self.service.submit(_turn())
        self.assertIs(first.future, second.future)
        self.assertTrue(second.replayed)
        gate.set()
        result = first.future.result(2)
        self.assertFalse(result.replayed)
        self.assertEqual(processor.calls, 1)

    def test_committed_replay_does_not_process_or_return_voice(self):
        processor = _Processor()
        self.service = TurnApplicationService(
            store=self.store,
            experiment_processor=processor,
            template_processor=processor, storage_processor=processor,
        )
        self.service.submit(_turn()).future.result(2)
        replay = self.service.submit(_turn()).future.result(2)
        self.assertTrue(replay.replayed)
        self.assertEqual(replay.voice_items, ())
        self.assertEqual(processor.calls, 1)

    def test_conflict_and_failure_are_durable_and_retryable(self):
        failing = _Processor(fail=True)
        self.service = TurnApplicationService(
            store=self.store,
            experiment_processor=failing,
            template_processor=failing, storage_processor=failing,
        )
        with self.assertRaises(RuntimeError):
            self.service.submit(_turn()).future.result(2)
        self.assertEqual(self.store.diagnostics("r1")["status"], "failed")
        with self.assertRaises(TurnRequestConflictError):
            self.service.submit(_turn(text="不同"))

    def test_post_commit_timing_failure_does_not_reverse_business_success(self):
        processor = _Processor()
        self.service = TurnApplicationService(
            store=self.store,
            experiment_processor=processor,
            template_processor=processor, storage_processor=processor,
        )
        original = self.store.update_committed_result
        self.store.update_committed_result = lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("diagnostic update failed")
        )
        try:
            with self.assertLogs("turn_application_service", level="ERROR"):
                result = self.service.submit(_turn()).future.result(2)
        finally:
            self.store.update_committed_result = original
        self.assertFalse(result.replayed)
        self.assertEqual(self.store.diagnostics("r1")["status"], "committed")
        with closing(db.get_connection()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
