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
        with mock.patch("api.record._build_record_service") as builder:
            with self.assertRaises(HTTPException) as caught:
                record(RecordPayload(
                    transcript="温度升到60度",
                    interaction_mode="chat", experiment_context="none",
                    mode_version=4, input_source="single_recording",
                ))
        self.assertEqual(caught.exception.status_code, 409)
        builder.assert_not_called()

    def test_chat_hides_and_hard_blocks_record_tool(self):
        names = [item["function"]["name"] for item in agent_core._tools_for_mode(InteractionMode.CHAT)]
        self.assertNotIn("record_observation", names)
        with mock.patch.object(agent_core.lab_tools, "call") as call:
            with self.assertRaises(PermissionError):
                agent_core._run_tool_with_presentation(
                    "record_observation", {"transcript": "加热"}, "c-1",
                    InteractionMode.CHAT,
                )
        call.assert_not_called()

    def test_frontend_routes_by_mode_not_input_source(self):
        recorder = (WEB / "frontend" / "voice_asr.js").read_text(encoding="utf-8")
        stream = (WEB / "frontend" / "streaming_chat_v2.js").read_text(encoding="utf-8")
        self.assertIn("submittedModeSnapshot.interaction_mode === 'chat'", recorder)
        self.assertIn("inputSource: 'single_recording'", recorder)
        self.assertIn("modeSnapshot.interaction_mode === 'experiment'", stream)
        self.assertIn("streamExperimentRecord", stream)
        self.assertIn("if (modeSnapshot.interaction_mode === 'experiment')", stream)


if __name__ == "__main__":
    unittest.main()
