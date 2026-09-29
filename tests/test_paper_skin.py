# -*- coding: utf-8 -*-
"""「纸上实验台」皮肤层（落地第一步）合同测试。

锁四个行为：
1. 皮肤只经 body.skin-paper 生效：theme.css 有该 token 重映射块，经典 :root token 原值保留（可回退）；
2. shell.js 启动按 localStorage['lab-skin'] 挂类，默认 paper，且提供切换按钮与纸纹层；
3. 老模块自动跟色的关键：皮肤块重映射 --n-00 与 --brand（模块引用变量即换血，不改 DOM）；
4. 聊天工具卡/思考卡在纸面皮肤下票面化（等宽 + 打孔虚线边 / 铅笔草稿）。
"""

import sys
import unittest
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

FRONTEND_DIR = WEB_DIR / "frontend"


class PaperSkinTokenTests(unittest.TestCase):
    def setUp(self):
        self.theme = (FRONTEND_DIR / "theme.css").read_text(encoding="utf-8")

    def test_skin_block_remaps_existing_tokens(self):
        self.assertIn("body.skin-paper {", self.theme)
        block = self.theme.split("body.skin-paper {", 1)[1]
        for token in ("--n-00:", "--brand:", "--bd-2:", "--paper:", "--ink:", "--f-kai:"):
            self.assertIn(token, block, f"皮肤块应重映射/提供 {token}")

    def test_classic_root_tokens_survive(self):
        # 经典外观的原值必须原样保留在 :root，保证一键切回
        self.assertIn("--brand: rgb(86,134,254)", self.theme)
        self.assertIn("--n-00: rgb(255,255,255)", self.theme)

    def test_canvas_gets_graph_paper_and_grain_layer_defined(self):
        self.assertIn("body.skin-paper #sh-canvas", self.theme)
        self.assertIn("body.skin-paper #paper-grain", self.theme)
        self.assertIn("feTurbulence", self.theme)

    def test_tool_and_think_cards_get_paper_identity(self):
        self.assertIn("body.skin-paper #chat .chat-tool", self.theme)
        self.assertIn("dashed", self.theme.split("body.skin-paper #chat .chat-tool", 1)[1][:400])
        self.assertIn("body.skin-paper #chat .chat-think", self.theme)


class PaperSkinBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.shell = (FRONTEND_DIR / "shell.js").read_text(encoding="utf-8")

    def test_shell_bootstraps_skin_from_localstorage_default_paper(self):
        self.assertIn("lab-skin", self.shell)
        self.assertIn("|| 'paper'", self.shell, "未设置时默认纸面皮肤")
        self.assertIn("classList.add('skin-paper')", self.shell)

    def test_shell_offers_switch_back_and_grain(self):
        self.assertIn('id="sh-skin"', self.shell)
        self.assertIn("换回经典外观", self.shell)
        self.assertIn("paper-grain", self.shell)

    def test_skin_never_touches_dom_structure_of_views(self):
        # 皮肤只挂类 + 附加纹理层，不得改写视图容器结构
        self.assertNotIn("innerHTML = ''", self.shell.split("skin", 1)[1][:600])


class PaperPageAndPolaroidTests(unittest.TestCase):
    """落地第二步：中栏纸页 + 拍立得立绘（均为纯样式覆盖，不改 DOM/逻辑）。"""

    def setUp(self):
        self.theme = (FRONTEND_DIR / "theme.css").read_text(encoding="utf-8")

    def test_canvas_becomes_a_notebook_page(self):
        block = self.theme.split("body.skin-paper #sh-canvas", 1)[1][:700]
        self.assertIn("--margin-red", block, "中栏应有红边线")
        self.assertIn("radial-gradient", block, "中栏应有装订孔")
        self.assertIn("repeat-y", block, "孔与线用背景层画，滚动时才能铺满整页")

    def test_portrait_becomes_a_taped_polaroid(self):
        self.assertIn("body.skin-paper #assistant-avatar", self.theme)
        block = self.theme.split("body.skin-paper #assistant-avatar {", 1)[1][:400]
        self.assertIn("rotate", block, "拍立得应微微倾斜")
        self.assertIn("--tape-amber", self.theme, "两角应有胶带")
        self.assertIn("paperRock", self.theme, "回答时轻摇，而非弹跳")

    def test_polaroid_is_presentation_only(self):
        avatar_js = (FRONTEND_DIR / "avatar.js").read_text(encoding="utf-8")
        for token in ("polaroid", "tape", "skin-paper"):
            self.assertNotIn(token, avatar_js, "立绘皮肤不得侵入 avatar.js 逻辑层")

    def test_instrument_numerals_and_kai_annotation(self):
        self.assertIn("--f-mono:", self.theme, "皮肤块应提供等宽字体 token")
        self.assertIn("body.skin-paper .fact", self.theme, "实体字段用仪器等宽数字")
        self.assertIn("tone-confirm .chat-block-lines", self.theme, "追问用楷体批注")


class NotebookEntryTests(unittest.TestCase):
    """记录条目：一套 DOM 两种外观（经典=干净卡片，纸面=挂红线的记录本条目）。"""

    def setUp(self):
        self.js = (FRONTEND_DIR / "record_ledger_view.js").read_text(encoding="utf-8")
        self.theme = (FRONTEND_DIR / "theme.css").read_text(encoding="utf-8")

    def test_renderer_emits_notebook_structure(self):
        for cls in ("nb-entry", "nb-ts", "nb-dot", "nb-tape", "nb-stamp", "nb-facts"):
            self.assertIn(cls, self.js, f"记录渲染器应产出 {cls}")

    def test_decorations_hidden_in_classic_skin(self):
        self.assertIn(".nb-ts, .nb-dot, .nb-tape, .nb-stamp { display: none; }", self.theme,
                      "经典外观下装饰件不得显形")
        for cls in ("body.skin-paper .nb-ts", "body.skin-paper .nb-tape",
                    "body.skin-paper .nb-stamp", "body.skin-paper .nb-dot"):
            self.assertIn(cls, self.theme, f"纸面外观应让 {cls} 显形")

    def test_timestamp_is_extracted_not_invented(self):
        # 拿不到时间就不渲染页边时间戳，不允许编造
        self.assertIn("function clockOf", self.js)
        self.assertIn("function parseLocal", self.js)
        self.assertIn("clock ? '<span class=\"nb-ts\">'", self.js)

    def test_entities_keep_original_values(self):
        # 实体仍原样输出（只改排布与字体，不改数据）
        self.assertIn("esc(item.entities[key])", self.js)
        self.assertIn("esc(item.transcript)", self.js)


class PaperReadsAsPaperTests(unittest.TestCase):
    """纸要读得出是纸：桌面明显深于纸张，且纸有边界与投影。

    事故（2026-08-30）：画布被满铺成近白纸色，没有边、影和桌面对比，
    用户看到的只是"背景发暖"，读不出"一张纸"，网格也因过淡而不可见。
    """

    def setUp(self):
        self.theme = (FRONTEND_DIR / "theme.css").read_text(encoding="utf-8")

    def _hex(self, token):
        import re
        m = re.search(re.escape(token) + r":\s*(#[0-9A-Fa-f]{6})", self.theme)
        self.assertIsNotNone(m, f"{token} 应为十六进制色值")
        h = m.group(1)
        return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))

    def test_desk_is_clearly_darker_than_page(self):
        desk = sum(self._hex("--paper")) / 3
        page = sum(self._hex("--paper-page")) / 3
        self.assertGreater(page - desk, 18,
                           f"桌面与纸张亮度差过小（桌面{desk:.0f} 纸{page:.0f}），纸读不出来")

    def test_page_has_edges_and_shadow(self):
        block = self.theme.split("body.skin-paper #sh-canvas", 1)[1][:600]
        self.assertIn("margin", block, "纸四周要留出桌面")
        self.assertIn("box-shadow", block, "纸要有投影才像纸")
        self.assertIn("border", block, "纸要有边界")
        self.assertIn("body.skin-paper #sh-center { background: var(--paper); }", self.theme,
                      "中栏应是桌面色")

    def test_grid_is_actually_visible(self):
        import re
        m = re.search(r"--grid:\s*rgba\([^)]*?,\s*\.(\d+)\)", self.theme)
        self.assertIsNotNone(m, "--grid 应为 rgba")
        alpha = float("0." + m.group(1))
        self.assertGreaterEqual(alpha, 0.08, f"网格透明度 {alpha} 过淡，屏幕上看不见")


class TicketFoldAndAttachmentTests(unittest.TestCase):
    """工具小票折叠、上传附页、会话面板默认收起。"""

    def setUp(self):
        self.theme = (FRONTEND_DIR / "theme.css").read_text(encoding="utf-8")
        self.chat = (FRONTEND_DIR / "streaming_chat_v2.js").read_text(encoding="utf-8")
        self.composer = (FRONTEND_DIR / "composer.js").read_text(encoding="utf-8")
        self.shell = (FRONTEND_DIR / "shell.js").read_text(encoding="utf-8")

    def test_ticket_collapsed_by_default(self):
        self.assertIn("#chat .chat-tool-body { display: none; }", self.theme)
        self.assertIn("#chat .chat-tool.open .chat-tool-body { display: block; }", self.theme)
        self.assertIn('class="chat-tool-head" aria-expanded="false"', self.chat)

    def test_failed_ticket_auto_expands(self):
        # 失败必须可见，不允许被折叠藏住
        self.assertIn("view.status === 'error'", self.chat)
        self.assertIn("classList.add('open')", self.chat)

    def test_ticket_head_is_a_real_button(self):
        self.assertIn('<button type="button" class="chat-tool-head"', self.chat)
        self.assertIn("setAttribute('aria-expanded'", self.chat)

    def test_upload_does_not_clobber_icon(self):
        self.assertNotIn("fileBtn.textContent", self.composer,
                         "上传中状态不得写 textContent（会顶掉 SVG 图标）")
        self.assertIn("fileBtn.classList.add('busy')", self.composer)

    def test_attachment_rendered_as_paper_slip_or_photo(self):
        self.assertIn("function addAttachment", self.composer)
        self.assertIn("attach-photo", self.composer)
        self.assertIn("attach-file", self.composer)
        self.assertIn("body.skin-paper .attach-photo::before", self.theme, "照片应贴胶带")

    def test_conversation_panel_visible_by_default(self):
        # 2026-08-30 教训：曾为"面板挡住聊天正文"把它改成默认收起，
        # 结果历史会话入口消失（用户报"看不到之前的会话了"）。
        # 正解是让两者互不遮挡，而不是藏掉功能入口。
        self.assertIn("localStorage.getItem('lab-conversation-hidden') === '1'", self.shell)

    def test_chat_body_makes_room_for_conversation_panel(self):
        self.assertIn(
            "#shell:not(.conversation-hidden) #sh-chat-main { padding-left: 236px; }",
            self.theme,
            "面板展开时聊天正文应右移让位，而不是被压在下面",
        )


class RunViewPaperTests(unittest.TestCase):
    """实验进行中（run 视图）纸面化：移液管进度、纸卡、红笔安全提示、仪器读数。"""

    def setUp(self):
        self.theme = (FRONTEND_DIR / "theme.css").read_text(encoding="utf-8")

    def test_progress_is_a_pipette(self):
        block = self.theme.split("body.skin-paper .rc-progress {", 1)[1][:300]
        self.assertIn("border", block, "移液管要有管壁")
        self.assertIn("body.skin-paper .rc-progress-bar::after", self.theme, "液面要有弯月")

    def test_step_cards_and_fields_are_paper(self):
        self.assertIn("body.skin-paper .rc-card", self.theme)
        self.assertIn("body.skin-paper .rc-kv", self.theme)
        kv = self.theme.split("body.skin-paper .rc-kv {", 1)[1][:200]
        self.assertIn("--f-mono", kv, "键值应为仪器等宽数字")

    def test_required_field_uses_highlighter(self):
        rec = self.theme.split("body.skin-paper .rc-kv.rec", 1)[1][:160]
        self.assertIn("--hl", rec, "现场必测项应用荧光笔标记")

    def test_safety_is_red_pen_and_mild_is_green(self):
        self.assertIn("body.skin-paper .rc-safe {", self.theme)
        safe = self.theme.split("body.skin-paper .rc-safe {", 1)[1][:220]
        self.assertIn("border-left", safe, "安全提示应是红笔批注式左边线")
        self.assertIn("body.skin-paper .rc-safe.mild", self.theme)


if __name__ == "__main__":
    unittest.main()
