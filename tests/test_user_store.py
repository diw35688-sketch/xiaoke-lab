# -*- coding: utf-8 -*-
"""用户与登录会话持久层合同测试。"""

import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

WEB_DIR = Path(__file__).resolve().parents[1] / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

import auth  # noqa: E402
from database.db import initialize_database  # noqa: E402
from database import user_store  # noqa: E402

PASSWORD = "a good lab password"
OTHER = "another good password"


class UserStoreTestCase(unittest.TestCase):
    def setUp(self):
        # ignore_cleanup_errors：Windows 上 SQLite 句柄释放晚于 tearDown，
        # 既有 test_conversations 就是因此长期飘红，这里不重蹈覆辙。
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.tmp.name) / "test.db"
        self.patches = [
            patch("database.db.DATABASE_PATH", self.db_path),
            patch.object(auth, "DEFAULT_ITERATIONS", 1000),
        ]
        for item in self.patches:
            item.start()
        initialize_database()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def rows(self, sql):
        with sqlite3.connect(self.db_path) as connection:
            return connection.execute(sql).fetchall()


class UserCreationTests(UserStoreTestCase):
    def test_first_user_is_admin_second_is_not(self):
        first = user_store.create_user("alice", PASSWORD)
        second = user_store.create_user("bob", OTHER)
        self.assertTrue(first["is_admin"], "首个用户必须是管理员，否则没人能建账号")
        self.assertFalse(second["is_admin"])

    def test_username_normalized_on_create(self):
        created = user_store.create_user("  Alice  ", PASSWORD)
        self.assertEqual(created["username"], "alice")
        self.assertIsNotNone(user_store.find_by_username("alice"))

    def test_duplicate_username_rejected_case_insensitively(self):
        user_store.create_user("alice", PASSWORD)
        with self.assertRaises(auth.AuthError):
            user_store.create_user("ALICE", OTHER)
        self.assertEqual(user_store.count_users(), 1)

    def test_display_name_defaults_to_username(self):
        self.assertEqual(user_store.create_user("alice", PASSWORD)["display_name"], "alice")
        self.assertEqual(
            user_store.create_user("bob", OTHER, "鲍勃")["display_name"], "鲍勃")

    def test_weak_password_rejected_before_any_row_is_written(self):
        with self.assertRaises(auth.AuthError):
            user_store.create_user("alice", "short")
        self.assertEqual(user_store.count_users(), 0)


class SecretsAtRestTests(UserStoreTestCase):
    """库被拷走时的最低保证：拿不到口令，也拿不到可用的登录令牌。"""

    def test_password_is_never_stored_in_plaintext(self):
        user_store.create_user("alice", PASSWORD)
        dump = str(self.rows("SELECT * FROM users"))
        self.assertNotIn(PASSWORD, dump)
        self.assertIn("pbkdf2_sha256", dump)

    def test_session_token_is_never_stored_in_plaintext(self):
        user = user_store.create_user("alice", PASSWORD)
        token = user_store.create_session(user["id"])
        dump = str(self.rows("SELECT * FROM user_sessions"))
        self.assertNotIn(token, dump, "库里存的必须是令牌散列，不是令牌本身")
        self.assertIn(auth.hash_session_token(token), dump)


class LoginTests(UserStoreTestCase):
    def setUp(self):
        super().setUp()
        self.user = user_store.create_user("alice", PASSWORD)

    def test_correct_password_logs_in(self):
        self.assertEqual(user_store.verify_login("alice", PASSWORD)["id"], self.user["id"])

    def test_login_is_case_insensitive_on_username(self):
        self.assertIsNotNone(user_store.verify_login("ALICE", PASSWORD))

    def test_wrong_password_and_unknown_user_both_return_none(self):
        # 两者不可区分，否则等于开放账号枚举
        self.assertIsNone(user_store.verify_login("alice", "wrong password here"))
        self.assertIsNone(user_store.verify_login("nobody", PASSWORD))
        self.assertIsNone(user_store.verify_login("!!bad-format!!", PASSWORD))

    def test_deactivated_user_cannot_log_in(self):
        user_store.set_active(self.user["id"], False)
        self.assertIsNone(user_store.verify_login("alice", PASSWORD))

    def test_login_records_timestamp(self):
        self.assertIsNone(self.user["last_login_at"])
        user_store.verify_login("alice", PASSWORD)
        self.assertIsNotNone(user_store.find_by_id(self.user["id"])["last_login_at"])


class SessionLifecycleTests(UserStoreTestCase):
    def setUp(self):
        super().setUp()
        self.user = user_store.create_user("alice", PASSWORD)

    def test_create_and_resolve(self):
        token = user_store.create_session(self.user["id"])
        self.assertEqual(user_store.resolve_session(token)["username"], "alice")

    def test_unknown_or_blank_token_resolves_to_none(self):
        for bad in ("", None, "not-a-real-token"):
            with self.subTest(bad=bad):
                self.assertIsNone(user_store.resolve_session(bad))

    def test_logout_invalidates(self):
        token = user_store.create_session(self.user["id"])
        user_store.delete_session(token)
        self.assertIsNone(user_store.resolve_session(token))

    def test_expired_session_rejected_and_removed(self):
        token = user_store.create_session(self.user["id"], ttl_days=-1)
        self.assertIsNone(user_store.resolve_session(token))
        self.assertEqual(len(self.rows("SELECT * FROM user_sessions")), 0)

    def test_resolving_slides_the_expiry_forward(self):
        token = user_store.create_session(self.user["id"], ttl_days=1)
        before = self.rows("SELECT expires_at FROM user_sessions")[0][0]
        user_store.resolve_session(token, ttl_days=30)
        after = self.rows("SELECT expires_at FROM user_sessions")[0][0]
        self.assertGreater(after, before, "每次访问应顺延有效期")

    def test_deactivating_user_kills_sessions(self):
        token = user_store.create_session(self.user["id"])
        user_store.set_active(self.user["id"], False)
        self.assertIsNone(user_store.resolve_session(token))

    def test_password_change_revokes_all_sessions(self):
        # 改密的动机通常正是怀疑别人在用这个账号，必须踢掉旧登录态
        first = user_store.create_session(self.user["id"])
        second = user_store.create_session(self.user["id"])
        user_store.set_password(self.user["id"], "a brand new password")
        self.assertIsNone(user_store.resolve_session(first))
        self.assertIsNone(user_store.resolve_session(second))
        self.assertIsNotNone(user_store.verify_login("alice", "a brand new password"))

    def test_sessions_are_isolated_between_users(self):
        bob = user_store.create_user("bob", OTHER)
        alice_token = user_store.create_session(self.user["id"])
        bob_token = user_store.create_session(bob["id"])
        self.assertEqual(user_store.resolve_session(alice_token)["username"], "alice")
        self.assertEqual(user_store.resolve_session(bob_token)["username"], "bob")
        user_store.revoke_all_sessions(bob["id"])
        self.assertIsNone(user_store.resolve_session(bob_token))
        self.assertIsNotNone(user_store.resolve_session(alice_token), "不得误伤他人登录态")

    def test_purge_expired_only_removes_expired(self):
        live = user_store.create_session(self.user["id"], ttl_days=5)
        user_store.create_session(self.user["id"], ttl_days=-1)
        self.assertEqual(user_store.purge_expired_sessions(), 1)
        self.assertIsNotNone(user_store.resolve_session(live))


if __name__ == "__main__":
    unittest.main()
