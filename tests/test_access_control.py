import unittest
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "web"))

import access_control  # noqa: E402


class AccessControlTests(unittest.TestCase):
    def test_generated_token_is_valid_and_wrong_token_is_rejected(self):
        self.assertTrue(access_control.is_valid(access_control.current_token()))
        self.assertFalse(access_control.is_valid("wrong"))
        self.assertFalse(access_control.is_valid(None))

    def test_add_token_preserves_existing_query(self):
        protected = access_control.add_token("https://example.test/phone?error=x")
        query = parse_qs(urlsplit(protected).query)
        self.assertEqual(query["error"], ["x"])
        self.assertEqual(query[access_control.ACCESS_TOKEN_PARAM], [access_control.current_token()])

    def test_without_token_preserves_other_query(self):
        protected = access_control.add_token("https://example.test/phone?error=x")
        clean = access_control.without_token(protected)
        self.assertEqual(clean, "https://example.test/phone?error=x")


if __name__ == "__main__":
    unittest.main()
