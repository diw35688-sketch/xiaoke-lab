"""Web 领域层的跨段累计与新会话边界回归测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "web"))

import domain  # noqa: E402
from database import session_store  # noqa: E402

DB_FILE = REPO_ROOT / "_sstest_web_domain_consistency.db"


class WebDomainConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.old_db_path = session_store.DB_PATH
        session_store.DB_PATH = DB_FILE
        if DB_FILE.exists():
            DB_FILE.unlink()
        domain._session = None
        domain._progress.reset()

    def tearDown(self):
        domain._session = None
        domain._progress.reset()
        session_store.DB_PATH = self.old_db_path
        if DB_FILE.exists():
            DB_FILE.unlink()

    def test_follow_up_uses_fields_accumulated_across_segments(self):
        state = domain.start_session("acid-base-titration-naoh-hcl").jump_to(4)
        domain._session = state

        first = domain.evaluate_and_record({"amount_value": "24.7"})
        self.assertEqual(first["missing_fields"], ["observation"])

        second = domain.evaluate_and_record({"observation": "溶液变为浅粉色"})
        self.assertEqual(second["missing_fields"], [])
        self.assertFalse(second["follow_up_required"])
        self.assertIsNone(second["follow_up_question"])

    def test_reset_session_clears_protocol_progress_and_deviation(self):
        domain.start_session("acid-base-titration-naoh-hcl")
        domain.evaluate_and_record({"observation": "已润洗"})
        self.assertTrue(domain.session().selection.has_protocol)
        self.assertTrue(domain._progress.recorded_fields(1))

        reset = domain.reset_session()

        self.assertTrue(reset.selection.is_free_mode)
        self.assertEqual(domain._progress.recorded_fields(1), [])
        self.assertIsNone(session_store.load_session_snapshot()["protocol_id"])
        self.assertEqual(session_store.load_step_progress(), {})


if __name__ == "__main__":
    unittest.main()
