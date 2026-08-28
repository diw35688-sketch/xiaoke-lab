# -*- coding: utf-8 -*-
"""模型连通性探针也必须显式关闭 DeepSeek 思考模式。"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

PROJECT_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = PROJECT_DIR / "web"
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from scripts import setup_config  # noqa: E402
import settings_store  # noqa: E402


class _UrlopenResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class ThinkingDisabledProbeTests(unittest.TestCase):
    def test_setup_probe_disables_thinking(self):
        captured: dict[str, object] = {}

        def fake_urlopen(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return _UrlopenResponse()

        values = {
            "LLM_BASE_URL": "https://example.test",
            "LLM_API_KEY": "secret",
            "LLM_MODEL": "deepseek-chat",
        }
        with mock.patch.object(
            setup_config.urllib.request, "urlopen", side_effect=fake_urlopen
        ):
            ok, _ = setup_config.test_connection(values, timeout=3.0)

        self.assertTrue(ok)
        self.assertEqual(
            captured["payload"]["thinking"], {"type": "disabled"}
        )

    def test_web_settings_probe_disables_thinking(self):
        settings = settings_store.ModelSettings(
            api_key="secret",
            base_url="https://example.test/v1",
            model_name="deepseek-chat",
        )
        with mock.patch(
            "httpx.post", return_value=SimpleNamespace(status_code=200)
        ) as post:
            ok, _ = settings_store.test_connection(settings)

        self.assertTrue(ok)
        self.assertEqual(
            post.call_args.kwargs["json"]["thinking"],
            {"type": "disabled"},
        )


if __name__ == "__main__":
    unittest.main()
