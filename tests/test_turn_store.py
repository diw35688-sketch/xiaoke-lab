import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

from database import db  # noqa: E402
from database.turn_store import (  # noqa: E402
    TurnRequestConflictError,
    TurnStore,
    canonical_request_hash,
)
from src.core.conversation_turn import (  # noqa: E402
    ExperimentContext, InputSource, InteractionMode,
)
from src.core.turn_input import TurnInput  # noqa: E402


def _turn(text="温度八十摄氏度"):
    return TurnInput(
        "c1", "r1", "t1", "lab1",
        InteractionMode.EXPERIMENT, ExperimentContext.FREE, 1,
        InputSource.TEXT, text,
    )


class TurnStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = db.DATABASE_PATH
        db.DATABASE_PATH = Path(self.temp.name) / "turns.db"
        db.initialize_database()
        with closing(db.get_connection()) as connection, connection:
            connection.execute("INSERT INTO conversations(id) VALUES ('c1')")
        self.store = TurnStore(connection_factory=db.get_connection)

    def tearDown(self):
        db.DATABASE_PATH = self.old_path
        self.temp.cleanup()

    def test_schema_is_additive_and_foreign_keys_are_on(self):
        db.initialize_database()
        with closing(db.get_connection()) as connection:
            self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            names = {r[0] for r in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
        self.assertTrue({"turn_requests", "asr_evidence", "experiment_events"} <= names)

    def test_reserve_replay_conflict_and_failed_retry(self):
        turn = _turn()
        digest = canonical_request_hash(turn.to_wire())
        self.assertEqual(self.store.reserve(turn, digest).disposition, "new")
        self.assertEqual(self.store.reserve(turn, digest).disposition, "processing")
        with self.assertRaises(TurnRequestConflictError):
            self.store.reserve(_turn("不同内容"), canonical_request_hash(_turn("不同内容").to_wire()))
        self.store.fail("r1", code="TEST", detail="failed", timings={})
        retry = self.store.reserve(turn, digest)
        self.assertEqual((retry.disposition, retry.attempt), ("retry", 2))

    def test_one_transaction_commits_all_business_rows(self):
        turn = _turn()
        digest = canonical_request_hash(turn.to_wire())
        self.store.reserve(turn, digest)
        result = {"turn": {"turn_id": "t1"}, "business": {"segment_id": 1}}
        self.store.commit(
            turn=turn, result=result, timings={"saving": {"elapsed_ms": 5}},
            lab_record={
                "session_id": "lab1", "segment_id": 1,
                "transcript": turn.raw_text, "entities": {"temperature": "80"},
                "extraction_source": "test", "evaluation": {}, "step": None,
                "at": "2026-08-26T00:00:00",
            },
            experiment_events=({"kind": "measurement"},),
            session_state={
                "revision": 1, "reply_coordinator": {}, "session_context": [],
            },
        )
        replay = self.store.reserve(turn, digest)
        self.assertEqual(replay.disposition, "committed")
        self.assertEqual(replay.result, result)
        state = self.store.load_experiment_state("c1", "lab1")
        self.assertEqual(state["next_segment_id"], 2)
        self.assertEqual(state["experiment_step_count"], 1)
        with closing(db.get_connection()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM lab_records").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM experiment_events").fetchone()[0], 1)

    def test_failed_commit_rolls_back_every_business_row(self):
        turn = _turn()
        self.store.reserve(turn, canonical_request_hash(turn.to_wire()))
        with self.assertRaises((KeyError, sqlite3.Error)):
            self.store.commit(
                turn=turn, result={}, timings={},
                experiment_events=({"kind": "measurement"},),
                lab_record={"session_id": "lab1"},
            )
        with closing(db.get_connection()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM experiment_events").fetchone()[0], 0)
            status = connection.execute(
                "SELECT status FROM turn_requests WHERE request_id='r1'"
            ).fetchone()[0]
        self.assertEqual(status, "processing")

    def test_recover_processing_makes_request_retryable(self):
        turn = _turn()
        digest = canonical_request_hash(turn.to_wire())
        self.store.reserve(turn, digest)
        self.assertEqual(self.store.recover_processing(), 1)
        self.assertEqual(self.store.reserve(turn, digest).disposition, "retry")

    def test_session_delete_cascades_turn_evidence_and_returns_audio(self):
        turn = _turn()
        self.store.reserve(turn, canonical_request_hash(turn.to_wire()))
        self.store.commit(
            turn=turn, result={"ok": True}, timings={},
            asr_evidence={
                "payload": {"schema_version": 2},
                "audio_rel_path": "conversations/c1/r1.wav",
                "audio_sha256": "abc", "audio_bytes": 3,
            },
            lab_record={
                "session_id": "lab1", "segment_id": 1,
                "transcript": turn.raw_text, "at": "2026-08-26T00:00:00",
            },
            session_state={
                "revision": 1, "reply_coordinator": {}, "session_context": {},
            },
        )
        paths = self.store.delete_experiment_session("c1", "lab1")
        self.assertEqual(paths, ("conversations/c1/r1.wav",))
        with closing(db.get_connection()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM turn_requests").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM asr_evidence").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM lab_records").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
