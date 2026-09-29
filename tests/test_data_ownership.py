# -*- coding: utf-8 -*-
"""数据归属隔离测试：登录之后，每个人只能看见和动自己的东西。

这组测试是多用户功能的核心保证。任何一条挂掉都意味着越权，
后果是把别人的实验记录暴露出去——所以宁可测得啰嗦。
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

WEB = Path(__file__).resolve().parent.parent / "web"
for _path in (str(WEB), str(Path(__file__).resolve().parent)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from fastapi.testclient import TestClient  # noqa: E402

import auth as auth_core  # noqa: E402
from api import auth as auth_api  # noqa: E402
from app import app  # noqa: E402
from database import crud, db, user_store  # noqa: E402
from database.lab_record_store import save_record  # noqa: E402

PASSWORD = "a good lab password"


class OwnershipTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.patches = [
            patch.object(db, "DATABASE_PATH", Path(self.tmp.name) / "own.db"),
            patch.object(auth_core, "DEFAULT_ITERATIONS", 1000),
        ]
        for item in self.patches:
            item.start()
        db.initialize_database()
        auth_api._failures.clear()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def client_for(self, username, bootstrap=False):
        """返回一个已登录该账号的独立客户端（各自持有自己的 Cookie）。"""
        client = TestClient(app)
        if bootstrap:
            client.post("/auth/register",
                        json={"username": username, "password": PASSWORD})
        else:
            admin = TestClient(app)
            admin.post("/auth/login", json={"username": "alice", "password": PASSWORD})
            admin.post("/auth/register",
                       json={"username": username, "password": PASSWORD})
            admin.close()
            client.post("/auth/login",
                        json={"username": username, "password": PASSWORD})
        return client


class CrudGuardTests(OwnershipTestCase):
    """归属参数是必填的：缺了要报错，不能被当成"不过滤"。"""

    def test_blank_owner_is_rejected_everywhere(self):
        for call in (
            lambda: crud.list_conversations(""),
            lambda: crud.list_conversations(None),
            lambda: crud.latest_conversation(""),
            lambda: crud.create_conversation(""),
            lambda: crud.conversation_exists("x", ""),
            lambda: crud.delete_conversation("x", ""),
        ):
            with self.subTest(call=call):
                with self.assertRaises(ValueError):
                    call()

    def test_owner_argument_has_no_default(self):
        import inspect
        for name in ("list_conversations", "latest_conversation", "create_conversation"):
            signature = inspect.signature(getattr(crud, name))
            first = list(signature.parameters.values())[0]
            self.assertEqual(first.name, "user_id")
            self.assertIs(first.default, inspect.Parameter.empty,
                          f"{name} 的 user_id 不得有默认值，否则漏传即越权")


class ConversationIsolationTests(OwnershipTestCase):
    def setUp(self):
        super().setUp()
        self.alice = self.client_for("alice", bootstrap=True)
        self.bob = self.client_for("bob")
        self.alice_convo = self.alice.post("/chat/conversations").json()["conversation_id"]
        # 让会话带上一条消息和实验记录，否则侧边栏不展示纯闲聊会话。
        crud.add_message(self.alice_convo, "user", "爱丽丝的实验记录")
        save_record({
            "session_id": "s1", "transcript": "爱丽丝的实验记录",
            "conversation_id": self.alice_convo, "at": "2026-08-25 10:00:00",
        })

    def tearDown(self):
        self.alice.close()
        self.bob.close()
        super().tearDown()

    def test_list_shows_only_my_conversations(self):
        mine = self.alice.get("/chat/conversations").json()["items"]
        theirs = self.bob.get("/chat/conversations").json()["items"]
        self.assertEqual([c["id"] for c in mine], [self.alice_convo])
        self.assertEqual(theirs, [], "鲍勃不该看见爱丽丝的任何会话")

    def test_cannot_rename_someone_elses_conversation(self):
        response = self.bob.patch(f"/chat/conversations/{self.alice_convo}",
                                  json={"title": "被篡改"})
        self.assertEqual(response.status_code, 404, "别人的会话应表现为不存在")
        items = self.alice.get("/chat/conversations").json()["items"]
        self.assertNotEqual(items[0]["title"], "被篡改")

    def test_cannot_delete_someone_elses_conversation(self):
        response = self.bob.delete(f"/chat/conversations/{self.alice_convo}")
        self.assertEqual(response.status_code, 404)
        self.assertTrue(crud.conversation_exists(self.alice_convo, self._alice_id()),
                        "越权删除必须完全无副作用")

    def test_history_never_leaks_another_users_conversation(self):
        response = self.bob.get(f"/chat/history?conversation_id={self.alice_convo}")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsNone(body["conversation_id"], "指定别人的会话时应回落为空")
        self.assertEqual(body["messages"], [])

    def test_each_user_gets_their_own_latest_conversation(self):
        bob_convo = self.bob.post("/chat/conversations").json()["conversation_id"]
        crud.add_message(bob_convo, "user", "鲍勃的记录")
        self.assertEqual(crud.latest_conversation(self._alice_id()), self.alice_convo)
        self.assertEqual(crud.latest_conversation(self._bob_id()), bob_convo)

    def _alice_id(self):
        return user_store.find_by_username("alice")["id"]

    def _bob_id(self):
        return user_store.find_by_username("bob")["id"]


class OrphanClaimTests(OwnershipTestCase):
    """升级路径：登录功能是后加的，既有数据不能因此人间蒸发。"""

    def test_first_account_inherits_pre_existing_data(self):
        with db.get_connection() as connection:
            connection.execute(
                "INSERT INTO conversations (id,title) VALUES ('legacy','升级前的会话')")
            connection.execute(
                "INSERT INTO messages (conversation_id,role,content)"
                " VALUES ('legacy','user','升级前的记录')")
            # 加一条实验记录让侧边栏展示这个会话。
            connection.execute(
                "INSERT INTO lab_records (session_id,transcript,conversation_id,at,segment_id)"
                " VALUES ('legacy','升级前的实验','legacy','2026-01-01 10:00:00','seg-1')")
        self.assertEqual(user_store.count_orphaned_data().get("conversations"), 1)

        client = self.client_for("alice", bootstrap=True)
        self.addCleanup(client.close)
        items = client.get("/chat/conversations").json()["items"]
        self.assertIn("legacy", [c["id"] for c in items],
                      "首个账号必须继承升级前的数据，否则用户会以为历史丢了")
        self.assertEqual(user_store.count_orphaned_data(), {})

    def test_second_account_inherits_nothing(self):
        with db.get_connection() as connection:
            connection.execute(
                "INSERT INTO conversations (id,title) VALUES ('legacy','升级前的会话')")
            connection.execute(
                "INSERT INTO messages (conversation_id,role,content)"
                " VALUES ('legacy','user','升级前的记录')")
        alice = self.client_for("alice", bootstrap=True)
        bob = self.client_for("bob")
        self.addCleanup(alice.close)
        self.addCleanup(bob.close)
        self.assertEqual(bob.get("/chat/conversations").json()["items"], [],
                         "认领只发生一次，第二个账号不得继承任何东西")

    def test_claim_is_idempotent(self):
        user = user_store.create_user("alice", PASSWORD)
        with db.get_connection() as connection:
            connection.execute(
                "INSERT INTO conversations (id,title) VALUES ('later','后来的')")
        first = user_store.claim_orphaned_data(user["id"])
        second = user_store.claim_orphaned_data(user["id"])
        self.assertEqual(first.get("conversations"), 1)
        self.assertEqual(second, {}, "重复认领不应重复划走数据")


if __name__ == "__main__":
    unittest.main()
