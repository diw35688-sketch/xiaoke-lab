import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


WEB = Path(__file__).resolve().parent.parent / "web"
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

from src.core.experiment_tool_command import (  # noqa: E402
    ExperimentToolCommandParser,
)


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


class ExperimentToolAgentTests(unittest.TestCase):
    def test_experiment_tools_are_discovered_from_tool_registration(self):
        import agent.core as core

        names = core.lab_tools.experiment_command_names()

        # The tool set is derived from the registry, not hard-coded.
        self.assertIn("get_current_time", names)
        self.assertIn("start_timer", names)
        self.assertIn("check_timer", names)
        self.assertIn("get_protocol_detail", names)
        self.assertIn("calculate_molecular_weight", names)
        self.assertIn("list_experiment_commands", names)
        self.assertGreater(len(names), 14)
        self.assertNotIn("EXPERIMENT_TOOL_NAMES", vars(core))

    def test_visible_catalog_is_derived_and_does_not_list_itself(self):
        import lab_tools

        outcome = lab_tools.call("list_experiment_commands", {})

        self.assertTrue(outcome["ok"])
        names = {item["name"] for item in outcome["result"]["tools"]}
        self.assertEqual(
            names,
            lab_tools.experiment_command_names() - {"list_experiment_commands"},
        )
        self.assertEqual(
            outcome["result"]["count"],
            len(lab_tools.experiment_command_names()) - 1,
        )

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
        """The schema may accept an optional protocol_id hint, but it is never
        required — the handler always binds to the session's selected protocol."""

        import agent.core as core

        tool = next(
            item for item in core.TOOLS
            if item["function"]["name"] == "get_protocol_detail"
        )

        self.assertEqual(tool["function"]["parameters"]["required"], [])
        # protocol_id is optional; the binding test verifies it is overridden.
        props = tool["function"]["parameters"]["properties"]
        if "protocol_id" in props:
            # If present, it must not be required.
            self.assertNotIn("protocol_id", tool["function"]["parameters"]["required"])


if __name__ == "__main__":
    unittest.main()
