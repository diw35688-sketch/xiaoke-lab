# -*- coding: utf-8 -*-
"""web/settings_store.py 从文件重建配置时 TTS 字段完整性的单测。

历史 bug：current() 从文件重建只读部分字段（漏 tts_provider/tts_api_key/
tts_model/tts_voice），导致直改文件后服务端拿不到 TTS 配置。
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

import settings_store  # noqa: E402


class SettingsStoreFileReadTests(unittest.TestCase):
    def tearDown(self):
        # 复位进程内缓存，避免影响其他测试
        with settings_store._lock:
            settings_store._cache = None

    def test_current_reads_all_tts_fields_from_file(self):
        payload = {
            "api_key": "sk-test",
            "base_url": "https://example.com/v1",
            "model_name": "test-model",
            "tts_enabled": True,
            "speak_record_ack": True,
            "tts_url": "http://127.0.0.1:8001/tts",
            "tts_provider": "volcano",
            "tts_api_key": "appid123:tok456",
            "tts_base_url": "https://openspeech.bytedance.com/api/v1/tts",
            "tts_model": "volcano_tts",
            "tts_voice": "BV001_streaming",
            "tts_speed": 1.2,
        }
        with tempfile.TemporaryDirectory() as directory:
            settings_file = Path(directory) / "settings.json"
            settings_file.write_text(json.dumps(payload), encoding="utf-8")
            with mock.patch.object(settings_store, "SETTINGS_FILE", settings_file):
                settings = settings_store.current()

        self.assertEqual(settings.tts_provider, "volcano")
        self.assertEqual(settings.tts_api_key, "appid123:tok456")
        self.assertEqual(settings.tts_base_url, "https://openspeech.bytedance.com/api/v1/tts")
        self.assertEqual(settings.tts_model, "volcano_tts")
        self.assertEqual(settings.tts_voice, "BV001_streaming")
        self.assertEqual(settings.tts_speed, 1.2)
        self.assertTrue(settings.tts_enabled)
        self.assertTrue(settings.speak_record_ack)

    def test_speak_record_ack_defaults_on_when_absent_from_file(self):
        payload = {
            "api_key": "sk-test",
            "base_url": "https://example.com/v1",
            "model_name": "test-model",
            "tts_enabled": True,
        }
        with tempfile.TemporaryDirectory() as directory:
            settings_file = Path(directory) / "settings.json"
            settings_file.write_text(json.dumps(payload), encoding="utf-8")
            with mock.patch.object(settings_store, "SETTINGS_FILE", settings_file):
                settings = settings_store.current()

        self.assertTrue(settings.speak_record_ack)


if __name__ == "__main__":
    unittest.main()
