# -*- coding: utf-8 -*-
"""手机演示页 /m 的路由与页面结构测试：不依赖网络、不触发数据库。

覆盖：/m 路由已注册；mobile.html 含录音按钮与脚本引用；
mobile.js 走现有 /asr/transcribe 与 /record 接口约定。
"""

import sys
import unittest
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

FRONTEND_DIR = WEB_DIR / "frontend"


class WebMobilePageTests(unittest.TestCase):
    def test_m_route_is_registered(self):
        from app import app

        paths = [getattr(route, "path", "") for route in app.routes]
        self.assertIn("/m", paths)

    def test_mobile_ua_on_root_serves_mobile_page(self):
        from fastapi.testclient import TestClient

        from app import app

        with TestClient(app) as client:
            response = client.get("/", headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"})
        self.assertEqual(response.status_code, 200)
        self.assertIn('id="m-record-btn"', response.text)

    def test_desktop_ua_on_root_serves_desktop_page(self):
        from fastapi.testclient import TestClient

        from app import app

        with TestClient(app) as client:
            response = client.get("/", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('id="m-record-btn"', response.text)
        self.assertIn("实验工作台", response.text)

    def test_mobile_html_has_record_button(self):
        html = (FRONTEND_DIR / "mobile.html").read_text(encoding="utf-8")
        self.assertIn('id="m-record-btn"', html)
        self.assertIn("/static/mobile.js", html)
        self.assertIn('name="viewport"', html)

    def test_mobile_js_uses_existing_api_contracts(self):
        js = (FRONTEND_DIR / "mobile.js").read_text(encoding="utf-8")
        self.assertIn("/asr/transcribe", js)
        self.assertIn('"/record/stream"', js)
        self.assertIn("response.body.getReader()", js)
        self.assertIn("getUserMedia", js)
        # B4：mobile.js 消费 /record 的 messages 合同（kind/screen_target/text），
        # 前端只按 kind/screen_target 上样式、显示/朗读 text，不自行判断。
        self.assertIn("messages", js)
        self.assertIn("screen_target", js)
        self.assertIn('"clarification"', js)
        # 旧薄字典平行投影字段已退役（前端不再读 evaluation 自行判断/拼话）
        self.assertNotIn("follow_up_question", js)
        self.assertNotIn("deviations", js)

    def test_mobile_page_does_not_depend_on_desktop_scripts(self):
        html = (FRONTEND_DIR / "mobile.html").read_text(encoding="utf-8")
        for desktop_script in ("shell.js", "composer.js", "vad_mode.js", "voice_asr.js"):
            self.assertNotIn(desktop_script, html)


if __name__ == "__main__":
    unittest.main()
