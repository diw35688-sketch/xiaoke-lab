# -*- coding: utf-8 -*-
"""跨用户越权测试：拿到别人的 conversation_id 也不能读、不能删。

事故记录（2026-08-31）：登录与归属列做完后，只有 crud.py 的会话增删改查
加了归属过滤。实测发现任何登录用户执行
    DELETE /turn/conversations/<别人的会话ID>
就能把对方的实验记录与消息清零（1 -> 0）。

教训：**「数据模型上归属谁」不等于「查询时会不会被拦住」**。
每一个接受 conversation_id 的入口都必须显式校验归属。
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

WEB = Path(__file__).resolve().parent.parent / "web"
for _p in (str(WEB), str(Path(__file__).resolve().parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fastapi.testclient import TestClient  # noqa: E402

import auth as auth_core  # noqa: E402
from api import auth as auth_api  # noqa: E402
from app import app  # noqa: E402
from database import crud, db, user_store  # noqa: E402

PASSWORD = "a good lab password"


class CrossUserAccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.patches = [
            patch.object(db, "DATABASE_PATH", Path(self.tmp.name) / "x.db"),
            patch.object(auth_core, "DEFAULT_ITERATIONS", 1000),
        ]
        for item in self.patches:
            item.start()
        db.initialize_database()
        auth_api._failures.clear()

        self.alice = TestClient(app)
        self.alice.post("/auth/register",
                        json={"username": "alice", "password": PASSWORD})
        self.alice.post("/auth/register",
                        json={"username": "bob", "password": PASSWORD})
        self.bob = TestClient(app)
        self.bob.post("/auth/login", json={"username": "bob", "password": PASSWORD})

        self.alice_id = user_store.find_by_username("alice")["id"]
        self.cid = self.alice.post("/chat/conversations").json()["conversation_id"]
        crud.add_message(self.cid, "user", "爱丽丝的机密实验记录")
        with db.get_connection() as connection:
            connection.execute(
                "INSERT INTO lab_records (session_id,segment_id,transcript,conversation_id,at)"
                " VALUES ('s1',1,'加入5mL浓硫酸',?,'2026-08-31 10:00:00')", (self.cid,))

    def tearDown(self):
        self.alice.close()
        self.bob.close()
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def _record_count(self):
        with db.get_connection() as connection:
            return connection.execute(
                "SELECT COUNT(*) FROM lab_records WHERE conversation_id=?",
                (self.cid,)).fetchone()[0]

    def test_cannot_delete_another_users_turn_data(self):
        """这条就是实测出来的真实漏洞，必须永远红着直到修好。"""
        response = self.bob.delete(f"/turn/conversations/{self.cid}")
        self.assertEqual(response.status_code, 404, "别人的会话必须表现为不存在")
        self.assertEqual(self._record_count(), 1, "越权删除必须完全无副作用")
        self.assertEqual(len(crud.get_messages(self.cid)), 1)

    def test_cannot_delete_another_users_experiment_session(self):
        response = self.bob.delete(
            f"/turn/conversations/{self.cid}/experiment-sessions/lab-1")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self._record_count(), 1)

    def test_cannot_read_another_users_turn_history(self):
        self.assertEqual(
            self.bob.get(f"/turn/history?conversation_id={self.cid}").status_code, 404)

    def test_owner_still_has_full_access(self):
        # 收紧权限不能把主人自己关在门外
        self.assertEqual(
            self.alice.get(f"/turn/history?conversation_id={self.cid}").status_code, 200)
        self.assertEqual(
            self.alice.delete(f"/turn/conversations/{self.cid}").status_code, 200)

    def test_chat_history_does_not_leak(self):
        body = self.bob.get(f"/chat/history?conversation_id={self.cid}").json()
        self.assertIsNone(body["conversation_id"])
        self.assertEqual(body["messages"], [])

    def test_rejection_is_404_not_403(self):
        # 403 等于确认「这个 ID 真实存在」，可被用来枚举他人会话
        real = self.bob.get(f"/turn/history?conversation_id={self.cid}")
        fake = self.bob.get("/turn/history?conversation_id=does-not-exist-at-all")
        self.assertEqual(real.status_code, fake.status_code)
        self.assertEqual(real.json()["detail"], fake.json()["detail"])


if __name__ == "__main__":
    unittest.main()
