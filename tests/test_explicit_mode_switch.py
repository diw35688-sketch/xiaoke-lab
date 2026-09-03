import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
FRONTEND = WEB / "frontend"
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mode_snapshot import ModeSnapshotFields  # noqa: E402


class ExplicitModeSwitchTests(unittest.TestCase):
    def test_server_accepts_three_explicit_modes(self):
        cases = (
            ("chat", "none"),
            ("experiment", "free"),
            ("experiment", "protocol"),
        )
        for mode, context in cases:
            with self.subTest(mode=mode, context=context):
                request = ModeSnapshotFields(
                    interaction_mode=mode,
                    experiment_context=context,
                    mode_version=7,
                    input_source="continuous_call",
                )
                self.assertEqual(request.mode_snapshot()["mode_version"], 7)

    def test_server_rejects_crossed_mode_context(self):
        with self.assertRaises(ValueError):
            ModeSnapshotFields(interaction_mode="chat", experiment_context="free")
        with self.assertRaises(ValueError):
            ModeSnapshotFields(interaction_mode="experiment", experiment_context="none")

    def test_request_and_turn_identity_must_arrive_together(self):
        with self.assertRaises(ValueError):
            ModeSnapshotFields(request_id="request-only")

    def test_chat_and_record_payloads_inherit_shared_validator(self):
        chat = (WEB / "api" / "chat.py").read_text(encoding="utf-8")
        record = (WEB / "api" / "record.py").read_text(encoding="utf-8")
        self.assertIn("class ChatRequest(ModeSnapshotFields)", chat)
        self.assertIn("class RecordPayload(ModeSnapshotFields)", record)

    def test_mode_state_loads_before_all_submission_entries(self):
        source = (WEB / "app.py").read_text(encoding="utf-8")
        mode = source.index("interaction_mode_state.js")
        self.assertLess(mode, source.index("voice_asr.js"))
        self.assertLess(mode, source.index("streaming_chat_v2.js"))
        self.assertLess(mode, source.index("composer.js"))

    def test_new_chat_has_three_explicit_modes_and_captures_before_submit(self):
        source = (FRONTEND / "streaming_chat_v2.js").read_text(encoding="utf-8")
        for name in ("chat", "free", "protocol"):
            self.assertIn(f'data-mode="{name}"', source)
        self.assertIn("window.selectComposerMode('chat')", source)
        self.assertIn("window.selectComposerMode('free')", source)
        protocol_branch = source[
            source.index("if (mode === 'protocol')"):
            source.index("if (mode === 'template')")
        ]
        self.assertIn("window.shellShow('protocols')", protocol_branch)
        self.assertNotIn("selectComposerMode", protocol_branch)
        self.assertEqual(source.count('data-mode="template"'), 1)
        template_branch = source[
            source.index("if (mode === 'template')"):
            source.index("if (mode === 'storage')")
        ]
        self.assertIn("interactionModeState.select('template')", template_branch)
        self.assertIn("showIntro", template_branch)
        self.assertNotIn("shellShow('protocols')", template_branch)
        self.assertIn("AI制作方案/配方", source)
        self.assertIn("可上传文本文件，PDF或图片请到方案页导入", source)
        self.assertIn("方案实验", source)
        composer = (FRONTEND / "composer.js").read_text(encoding="utf-8")
        self.assertIn("captureComposerModeSnapshot", composer)
        self.assertLess(
            composer.index("captureComposerModeSnapshot"),
            composer.index("form.requestSubmit"),
        )

    def test_protocol_mode_requires_a_selected_server_protocol(self):
        composer = (FRONTEND / "composer.js").read_text(encoding="utf-8")
        views = (FRONTEND / "views.js").read_text(encoding="utf-8")
        self.assertIn("fetch('/protocols/session')", composer)
        self.assertIn("session.mode !== 'protocol' || !session.protocol", composer)
        self.assertLess(
            composer.index("session.mode !== 'protocol' || !session.protocol"),
            composer.index("interactionModeState.select('protocol', session.protocol.id)"),
        )
        self.assertIn("window.shellShow('protocols')", composer)
        self.assertIn(
            "interactionModeState.select(id ? 'protocol' : 'free', id || null)",
            views,
        )
        self.assertIn("window.shellShow('chat')", views)

    def test_free_mode_clears_server_protocol_before_switching_frontend(self):
        composer = (FRONTEND / "composer.js").read_text(encoding="utf-8")
        free_branch = composer[
            composer.index("if (mode === 'free')"):
            composer.index("if (mode !== 'protocol')")
        ]
        self.assertIn("fetch('/protocols/session'", free_branch)
        self.assertIn("protocol_id: null", free_branch)
        self.assertIn("session.mode !== 'free'", free_branch)
        self.assertLess(
            free_branch.index("session.mode !== 'free'"),
            free_branch.index("interactionModeState.select('free')"),
        )

    def test_agent_protocol_tool_switches_mode_before_navigating(self):
        tools = (WEB / "lab_tools.py").read_text(encoding="utf-8")
        shell = (FRONTEND / "shell.js").read_text(encoding="utf-8")
        state = (FRONTEND / "interaction_mode_state.js").read_text(
            encoding="utf-8"
        )
        stream = (FRONTEND / "streaming_chat_v2.js").read_text(
            encoding="utf-8"
        )
        select_tool = tools[
            tools.index("def _select_protocol"):
            tools.index("def _create_reagent_prep", tools.index("def _select_protocol"))
        ]
        self.assertIn('"type": "switch_interaction_mode"', select_tool)
        self.assertIn('"mode": "free"', select_tool)
        self.assertIn('"mode": "protocol"', select_tool)
        self.assertIn('"protocol_id": result["protocol"]["id"]', select_tool)
        self.assertIn("window.applyInteractionModeUiAction(action)", shell)
        switch_branch = shell[
            shell.index("if (action.type === 'switch_interaction_mode')"):
            shell.index("if (action.type === 'navigate'")
        ]
        self.assertLess(
            switch_branch.index("applyInteractionModeUiAction"),
            switch_branch.index("show(action.view || 'run')"),
        )
        self.assertIn("window.interactionModeState.select(", state)
        tool_branch_start = stream.index(
            "} else if (block.type === 'tool_card') {"
        )
        tool_branch = stream[
            tool_branch_start:
            stream.index(
                "} else if (block.type === 'assistant_text'", tool_branch_start
            )
        ]
        self.assertNotIn("&& activeReply", tool_branch)
        self.assertIn("window.appApplyUiAction(action)", tool_branch)

    def test_chat_store_and_request_share_one_frozen_snapshot(self):
        source = (FRONTEND / "streaming_chat_v2.js").read_text(encoding="utf-8")
        self.assertIn("consumeComposerModeSnapshot(form, 'text')", source)
        self.assertGreaterEqual(source.count("...modeSnapshot"), 2)
        self.assertNotIn("interaction_mode: 'chat'", source)

    def test_composer_labels_chat_and_free_experiment_separately(self):
        source = (FRONTEND / "composer.js").read_text(encoding="utf-8")

        self.assertIn("snapshot.interaction_mode === 'chat'", source)
        self.assertIn("return '自由聊天'", source)
        self.assertIn("snapshot.experiment_context === 'free'", source)
        self.assertIn("return '自由实验记录'", source)
        self.assertNotIn(": '自由记录') + '<span", source)

    def test_header_status_labels_chat_and_free_experiment_separately(self):
        views = (FRONTEND / "views.js").read_text(encoding="utf-8")
        shell = (FRONTEND / "shell.js").read_text(encoding="utf-8")

        status_start = views.index("function interactionStatusLabel")
        status_end = views.index("window.interactionStatusLabel", status_start)
        status = views[status_start:status_end]
        self.assertIn("snapshot.interaction_mode === 'chat'", status)
        self.assertIn("return '自由聊天'", status)
        self.assertIn("snapshot.experiment_context === 'free'", status)
        self.assertIn("return '自由实验记录'", status)
        self.assertNotIn("自由记录模式", status)
        self.assertIn("window.shellRefreshStatus()", shell)

    def test_recording_and_call_are_only_input_sources(self):
        recorder = (FRONTEND / "voice_asr.js").read_text(encoding="utf-8")
        call = (FRONTEND / "phone_call.js").read_text(encoding="utf-8")
        context = (FRONTEND / "conversation_context_blocks.js").read_text(encoding="utf-8")
        self.assertIn("capture('single_recording')", recorder)
        self.assertIn("...modeSnapshot", recorder)
        self.assertIn("inputSource: 'continuous_call'", call)
        self.assertNotIn("session.mode === 'protocol'", context)

    def test_experiment_record_request_carries_the_turn_identity(self):
        chat = (FRONTEND / "streaming_chat_v2.js").read_text(encoding="utf-8")
        experiment_branch = chat[
            chat.index("if (modeSnapshot.interaction_mode === 'experiment')"):
            chat.index("const response = await fetch('/chat/stream'")
        ]
        self.assertIn("request_id: localRequestId", experiment_branch)
        self.assertIn("turn_id: localTurnId", experiment_branch)


if __name__ == "__main__":
    unittest.main()
