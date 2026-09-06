# -*- coding: utf-8 -*-
"""智能体存在感（第二刀）合同测试。

锁四个行为：
1. 首页注入 agent_presence.js（defer），状态条订阅三个既有事件源，词表与立绘一致；
2. 新代码 token 纪律：agent_presence.js 零硬编码十六进制颜色，样式落在 theme.css；
3. 图标不再被字符顶掉：composer/phone_call 中不得残留 ■/◉ 写入，通话状态点亮通话按钮；
4. 语音启动自检不刷聊天流（呈现层过滤），开发指标默认对用户隐藏。
"""

import re
import sys
import unittest
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

FRONTEND_DIR = WEB_DIR / "frontend"


class AgentPresenceInjectionTests(unittest.TestCase):
    def test_presence_subscribes_existing_event_sources_only(self):
        js = (FRONTEND_DIR / "agent_presence.js").read_text(encoding="utf-8")
        self.assertIn("'avatar-state'", js)
        self.assertIn("'lab:continuous-call-state'", js)
        self.assertIn("'lab:voice-startup-progress'", js)
        self.assertNotIn("dispatchEvent", js, "状态条只订阅，不得成为新的状态源")
        self.assertNotIn("fetch(", js, "状态条不发请求，状态全部来自既有事件")

    def test_presence_vocabulary_matches_avatar(self):
        presence = (FRONTEND_DIR / "agent_presence.js").read_text(encoding="utf-8")
        avatar = (FRONTEND_DIR / "avatar.js").read_text(encoding="utf-8")
        for label in ("准备就绪", "正在聆听", "正在思考", "正在回答", "已完成", "已暂停"):
            self.assertIn(label, presence)
            self.assertIn(label, avatar)

    def test_presence_has_no_hardcoded_colors_and_styles_live_in_theme(self):
        js = (FRONTEND_DIR / "agent_presence.js").read_text(encoding="utf-8")
        self.assertEqual(
            re.findall(r"#[0-9a-fA-F]{3,6}\b", js), [],
            "新代码必须走 theme.css token，不得硬编码颜色",
        )
        self.assertNotIn("createElement('style')", js)
        theme = (FRONTEND_DIR / "theme.css").read_text(encoding="utf-8")
        self.assertIn("#agent-presence", theme)
        self.assertIn(".ap-dot", theme)


class VoiceEntryIconTests(unittest.TestCase):
    def test_glyph_clobbering_removed_from_composer_and_phone_call(self):
        for name in ("composer.js", "phone_call.js"):
            source = (FRONTEND_DIR / name).read_text(encoding="utf-8")
            self.assertNotIn("■", source, f"{name} 不得再用字符顶掉 SVG 图标")
            self.assertNotIn("◉", source, f"{name} 不得再用字符顶掉 SVG 图标")

    def test_composer_swaps_svg_icons_for_recording_state(self):
        source = (FRONTEND_DIR / "composer.js").read_text(encoding="utf-8")
        self.assertIn("stop:", source)
        self.assertIn("ICONS.stop : ICONS.mic", source)

    def test_call_state_lights_up_call_button_not_mic(self):
        source = (FRONTEND_DIR / "phone_call.js").read_text(encoding="utf-8")
        self.assertIn("$('#cp-phone-call')", source)
        # 启动期间禁用麦克风按钮（button.disabled）合法；
        # 禁止的是改写它的图标内容与 rec 样式（旧 setCallButton 的两行）。
        self.assertNotIn("mic.textContent", source)
        self.assertNotIn("mic.classList", source)


class QuietStartupAndDevMetricsTests(unittest.TestCase):
    def test_voice_startup_card_renders_only_on_failure(self):
        source = (FRONTEND_DIR / "conversation_block_view.js").read_text(encoding="utf-8")
        self.assertIn("payload.kind === 'voice_startup' && !payload.error", source)

    def test_dev_metrics_hidden_by_default(self):
        theme = (FRONTEND_DIR / "theme.css").read_text(encoding="utf-8")
        self.assertIn("#cp-meta { display: none; }", theme)
        self.assertIn("body.lab-dev-metrics #cp-meta", theme)
        composer = (FRONTEND_DIR / "composer.js").read_text(encoding="utf-8")
        self.assertIn("lab-dev-metrics", composer)


if __name__ == "__main__":
    unittest.main()
