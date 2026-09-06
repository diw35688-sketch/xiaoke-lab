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


class ConversationCrudTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        self.patch = patch("database.db.DATABASE_PATH", self.db_path)
        self.patch.start()
        initialize_database()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_create_list_auto_title_rename_delete(self):
        conversation_id = crud.create_conversation()
        items = crud.list_conversations()
        self.assertEqual(items[0]["title"], "新会话")

        crud.add_message(conversation_id, "user", "帮我修改磷酸缓冲液方案")
        items = crud.list_conversations()
        self.assertEqual(items[0]["title"], "帮我修改磷酸缓冲液方案")
        self.assertEqual(items[0]["message_count"], 1)

        self.assertTrue(crud.rename_conversation(conversation_id, "缓冲液方案修改"))
        self.assertEqual(crud.list_conversations()[0]["title"], "缓冲液方案修改")

        self.assertTrue(crud.delete_conversation(conversation_id))
        self.assertEqual(crud.list_conversations(), [])


if __name__ == "__main__":
    unittest.main()
