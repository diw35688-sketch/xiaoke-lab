# -*- coding: utf-8 -*-
"""登录接口与全局访问闸门的端到端合同测试。

最要紧的两条：
1. 未登录拿不到任何业务数据（闸门真的关着）；
2. 一个账号都没有时仍能创建第一个账号（闸门没把人锁在门外）。
第 2 条是这类改动最经典的事故：把认证做严，结果自己也进不去。
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

WEB = Path(__file__).resolve().parent.parent / "web"
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

from fastapi.testclient import TestClient  # noqa: E402

import auth as auth_core  # noqa: E402
from api import auth as auth_api  # noqa: E402
from app import app  # noqa: E402
from database import db, user_store  # noqa: E402

PASSWORD = "a good lab password"


class AuthAPITestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.patches = [
            patch.object(db, "DATABASE_PATH", Path(self.tmp.name) / "test.db"),
            patch.object(auth_core, "DEFAULT_ITERATIONS", 1000),
        ]
        for item in self.patches:
            item.start()
        db.initialize_database()
        auth_api._failures.clear()
        self.client = TestClient(app, follow_redirects=False)

    def tearDown(self):
        self.client.close()
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def bootstrap(self, username="alice", password=PASSWORD):
        return self.client.post("/auth/register",
                                json={"username": username, "password": password})


class GateTests(AuthAPITestCase):
    def test_page_navigation_redirects_to_login(self):
        response = self.client.get("/", headers={"accept": "text/html"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/login")

    def test_api_call_gets_401_not_a_redirect(self):
        # 接口要能区分「该跳转」和「该提示重新登录」
        response = self.client.get("/chat/conversations")
        self.assertEqual(response.status_code, 401)

    def test_login_page_and_health_are_open(self):
        self.assertEqual(self.client.get("/login").status_code, 200)
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_auth_state_is_open(self):
        response = self.client.get("/auth/state")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["authenticated"])
        self.assertTrue(response.json()["needs_bootstrap"])

    def test_logged_in_user_reaches_business_api(self):
        self.bootstrap()
        self.assertEqual(self.client.get("/chat/conversations").status_code, 200)


class BootstrapTests(AuthAPITestCase):
    def test_first_account_can_be_created_without_login(self):
        response = self.bootstrap()
        self.assertEqual(response.status_code, 200, "没有账号时必须允许创建第一个")
        body = response.json()
        self.assertTrue(body["user"]["is_admin"])
        self.assertTrue(body["logged_in"], "建完首个账号应直接登录")
        self.assertIn("lab_session", response.cookies)

    def test_after_bootstrap_registration_requires_admin(self):
        self.bootstrap()
        self.client.post("/auth/logout")
        response = self.client.post(
            "/auth/register", json={"username": "bob", "password": PASSWORD})
        self.assertEqual(response.status_code, 401)

    def test_non_admin_cannot_create_accounts(self):
        self.bootstrap()
        self.client.post("/auth/register",
                         json={"username": "bob", "password": PASSWORD})
        self.client.post("/auth/logout")
        self.client.post("/auth/login", json={"username": "bob", "password": PASSWORD})
        response = self.client.post(
            "/auth/register", json={"username": "carol", "password": PASSWORD})
        self.assertEqual(response.status_code, 403)

    def test_admin_can_create_accounts(self):
        self.bootstrap()
        response = self.client.post(
            "/auth/register", json={"username": "bob", "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["user"]["is_admin"])


class LoginTests(AuthAPITestCase):
    def setUp(self):
        super().setUp()
        self.bootstrap()
        self.client.post("/auth/logout")

    def test_login_sets_cookie_and_state(self):
        response = self.client.post(
            "/auth/login", json={"username": "alice", "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertIn("lab_session", response.cookies)
        self.assertTrue(self.client.get("/auth/state").json()["authenticated"])

    def test_cookie_is_httponly(self):
        response = self.client.post(
            "/auth/login", json={"username": "alice", "password": PASSWORD})
        header = response.headers["set-cookie"].lower()
        self.assertIn("httponly", header, "令牌 Cookie 必须 HttpOnly，否则 XSS 可窃取")
        self.assertIn("samesite=lax", header)

    def test_wrong_password_rejected(self):
        response = self.client.post(
            "/auth/login", json={"username": "alice", "password": "wrong password!!"})
        self.assertEqual(response.status_code, 401)
        self.assertFalse(self.client.get("/auth/state").json()["authenticated"])

    def test_unknown_user_is_indistinguishable_from_wrong_password(self):
        a = self.client.post("/auth/login",
                             json={"username": "alice", "password": "wrong password!!"})
        b = self.client.post("/auth/login",
                             json={"username": "nobody", "password": "wrong password!!"})
        self.assertEqual(a.status_code, b.status_code)
        self.assertEqual(a.json()["detail"], b.json()["detail"])

    def test_logout_closes_the_door(self):
        self.client.post("/auth/login", json={"username": "alice", "password": PASSWORD})
        self.client.post("/auth/logout")
        self.assertEqual(self.client.get("/chat/conversations").status_code, 401)

    def test_login_is_rate_limited(self):
        for _ in range(auth_api._FAIL_LIMIT):
            self.client.post("/auth/login",
                             json={"username": "alice", "password": "wrong password!!"})
        response = self.client.post(
            "/auth/login", json={"username": "alice", "password": PASSWORD})
        self.assertEqual(response.status_code, 429, "连续失败后必须锁定，否则公网可爆破")


class PasswordChangeTests(AuthAPITestCase):
    def setUp(self):
        super().setUp()
        self.bootstrap()

    def test_change_password_requires_current(self):
        response = self.client.post("/auth/password", json={
            "current_password": "not the password", "new_password": "brand new password"})
        self.assertEqual(response.status_code, 401)

    def test_change_password_keeps_me_logged_in(self):
        response = self.client.post("/auth/password", json={
            "current_password": PASSWORD, "new_password": "brand new password"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/chat/conversations").status_code, 200)

    def test_old_password_stops_working(self):
        self.client.post("/auth/password", json={
            "current_password": PASSWORD, "new_password": "brand new password"})
        self.client.post("/auth/logout")
        self.assertEqual(self.client.post(
            "/auth/login", json={"username": "alice", "password": PASSWORD}).status_code, 401)
        self.assertEqual(self.client.post(
            "/auth/login",
            json={"username": "alice", "password": "brand new password"}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
