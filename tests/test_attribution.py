# -*- coding: utf-8 -*-
"""署名合同测试。

个人使用场景下，登录的用途不是数据隔离，而是给两样东西签名：
社区投稿的作者、实验记录的记录人。

两列并存的理由：id 可追溯（改名后仍查得到是哪个账号），
name 是当时的显示名快照（实验记录是科学档案，改名不该改写历史）。
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

import attribution  # noqa: E402
import auth as auth_core  # noqa: E402
from api import auth as auth_api  # noqa: E402
from app import app  # noqa: E402
from database import crud, db, user_store  # noqa: E402

PASSWORD = "a good lab password"


class AttributionTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.patches = [
            patch.object(db, "DATABASE_PATH", Path(self.tmp.name) / "sig.db"),
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


class SignatureResolutionTests(AttributionTestCase):
    def test_resolves_from_conversation_owner(self):
        user = user_store.create_user("alice", PASSWORD, "张三")
        cid = crud.create_conversation(user["id"])
        self.assertEqual(attribution.signature_for_conversation(cid),
                         (user["id"], "张三"))

    def test_falls_back_to_the_sole_account(self):
        # 自由记录模式没有 conversation_id；个人使用时库里只有一个账号
        user = user_store.create_user("alice", PASSWORD, "张三")
        self.assertEqual(attribution.signature_for_conversation(None),
                         (user["id"], "张三"))

    def test_never_invents_a_signature(self):
        # 没有账号时必须留空，让记录如实显示"未署名"，不能瞎猜
        self.assertEqual(attribution.signature_for_conversation(None), ("", ""))
        self.assertEqual(attribution.signature_for_conversation("no-such"), ("", ""))

    def test_ambiguous_multi_account_without_conversation_is_left_blank(self):
        user_store.create_user("alice", PASSWORD)
        user_store.create_user("bob", PASSWORD)
        self.assertEqual(attribution.signature_for_conversation(None), ("", ""),
                         "分不清是谁时不得随便签一个名")

    def test_display_name_falls_back_to_username(self):
        user = user_store.create_user("alice", PASSWORD)
        self.assertEqual(attribution.signature_for_conversation(None)[1], "alice")


class RecordSignatureTests(AttributionTestCase):
    def test_record_carries_both_id_and_name_snapshot(self):
        from database import lab_record_store

        user = user_store.create_user("alice", PASSWORD, "张三")
        cid = crud.create_conversation(user["id"])
        lab_record_store.save_record({
            "session_id": "s1", "transcript": "加入5mL缓冲液",
            "at": "2026-08-31 10:00:00", "conversation_id": cid,
        })
        with db.get_connection() as connection:
            row = connection.execute(
                "SELECT recorded_by_id, recorded_by_name FROM lab_records").fetchone()
        self.assertEqual(row["recorded_by_id"], user["id"])
        self.assertEqual(row["recorded_by_name"], "张三")

    def test_rename_does_not_rewrite_history(self):
        """实验记录是科学档案：事后改名不得改写既有记录的署名。"""
        from database import lab_record_store

        user = user_store.create_user("alice", PASSWORD, "张三")
        cid = crud.create_conversation(user["id"])
        lab_record_store.save_record({
            "session_id": "s1", "transcript": "加入5mL缓冲液",
            "at": "2026-08-31 10:00:00", "conversation_id": cid,
        })
        with db.get_connection() as connection:
            connection.execute("UPDATE users SET display_name='李四' WHERE id=?",
                               (user["id"],))
            row = connection.execute(
                "SELECT recorded_by_id, recorded_by_name FROM lab_records").fetchone()
        self.assertEqual(row["recorded_by_name"], "张三", "旧记录仍应显示当时的署名")
        self.assertEqual(row["recorded_by_id"], user["id"], "但仍可追溯到该账号")


class CommunityAuthorTests(AttributionTestCase):
    def test_author_comes_from_session_not_from_payload(self):
        client = TestClient(app)
        self.addCleanup(client.close)
        client.post("/auth/register",
                    json={"username": "alice", "password": PASSWORD,
                          "display_name": "张三"})
        response = client.post("/community", json={
            "kind": "protocol", "title": "PBS 配制",
            "content": {
                "protocol_id": "test_attribution",
                "title": "PBS 配制",
                "source": "社区",
                "version": "1",
                "schema_version": 1,
                "steps": [{
                    "step_number": 1, "title": "溶解", "instruction": "称量NaCl",
                    "protocol_values": {}, "must_record": [],
                    "terms": [], "hazard_note": "无",
                }],
            },
            "author": "我冒充的别人", "tags": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["entry"]["author"], "张三",
                         "作者必须取自登录态，不能由客户端指定")

    def test_publishing_requires_login(self):
        client = TestClient(app)
        self.addCleanup(client.close)
        response = client.post("/community", json={
            "kind": "protocol", "title": "x", "content": {}, "author": "", "tags": "",
        })
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
