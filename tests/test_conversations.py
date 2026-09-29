# -*- coding: utf-8 -*-
"""会话列表、新建、标题、切换历史所依赖的 SQLite 合同测试。"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

WEB_DIR = Path(__file__).resolve().parents[1] / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from database import crud  # noqa: E402
from database.db import initialize_database  # noqa: E402
from database.user_store import create_user  # noqa: E402
from database.lab_record_store import save_record  # noqa: E402


class ConversationCrudTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        self.patch = patch("database.db.DATABASE_PATH", self.db_path)
        self.patch.start()
        initialize_database()
        self.user_id = create_user("tester", "pw123456", "测试员")["id"]

    def tearDown(self):
        self.patch.stop()
        # Force garbage collection so SQLite connections are released before
        # tempfile cleanup — Windows holds exclusive locks otherwise.
        import gc
        gc.collect()
        try:
            self.tmp.cleanup()
        except OSError:
            pass  # Windows may still hold a lock; let the OS clean up later

    def test_create_list_auto_title_rename_delete(self):
        conversation_id = crud.create_conversation(self.user_id)
        crud.add_message(conversation_id, "user", "帮我修改磷酸缓冲液方案")
        # 侧边栏只展示实验相关会话；加一条实验记录让会话可见。
        save_record({
            "session_id": "s1", "transcript": "加入5mL缓冲液",
            "conversation_id": conversation_id, "at": "2026-08-25 10:00:00",
        })
        items = crud.list_conversations(self.user_id)
        self.assertEqual(items[0]["title"], "帮我修改磷酸缓冲液方案")
        self.assertEqual(items[0]["message_count"], 1)

        self.assertTrue(crud.rename_conversation(conversation_id, "缓冲液方案修改", self.user_id))
        self.assertEqual(crud.list_conversations(self.user_id)[0]["title"], "缓冲液方案修改")

        self.assertTrue(crud.delete_conversation(conversation_id, self.user_id))
        self.assertEqual(crud.list_conversations(self.user_id), [])


if __name__ == "__main__":
    unittest.main()
