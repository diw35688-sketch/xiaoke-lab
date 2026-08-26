# -*- coding: utf-8 -*-
"""database/session_store.py 的持久化测试。

用仓库内临时目录放测试数据库（沙箱禁止系统临时目录），测试完清理；
不碰真实的 web/lab_agent.db。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "web"))

from database import session_store  # noqa: E402

# 沙箱限制：只允许在仓库根目录直接建文件，不允许在运行时新建子目录里建库，
# 因此测试库用根目录固定文件名，测试前后清理，不碰真实 web/lab_agent.db。
DB_FILE = REPO_ROOT / "_sstest_session_store.db"


class SessionStoreTests(unittest.TestCase):
    def setUp(self):
        self._old_path = session_store.DB_PATH
        if DB_FILE.exists():
            DB_FILE.unlink()
        session_store.DB_PATH = DB_FILE

    def tearDown(self):
        session_store.DB_PATH = self._old_path
        if DB_FILE.exists():
            DB_FILE.unlink()

    def test_snapshot_roundtrip_protocol(self):
        session_store.save_session_snapshot("phosphate-buffer-0.1m-ph7.4", 3)
        snap = session_store.load_session_snapshot()
        self.assertEqual(snap["protocol_id"], "phosphate-buffer-0.1m-ph7.4")
        self.assertEqual(snap["step_number"], 3)

    def test_snapshot_roundtrip_free_mode(self):
        session_store.save_session_snapshot(None, None)
        snap = session_store.load_session_snapshot()
        self.assertIsNotNone(snap)
        self.assertIsNone(snap["protocol_id"])
        self.assertIsNone(snap["step_number"])

    def test_snapshot_overwrite_keeps_single_row(self):
        session_store.save_session_snapshot("a", 1)
        session_store.save_session_snapshot("b", 2)
        snap = session_store.load_session_snapshot()
        self.assertEqual(snap["protocol_id"], "b")
        self.assertEqual(snap["step_number"], 2)

    def test_progress_save_and_load(self):
        session_store.save_step_progress(2, ["amount_value", "temperature"], False)
        session_store.save_step_progress(2, ["amount_value"], True)   # 重复字段去重
        session_store.save_step_progress(3, ["observation"], False)
        progress = session_store.load_step_progress()
        self.assertEqual(sorted(progress[2]["recorded"]), ["amount_value", "temperature"])
        self.assertTrue(progress[2]["deviation"])
        self.assertEqual(progress[3]["recorded"], ["observation"])
        self.assertFalse(progress[3]["deviation"])

    def test_progress_ignores_none_step(self):
        session_store.save_step_progress(None, ["a"], False)   # 不抛异常、不落行
        self.assertEqual(session_store.load_step_progress(), {})

    def test_confirmation_save_and_load(self):
        session_store.save_step_confirmation(2)
        session_store.save_step_confirmation(2)   # 幂等
        session_store.save_step_confirmation(4)
        self.assertEqual(sorted(session_store.load_step_confirmations()), [2, 4])

    def test_clear_removes_confirmations(self):
        session_store.save_step_confirmation(1)
        session_store.clear_progress_rows()
        self.assertEqual(session_store.load_step_confirmations(), [])

    def test_clear_progress_rows(self):
        session_store.save_step_progress(1, ["a"], True)
        session_store.clear_progress_rows()
        self.assertEqual(session_store.load_step_progress(), {})


if __name__ == "__main__":
    unittest.main()
