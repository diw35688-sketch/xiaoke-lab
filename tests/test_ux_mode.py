# -*- coding: utf-8 -*-
"""UX-MODE-01 输出分层测试：会话级 DEBUG 文件。"""

import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.main import _attach_session_debug_log


class SessionDebugLogTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.root = logging.getLogger()
        self.old_handlers = list(self.root.handlers)
        self.old_level = self.root.level
        for handler in self.old_handlers:
            self.root.removeHandler(handler)
        self.root.setLevel(logging.DEBUG)

    def tearDown(self):
        for handler in list(self.root.handlers):
            if getattr(handler, "_ai107_session_debug_log", False):
                self.root.removeHandler(handler)
                handler.close()
        self.root.setLevel(self.old_level)
        for handler in self.old_handlers:
            self.root.addHandler(handler)
        self._tmp.cleanup()

    def _session_handlers(self):
        return [
            handler
            for handler in self.root.handlers
            if getattr(handler, "_ai107_session_debug_log", False)
        ]

    def test_user_mode_creates_per_session_debug_file(self):
        with patch("src.main.UI_MODE", "user"), patch(
            "src.main.RESULTS_DIR", self.tmp_path
        ):
            _attach_session_debug_log("s1")

        logging.getLogger("ux_mode_test").debug("hello from session")

        for handler in self._session_handlers():
            handler.flush()
        debug_file = self.tmp_path / "debug_s1.log"
        self.assertTrue(debug_file.exists())
        self.assertIn(
            "hello from session",
            debug_file.read_text(encoding="utf-8"),
        )

    def test_new_session_replaces_previous_session_handler(self):
        with patch("src.main.UI_MODE", "user"), patch(
            "src.main.RESULTS_DIR", self.tmp_path
        ):
            _attach_session_debug_log("s1")
            _attach_session_debug_log("s2")

        handlers = self._session_handlers()
        self.assertEqual(len(handlers), 1)
        self.assertEqual(
            Path(handlers[0].baseFilename).name,
            "debug_s2.log",
        )

    def test_admin_mode_does_not_attach_session_file(self):
        with patch("src.main.UI_MODE", "admin"), patch(
            "src.main.RESULTS_DIR", self.tmp_path
        ):
            handler = _attach_session_debug_log("s1")

        self.assertIsNone(handler)
        self.assertEqual(self._session_handlers(), [])
        self.assertFalse((self.tmp_path / "debug_s1.log").exists())


if __name__ == "__main__":
    unittest.main()
