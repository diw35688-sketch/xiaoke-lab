# -*- coding: utf-8 -*-
"""手机演示页 /m 的路由与页面结构测试：不依赖网络、不触发数据库。

覆盖：/m 路由已注册；mobile.html 含录音按钮与脚本引用；
mobile.js 通过 turn_client 走统一 /turn/audio SSE 合同。
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

    def test_mobile_ua_on_root_serves_responsive_desktop_page(self):
        from fastapi.testclient import TestClient

        from app import app

        with TestClient(app) as client:
            response = client.get("/", headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("mobile-shell.css", response.text)
        self.assertIn("mobile_shell.js", response.text)

    def test_desktop_ua_on_root_serves_desktop_page(self):
        from fastapi.testclient import TestClient

        from app import app

        with TestClient(app) as client:
            response = client.get("/", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('id="m-record-btn"', response.text)
        self.assertIn("实验工作台", response.text)

    def test_legacy_mobile_html_has_chat_entry(self):
        html = (FRONTEND_DIR / "mobile.html").read_text(encoding="utf-8")
        self.assertIn('id="m-chat-input"', html)
        self.assertIn("/static/mobile_cards.js", html)
        self.assertIn('name="viewport"', html)

    def test_legacy_mobile_assets_keep_unified_turn_client_available(self):
        js = (FRONTEND_DIR / "mobile.js").read_text(encoding="utf-8")
        client = (FRONTEND_DIR / "turn_client.js").read_text(encoding="utf-8")
        self.assertIn("turnClient.submitAudio", js)
        self.assertIn("'/turn/audio'", client)
        self.assertIn("turn_result", js)
        self.assertIn("voice_delivery", js)
        self.assertIn("getUserMedia", js)
        self.assertIn("'/turn/audio'", client)

    def test_mobile_page_does_not_depend_on_desktop_scripts(self):
        html = (FRONTEND_DIR / "mobile.html").read_text(encoding="utf-8")
        for desktop_script in ("shell.js", "composer.js", "vad_mode.js", "voice_asr.js"):
            self.assertNotIn(desktop_script, html)

    def test_mobile_experiment_view_keeps_flex_layout(self):
        source = (FRONTEND_DIR / "mobile_cards.js").read_text(encoding="utf-8")
        self.assertIn("card.style.display = 'flex'", source)
        self.assertIn("chat.style.display = 'flex'", source)
        self.assertNotIn("card.style.display = 'block'", source)

    def test_mobile_formal_entry_hides_dev_controls_and_does_not_fallback_to_mock(self):
        html = (FRONTEND_DIR / "mobile.html").read_text(encoding="utf-8")
        source = (FRONTEND_DIR / "mobile_cards.js").read_text(encoding="utf-8")
        self.assertIn('<details class="m-dev" hidden>', html)
        self.assertIn('class="m-mock-badge" hidden', html)
        self.assertIn("new URLSearchParams(window.location.search).get('dev') === '1'", source)
        self.assertNotIn("连不上后端，已切换演示数据", source)
        self.assertIn("backendErrorCard", source)

    def test_mobile_navigation_uses_the_current_experiment_session(self):
        source = (FRONTEND_DIR / "mobile_cards.js").read_text(encoding="utf-8")
        self.assertIn("function experimentSessionIds()", source)
        self.assertIn("'/record/history'", source)
        self.assertIn("items[0].conversation_id || items[0].id", source)
        self.assertIn("title: '手机实验会话'", source)
        self.assertIn("conversation_id: ids.conversation_id", source)
        self.assertIn("lab_session_id: ids.lab_session_id", source)
        self.assertIn("'/protocols/session/steps' + query", source)
        self.assertIn("'/complete'", source)
        self.assertIn("var scopedStatuses = view.step_statuses || {}", source)
        self.assertIn("applyScopedStatus(view.step)", source)
        self.assertIn("mobileExperimentConversationId", source)
        self.assertIn("localStorage.setItem(MOBILE_CONVERSATION_KEY, id)", source)
        self.assertIn("mobileCompletedSteps:", source)
        self.assertIn("rememberCompletedStep(Number(realCard.step))", source)
        self.assertIn("applyRememberedCompletion(view.step)", source)


if __name__ == "__main__":
    unittest.main()
