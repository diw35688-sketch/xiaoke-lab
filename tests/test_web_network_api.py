import unittest
import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "web"))

from web.api.network import ModePayload, set_mode


class NetworkModeApiTests(unittest.TestCase):
    @patch("web.api.network.network_mode.set_mode")
    def test_post_mode_calls_real_switch(self, switch):
        switch.return_value = {
            "mode": "lan",
            "lan_url": "https://192.168.1.2:8000",
            "public_url": None,
            "cloudflared_ready": True,
            "tunnel_running": False,
        }
        result = set_mode(ModePayload(mode="lan"))
        switch.assert_called_once_with("lan")
        self.assertEqual(result["mode"], "lan")


if __name__ == "__main__":
    unittest.main()
