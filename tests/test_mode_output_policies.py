import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
for path in (str(WEB), str(ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from api.record import RecordPayload, record  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from output_policy import OutputStrategy, select_output_policy  # noqa: E402
from record_service import (  # noqa: E402
    RecordCommand,
    RecordModeConflictError,
    SharedRecordService,
)
from src.core.conversation_turn import ExperimentContext, InteractionMode  # noqa: E402
import agent.core as agent_core  # noqa: E402


class ModeOutputPolicyTests(unittest.TestCase):
    def _service(self, *, step, calls):
        def mark(name, value):
            calls.append(name)
            return value

        return SharedRecordService(
            current_session_id=lambda: mark("session", "session-1"),
            next_segment_id=lambda _: mark("segment", 1),
            list_records=lambda _: [],
            extract_entities_llm=lambda *args, **kwargs: mark("llm", {
                "events": [{"entities": {"action": "加热"}, "missing_fields": ["duration"]}],
                "input_kind": "experiment", "degraded": False,
                "should_ask_follow_up": True,
                "follow_up_question": "加热了多长时间？",
            }),
            extract_entities_rule=lambda *_: SimpleNamespace(action=None),
            current_terms=lambda: (),
            evaluate=lambda _: mark("evaluate", {
                "missing_fields": ["temperature"],
                "follow_up_question": "方案要求的温度是多少？",
                "follow_up_required": True, "deviations": [],
            }),
            step_view=lambda: mark("step", step),
            save_record=lambda item: mark("save", dict(item)),
            clock=lambda: datetime(2026, 8, 25, tzinfo=timezone.utc),
            request_id_factory=lambda: mark("request_id", "request-1"),
        )

    def test_pure_policy_separates_chat_free_and_protocol(self):
        chat = select_output_policy(InteractionMode.CHAT, ExperimentContext.NONE)
        free = select_output_policy(InteractionMode.EXPERIMENT, ExperimentContext.FREE)
        protocol = select_output_policy(InteractionMode.EXPERIMENT, ExperimentContext.PROTOCOL)
        self.assertEqual(chat.strategy, OutputStrategy.CHAT)
        self.assertFalse(chat.save_observation)
        self.assertEqual(free.max_follow_up_questions, 1)
        self.assertEqual(protocol.strategy, OutputStrategy.EXPERIMENT_PROTOCOL)

    def test_explicit_free_ignores_loaded_protocol_and_asks_at_most_one_question(self):
        calls = []
        service = self._service(step={"mode": "protocol", "index": 2}, calls=calls)
        result = service.record(RecordCommand(
            "加热样品", experiment_context=ExperimentContext.FREE
        ))
        self.assertNotIn("evaluate", calls)
        self.assertLess(calls.index("save"), calls.index("request_id"))
        self.assertEqual(result.saved_record["step"]["mode"], "free")
        self.assertEqual(len(result.intents), 1)
        self.assertEqual(result.intents[0].kind.value, "clarification")

    def test_protocol_without_active_protocol_fails_before_extract_or_save(self):
        calls = []
        service = self._service(step={"mode": "free"}, calls=calls)
        with self.assertRaises(RecordModeConflictError):
            service.record(RecordCommand(
                "加热样品", experiment_context=ExperimentContext.PROTOCOL
            ))
        self.assertNotIn("llm", calls)
        self.assertNotIn("save", calls)

    def test_record_endpoint_rejects_explicit_chat_without_calling_service(self):
        with mock.patch("api.turn.turn_application_service") as service:
            with self.assertRaises(HTTPException) as caught:
                record(RecordPayload(
                    transcript="温度升到60度",
                    interaction_mode="chat", experiment_context="none",
                    mode_version=4, input_source="single_recording",
                ))
        self.assertEqual(caught.exception.status_code, 409)
        service.submit.assert_not_called()

    def test_record_tool_available_in_all_modes_but_endpoint_blocks_chat(self):
        # 架构演进：所有工具对所有模式开放，模型自己决定调什么。
        # 记录端点仍按交互模式拦截（见 test_record_endpoint_rejects_explicit_chat）。
        chat_tools = agent_core._tools_for_mode(InteractionMode.CHAT)
        exp_tools = agent_core._tools_for_mode(InteractionMode.EXPERIMENT)
        chat_names = {item["function"]["name"] for item in chat_tools}
        exp_names = {item["function"]["name"] for item in exp_tools}
        self.assertEqual(chat_names, exp_names, "所有模式应共享同一套工具")

    def test_frontend_routes_by_mode_not_input_source(self):
        recorder = (WEB / "frontend" / "voice_asr.js").read_text(encoding="utf-8")
        stream = (WEB / "frontend" / "streaming_chat_v2.js").read_text(encoding="utf-8")
        self.assertIn("single_recording", recorder)
        self.assertIn("modeSnapshot", recorder)
        self.assertIn("interaction_mode === 'experiment'", stream)
        self.assertIn("streamExperimentRecord", stream)


if __name__ == "__main__":
    unittest.main()
