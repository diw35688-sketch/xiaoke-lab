import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "web"))

import access_control  # noqa: E402
from app import app  # noqa: E402


class RemoteAccessMiddlewareTests(unittest.TestCase):
    def test_remote_request_without_token_is_rejected(self):
        client = TestClient(app, base_url="http://device.test")
        response = client.get("/health")
        self.assertEqual(response.status_code, 401)

    def test_valid_entry_token_becomes_cookie_and_is_removed_from_url(self):
        client = TestClient(app, base_url="http://device.test")
        response = client.get(
            "/health",
            params={access_control.ACCESS_TOKEN_PARAM: access_control.current_token()},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(access_control.ACCESS_TOKEN_PARAM, str(response.url))
        self.assertEqual(client.get("/health").status_code, 200)

    def test_spoofed_local_host_without_local_connection_is_rejected(self):
        client = TestClient(app, base_url="http://localhost")
        response = client.get("/health")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
