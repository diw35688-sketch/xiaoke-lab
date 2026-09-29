import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "web" / "frontend"
APP = ROOT / "web" / "app.py"
AGENT_CORE = ROOT / "web" / "agent" / "core.py"


class ConversationTurnStoreFrontendTests(unittest.TestCase):
    def test_store_loads_before_stream_consumer(self):
        source = APP.read_text(encoding="utf-8")
        self.assertLess(
            source.index("conversation_turn_store.js"),
            source.index("streaming_chat_v2.js"),
        )

    def test_stream_writes_think_and_tool_only_to_one_store(self):
        source = (FRONTEND / "streaming_chat_v2.js").read_text(encoding="utf-8")
        self.assertIn("turnStore.pushThink(", source)
        self.assertIn("turnStore.pushTool(view)", source)
        for legacy in (
            "chatPushThink", "runPushThink", "chatPushTool",
            "runPushTool", "labToolCard",
        ):
            with self.subTest(legacy=legacy):
                self.assertNotIn(legacy, source)

    def test_server_text_events_become_assistant_blocks_before_rendering(self):
        source = (FRONTEND / "streaming_chat_v2.js").read_text(encoding="utf-8")
        self.assertIn("type: 'assistant_text'", source)
        self.assertIn("publishAnswer(answer)", source)
        self.assertIn("block.type === 'assistant_text'", source)
        screen_start = source.index("data.type === 'screen_delta'")
        delta_start = source.index("data.type === 'delta'", screen_start)
        screen_branch = source[screen_start:delta_start]
        self.assertNotIn("reply.textContent", screen_branch)

    def test_run_canvas_no_longer_owns_realtime_think_or_tool_state(self):
        source = (FRONTEND / "run_canvas.js").read_text(encoding="utf-8")
        # run_canvas 不再拥有流式状态（stream 变量、pending 索引、think/stream 推送）。
        # runPushTool 保留为渲染回调——它只接收已构建好的 artifact view 并渲染，
        # 不积累 streaming delta，不属于"拥有状态"。
        for removed in ("var stream =", "pendingIndex", "runPushThink", "runClearStream"):
            with self.subTest(removed=removed):
                self.assertNotIn(removed, source)
        self.assertIn("stepsHtml() + stepCardHtml()", source)

    def test_old_tool_forwarder_is_not_loaded(self):
        source = APP.read_text(encoding="utf-8")
        self.assertNotIn("/static/tool_cards.js", source)

    def test_store_has_no_business_side_effect_api(self):
        source = (FRONTEND / "conversation_turn_store.js").read_text(encoding="utf-8")
        for forbidden in ("fetch(", "/record", "executeTool", "enqueueSpeech", "window.speak"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_tool_cards_receive_stable_server_call_identity(self):
        source = AGENT_CORE.read_text(encoding="utf-8")
        self.assertIn('call_view["tool_call_id"] = call["id"]', source)
        self.assertIn('result_view["tool_call_id"] = call["id"]', source)


if __name__ == "__main__":
    unittest.main()
