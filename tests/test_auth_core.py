# -*- coding: utf-8 -*-
"""认证内核合同测试：口令散列、令牌、用户名规范化。

这些是安全边界，出错的后果不是"体验差"而是"账号被冒用"，
因此把不变量钉死，任何人改动都必须先解释为什么可以放宽。
"""

import sys
import unittest
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parents[1] / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

import auth  # noqa: E402

FAST = 1000  # 测试用低轮数；生产强度由 test_production_strength 单独把关


class PasswordHashTests(unittest.TestCase):
    def test_roundtrip(self):
        encoded = auth.hash_password("correct horse battery", iterations=FAST)
        self.assertTrue(auth.verify_password("correct horse battery", encoded))

    def test_wrong_password_rejected(self):
        encoded = auth.hash_password("correct horse battery", iterations=FAST)
        self.assertFalse(auth.verify_password("Correct horse battery", encoded))
        self.assertFalse(auth.verify_password("", encoded))

    def test_same_password_yields_different_hashes(self):
        # 每次必须换盐，否则相同口令的用户在库里长得一样，一眼可见
        a = auth.hash_password("same-password-1", iterations=FAST)
        b = auth.hash_password("same-password-1", iterations=FAST)
        self.assertNotEqual(a, b)
        self.assertTrue(auth.verify_password("same-password-1", a))
        self.assertTrue(auth.verify_password("same-password-1", b))

    def test_hash_is_self_describing(self):
        encoded = auth.hash_password("another-password", iterations=FAST)
        algorithm, iterations, salt, digest = encoded.split("$")
        self.assertEqual(algorithm, "pbkdf2_sha256")
        self.assertEqual(int(iterations), FAST)
        self.assertTrue(salt and digest)

    def test_plaintext_never_appears_in_hash(self):
        encoded = auth.hash_password("unmistakable-secret", iterations=FAST)
        self.assertNotIn("unmistakable-secret", encoded)

    def test_malformed_hash_returns_false_never_raises(self):
        for bad in ("", "not-a-hash", "a$b$c$d", "pbkdf2_sha256$0$x$y",
                    "pbkdf2_sha256$abc$x$y", "md5$1$x$y", None, 123):
            with self.subTest(bad=bad):
                self.assertFalse(auth.verify_password("x", bad))

    def test_production_strength(self):
        # OWASP 2023 对 PBKDF2-SHA256 的推荐下限
        self.assertGreaterEqual(auth.DEFAULT_ITERATIONS, 600_000)

    def test_needs_rehash(self):
        self.assertTrue(auth.needs_rehash(auth.hash_password("pw-to-upgrade", iterations=FAST)))
        self.assertFalse(auth.needs_rehash(
            auth.hash_password("pw-current", iterations=FAST), iterations=FAST))
        self.assertTrue(auth.needs_rehash("garbage"))
        self.assertTrue(auth.needs_rehash("md5$600000$x$y"))


class PasswordPolicyTests(unittest.TestCase):
    def test_rejects_too_short(self):
        with self.assertRaises(auth.AuthError):
            auth.validate_password("short12")

    def test_rejects_blank_and_oversized(self):
        with self.assertRaises(auth.AuthError):
            auth.validate_password("         ")
        with self.assertRaises(auth.AuthError):
            auth.validate_password("x" * 2000)

    def test_accepts_a_plain_long_passphrase(self):
        # 不强制大小写符号混合：复杂度规则会把人逼去写便签贴屏幕上
        self.assertTrue(auth.validate_password("my lab notebook password"))


class UsernameTests(unittest.TestCase):
    def test_normalizes_case_and_whitespace(self):
        self.assertEqual(auth.normalize_username("  Alice_01 "), "alice_01")

    def test_rejects_invalid(self):
        for bad in ("", "a", "_leading", "has space", "x" * 33, "中文名", "a@b"):
            with self.subTest(bad=bad):
                with self.assertRaises(auth.AuthError):
                    auth.normalize_username(bad)

    def test_case_variants_collapse_to_one_account(self):
        self.assertEqual(auth.normalize_username("ALICE"), auth.normalize_username("alice"))


class SessionTokenTests(unittest.TestCase):
    def test_tokens_are_unique_and_high_entropy(self):
        tokens = {auth.issue_session_token().token for _ in range(200)}
        self.assertEqual(len(tokens), 200)
        self.assertGreaterEqual(len(next(iter(tokens))), 32)

    def test_hash_is_deterministic_and_hides_token(self):
        issued = auth.issue_session_token()
        self.assertEqual(auth.hash_session_token(issued.token), issued.token_hash)
        self.assertNotIn(issued.token, issued.token_hash)

    def test_blank_token_rejected(self):
        for bad in ("", "   ", None):
            with self.subTest(bad=bad):
                with self.assertRaises(auth.AuthError):
                    auth.hash_session_token(bad)


if __name__ == "__main__":
    unittest.main()
