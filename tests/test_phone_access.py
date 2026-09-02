# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

import phone_access


class PhoneAccessTests(unittest.TestCase):
    def test_proxy_tun_default_route_does_not_hide_wifi(self):
        routes = """
          0.0.0.0          0.0.0.0       198.18.0.2       198.18.0.1      0
          0.0.0.0          0.0.0.0    10.101.192.98    10.101.192.18     50
        """
        with patch("subprocess.check_output", return_value=routes):
            self.assertEqual(phone_access.lan_ip(), "10.101.192.18")

    def test_benchmark_and_loopback_addresses_are_not_lan(self):
        self.assertFalse(phone_access._usable_lan_ip("198.18.0.1"))
        self.assertFalse(phone_access._usable_lan_ip("127.0.0.1"))
        self.assertTrue(phone_access._usable_lan_ip("192.168.1.25"))
        self.assertTrue(phone_access._usable_lan_ip("10.101.192.18"))


if __name__ == "__main__":
    unittest.main()
