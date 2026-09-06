# -*- coding: utf-8 -*-
"""整页美化第一步（视觉底子 + 侧栏翻新）合同测试。

锁三个行为：
1. 外壳图标单语言：shell.js 不再出现几何字符/emoji 图标，导航与铃铛全部为 SVG 细线图标；
2. 品牌统一：侧栏与浏览器标签页统一为「小科 · 实验助手」；
3. 视觉 token 底子：theme.css 提供字体栈/三档阴影/大圆角 token 与 14px 正文基准。
"""

import sys
import unittest
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

FRONTEND_DIR = WEB_DIR / "frontend"


class ShellIconLanguageTests(unittest.TestCase):
    def test_shell_has_no_glyph_or_emoji_icons(self):
        source = (FRONTEND_DIR / "shell.js").read_text(encoding="utf-8")
        for glyph in ("◈", "∑", "☰", "🧪", "▣", "🌐", "▤", "⚙", "🔔"):
            self.assertNotIn(glyph, source, f"shell.js 不得再用字符图标 {glyph}")

    def test_shell_nav_uses_svg_line_icons(self):
        source = (FRONTEND_DIR / "shell.js").read_text(encoding="utf-8")
        self.assertIn("viewBox=\"0 0 24 24\"", source)
        self.assertIn("stroke-width=\"1.7\"", source, "与 composer 图标同规格（1.7 细线）")
        # 8 个导航项 + 品牌徽标 + 铃铛都应有 SVG
        self.assertGreaterEqual(source.count("class=\"sh-ico\">"), 8)


class BrandUnificationTests(unittest.TestCase):
    def test_sidebar_brand_is_xiaoke(self):
        source = (FRONTEND_DIR / "shell.js").read_text(encoding="utf-8")
        self.assertIn("小科 · 实验助手", source)
        self.assertNotIn("实验语音助手", source)

    def test_page_title_is_xiaoke(self):
        html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
        self.assertIn("<title>小科 · 实验助手</title>", html)


class ThemeTokenFoundationTests(unittest.TestCase):
    def test_theme_provides_font_shadow_radius_tokens(self):
        theme = (FRONTEND_DIR / "theme.css").read_text(encoding="utf-8")
        for token in ("--font-ui:", "--sh-1:", "--sh-2:", "--sh-3:", "--r-xl:"):
            self.assertIn(token, theme)
        self.assertIn("--fs-md: 14px", theme, "中文正文基准提升到 14px")

    def test_shell_consumes_font_token(self):
        source = (FRONTEND_DIR / "shell.js").read_text(encoding="utf-8")
        # 允许带字面量兜底（var(--font-ui, ...)）：theme.css 缓存旧版/加载失败时外壳仍可读，
        # 这是 2026-08-30 皮肤事故后加的防线，不算违反 token 纪律。
        self.assertIn("font-family:var(--font-ui", source)


if __name__ == "__main__":
    unittest.main()
