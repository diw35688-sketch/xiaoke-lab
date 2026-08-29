import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


WEB = Path(__file__).resolve().parent.parent / "web"
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

from agent.core import ExperimentToolAgentResult  # noqa: E402
from src.core.conversation_turn import (  # noqa: E402
    BlockType,
    ExperimentContext,
    InputSource,
    InteractionMode,
)
from src.core.experiment_tool_command import (  # noqa: E402
    ExperimentToolCommandParser,
)
from src.core.turn_input import TurnInput  # noqa: E402
from src.core.turn_timing import TurnTimingRecorder  # noqa: E402
from turn_processors import ExperimentProcessor  # noqa: E402


class ExperimentToolCommandParserTests(unittest.TestCase):
    def test_sentence_initial_address_extracts_command(self):
        parsed = ExperimentToolCommandParser.parse("小科小科，帮我计时10分钟。😔")

        self.assertTrue(parsed.matched)
        self.assertEqual(parsed.raw_text, "小科小科，帮我计时10分钟。😔")
        self.assertEqual(parsed.command_text, "帮我计时10分钟。")

    def test_normal_experiment_fact_does_not_enter_tool_route(self):
        parsed = ExperimentToolCommandParser.parse("继续加热10分钟")

        self.assertFalse(parsed.matched)
        self.assertIsNone(parsed.command_text)

    def test_empty_address_is_not_a_tool_command(self):
        self.assertFalse(ExperimentToolCommandParser.parse("小科。😊").matched)


class _StoreMustNotLoad:
    def load_experiment_state(self, conversation_id, lab_session_id):
        raise AssertionError("实验工具指令不应载入或修改实验记录状态")


class ExperimentToolTurnTests(unittest.TestCase):
    def test_addressed_tool_returns_cards_without_lab_record(self):
        calls = []

        def runner(command_text, conversation_id, lab_session_id):
            calls.append((command_text, conversation_id, lab_session_id))
            return ExperimentToolAgentResult(
                answer="已开始计时10分钟。",
                tool_views=({
                    "card": "generic",
                    "kind": "execute",
                    "title": "启动计时器",
                    "status": "done",
                    "lines": ["计时器已启动：600秒后结束"],
                    "tool_call_id": "call-1",
                },),
                called_tools=("start_timer",),
            )

        processor = ExperimentProcessor(
            _StoreMustNotLoad(), tool_runner=runner
        )
        turn = TurnInput(
            "conversation-1", "request-1", "turn-1", "lab-1",
            InteractionMode.EXPERIMENT, ExperimentContext.FREE, 1,
            InputSource.TEXT, "小科，帮我计时10分钟",
        )

        prepared = processor.prepare(turn, TurnTimingRecorder())

        self.assertEqual(
            calls, [("帮我计时10分钟", "conversation-1", "lab-1")]
        )
        self.assertEqual(prepared.business["kind"], "experiment_tool")
        self.assertEqual(prepared.business["called_tools"], ["start_timer"])
        self.assertIsNone(prepared.lab_record)
        self.assertEqual(prepared.experiment_events, ())
        self.assertIsNone(prepared.session_state)
        self.assertEqual(
            [block.type for block in prepared.turn.blocks],
            [
                BlockType.USER_TEXT,
                BlockType.TOOL_CARD,
                BlockType.ASSISTANT_TEXT,
                BlockType.VOICE,
            ],
        )
        self.assertEqual(prepared.voice_items[0].voice_text, "已开始计时10分钟。")


class ExperimentToolAgentTests(unittest.TestCase):
    def test_experiment_tools_are_discovered_from_tool_registration(self):
        import agent.core as core

        names = core.lab_tools.experiment_command_names()

        self.assertEqual(
            names,
            {
                "get_current_time", "start_timer", "check_timer",
                "get_current_step", "list_experiment_commands",
                "check_reagent_safety", "get_protocol_detail",
                "get_protocol_prep_requirements", "list_reagent_preps",
                "get_reagent_prep", "calculate_molecular_weight",
                "calculate_solution_prep", "calculate_dilution",
            },
        )
        self.assertEqual(
            {tool["function"]["name"] for tool in core._experiment_tools()},
            names,
        )
        self.assertNotIn("EXPERIMENT_TOOL_NAMES", vars(core))

    def test_standard_tool_call_loop_uses_only_experiment_allowlist(self):
        import agent.core as core

        requests = []
        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(
                name="start_timer",
                arguments='{"duration_seconds":600,"label":"水浴"}',
            ),
        )
        responses = iter([
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                content=None, tool_calls=[tool_call]
            ))]),
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                content="已开始计时10分钟。", tool_calls=[]
            ))]),
        ])

        class _Completions:
            def create(self, **kwargs):
                requests.append(kwargs)
                return next(responses)

        client = SimpleNamespace(
            chat=SimpleNamespace(completions=_Completions())
        )
        result_payload = {
            "timer_id": "timer-1",
            "label": "水浴",
            "duration_seconds": 600,
        }
        with mock.patch("agent.core._client", return_value=client), \
             mock.patch(
                 "agent.core.lab_tools.call",
                 return_value={"ok": True, "result": result_payload},
             ):
            result = core.run_experiment_tool_agent(
                "帮我计时10分钟", "conversation-1", "lab-1"
            )

        self.assertEqual(result.answer, "已开始计时10分钟。")
        self.assertEqual(result.called_tools, ("start_timer",))
        self.assertEqual(result.tool_views[0]["status"], "done")
        self.assertEqual(
            {tool["function"]["name"] for tool in requests[0]["tools"]},
            {
                "get_current_time", "start_timer", "check_timer",
                "get_current_step", "list_experiment_commands",
                "check_reagent_safety", "get_protocol_detail",
                "get_protocol_prep_requirements", "list_reagent_preps",
                "get_reagent_prep", "calculate_molecular_weight",
                "calculate_solution_prep", "calculate_dilution",
            },
        )
        check_timer = next(
            tool for tool in requests[0]["tools"]
            if tool["function"]["name"] == "check_timer"
        )
        self.assertEqual(
            check_timer["function"]["parameters"]["properties"], {}
        )
        self.assertEqual(requests[1]["messages"][-1]["role"], "tool")

    def test_visible_catalog_is_derived_and_does_not_list_itself(self):
        import lab_tools

        outcome = lab_tools.call("list_experiment_commands", {})

        self.assertTrue(outcome["ok"])
        names = {item["name"] for item in outcome["result"]["tools"]}
        self.assertEqual(
            names,
            lab_tools.experiment_command_names() - {"list_experiment_commands"},
        )
        self.assertEqual(outcome["result"]["count"], 12)

    def test_capability_question_uses_local_catalog_tool(self):
        import agent.core as core

        with mock.patch(
            "agent.core._client",
            side_effect=AssertionError("能力清单不应依赖模型"),
        ):
            result = core.run_experiment_tool_agent(
                "你现在能做什么？", "conversation-1", "lab-1"
            )

        self.assertEqual(result.called_tools, ("list_experiment_commands",))
        self.assertEqual(result.tool_views[0]["status"], "done")
        self.assertIn("查看当前步骤", result.answer)
        self.assertIn("启动计时器", result.answer)

    def test_timer_lookup_uses_latest_timer_from_same_conversation(self):
        import agent.core as core

        calls = []

        def fake_call(name, args):
            calls.append((name, dict(args)))
            if name == "start_timer":
                return {"ok": True, "result": {
                    "timer_id": "timer-c1", "label": "", "duration_seconds": 60,
                }}
            return {"ok": True, "result": {
                "found": True, "timer_id": args["timer_id"],
            }}

        with mock.patch("agent.core.lab_tools.call", side_effect=fake_call):
            core._execute_experiment_tool(
                "start_timer", {"duration_seconds": 60},
                "conversation-c1", "lab-1",
            )
            result = core._execute_experiment_tool(
                "check_timer", {}, "conversation-c1", "lab-1"
            )

        self.assertEqual(result["timer_id"], "timer-c1")
        self.assertEqual(calls[-1], ("check_timer", {"timer_id": "timer-c1"}))

    def test_timer_reference_is_isolated_by_lab_session(self):
        import agent.core as core

        with core._latest_experiment_timer_lock:
            core._latest_experiment_timer.pop(("conversation-shared", "lab-2"), None)
            core._latest_experiment_timer[("conversation-shared", "lab-1")] = "timer-lab-1"

        result = core._execute_experiment_tool(
            "check_timer", {}, "conversation-shared", "lab-2"
        )

        self.assertFalse(result["found"])
        self.assertIn("还没有启动计时器", result["message"])

    def test_current_step_is_read_only_and_uses_registered_tool(self):
        import agent.core as core

        step = {
            "mode": "protocol",
            "protocol": {"title": "PCR", "total_steps": 4},
            "step": {"number": 2, "title": "扩增", "must_record": ["temperature"]},
            "progress": {
                "status": "in_progress",
                "recorded": [],
                "missing": ["temperature"],
            },
            "safety": [],
        }
        with mock.patch(
            "agent.core.lab_tools.call",
            return_value={"ok": True, "result": step},
        ) as call:
            result = core._execute_experiment_tool(
                "get_current_step", {}, "conversation-1", "lab-1"
            )

        self.assertEqual(result, step)
        call.assert_called_once_with("get_current_step", {})

    def test_protocol_detail_is_bound_to_current_selected_protocol(self):
        import agent.core as core

        selected = SimpleNamespace(
            selection=SimpleNamespace(
                protocol=SimpleNamespace(protocol_id="protocol-current")
            )
        )
        detail = {"protocol": {"title": "当前方案"}, "steps": []}
        with mock.patch(
            "agent.core.lab_tools.domain.session", return_value=selected
        ), mock.patch(
            "agent.core.lab_tools.call",
            return_value={"ok": True, "result": detail},
        ) as call:
            result = core._execute_experiment_tool(
                "get_protocol_detail", {"protocol_id": "model-guessed"},
                "conversation-1", "lab-1",
            )

        self.assertEqual(result, detail)
        call.assert_called_once_with(
            "get_protocol_detail", {"protocol_id": "protocol-current"}
        )

    def test_protocol_detail_schema_does_not_ask_model_for_protocol_id(self):
        import agent.core as core

        tool = next(
            item for item in core._experiment_tools()
            if item["function"]["name"] == "get_protocol_detail"
        )

        self.assertEqual(tool["function"]["parameters"]["properties"], {})
        self.assertEqual(tool["function"]["parameters"]["required"], [])


if __name__ == "__main__":
    unittest.main()
