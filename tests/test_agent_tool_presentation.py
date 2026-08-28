import importlib
import json
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from src.core.presentation_delivery import build_delivery_plan  # noqa: E402
from src.core.presentation_intent import (  # noqa: E402
    MessageKind,
    MessagePriority,
    PresentationIntent,
    ScreenTarget,
)
from tool_presentation import ToolVoiceDeliveryBatch  # noqa: E402


def _stub_module(name, **attributes):
    module = ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def _import_agent_core():
    service_error = type("ServiceError", (Exception,), {})
    stubs = {
        "httpx": _stub_module("httpx", Timeout=Mock),
        "openai": _stub_module(
            "openai",
            APIConnectionError=service_error,
            APIStatusError=service_error,
            APITimeoutError=service_error,
            OpenAI=Mock,
        ),
        "settings_store": _stub_module(
            "settings_store",
            current=lambda: SimpleNamespace(
                api_key="test", base_url="test", model_name="test",
                voice_disable_thinking=False,
            ),
        ),
        "database.crud": _stub_module(
            "database.crud", list_memories=lambda: []
        ),
        "tools.calculator": _stub_module(
            "tools.calculator", calculate=lambda value: value
        ),
        "tools.experiment_tools": _stub_module(
            "tools.experiment_tools",
            check_experiment_conflicts=Mock(),
            confirm_pending_experiment=Mock(),
            list_current_experiments=Mock(),
            propose_experiment=Mock(),
        ),
        "tools.memory_tools": _stub_module(
            "tools.memory_tools",
            confirm_pending_memory=Mock(),
            propose_memory=Mock(),
        ),
    }
    sys.modules.pop("agent.core", None)
    with patch.dict(sys.modules, stubs):
        return importlib.import_module("agent.core")


def _plan():
    intent = PresentationIntent(
        intent_id="ask-1",
        kind=MessageKind.CLARIFICATION,
        args={"question": "加热了多长时间？"},
        priority=MessagePriority.ACTIVE_QUESTION,
        screen_target=ScreenTarget.CURRENT_QUESTION,
        source_segment_id=3,
    )
    return build_delivery_plan((intent,), ui_mode="user")


def _silent_plan():
    intent = PresentationIntent(
        intent_id="ack-1",
        kind=MessageKind.RECORD_ACK,
        args={"result": "recorded_no_step"},
        priority=MessagePriority.ROUTINE,
        screen_target=ScreenTarget.RECORD_TIMELINE,
        source_segment_id=3,
    )
    return build_delivery_plan((intent,), ui_mode="user")


class AgentToolPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = _import_agent_core()

    def test_legacy_run_tool_keeps_plain_result_contract(self):
        outcome = {
            "ok": True,
            "result": {"transcript": "加热到60摄氏度"},
            "presentation_plan": _plan(),
        }
        with patch.object(self.core.lab_tools, "names", return_value=["record_observation"]), patch.object(
            self.core.lab_tools, "call", return_value=outcome
        ):
            result = self.core.run_tool(
                "record_observation", {"transcript": "加热到60摄氏度"}, "c-1"
            )

        self.assertEqual(result, outcome["result"])

    def test_run_agent_returns_copy_text_without_second_model_call(self):
        call = SimpleNamespace(
            id="tool-1",
            function=SimpleNamespace(
                name="record_observation",
                arguments=json.dumps({"transcript": "加热到60摄氏度"}),
            ),
        )
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[call]))]
        )
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=Mock(return_value=response))
            )
        )
        with patch.object(self.core, "_client", return_value=client), patch.object(
            self.core,
            "_run_tool_with_presentation",
            return_value=({"transcript": "加热到60摄氏度"}, _plan()),
        ):
            reply = self.core.run_agent([], "c-1")

        self.assertEqual(reply, "小科：加热了多长时间？")
        self.assertEqual(client.chat.completions.create.call_count, 1)

    def test_stream_agent_yields_copy_text_and_stops_before_model_rewrite(self):
        partial = SimpleNamespace(
            index=0,
            id="tool-1",
            function=SimpleNamespace(
                name="record_observation",
                arguments=json.dumps({"transcript": "加热到60摄氏度"}),
            ),
        )
        delta = SimpleNamespace(
            content=None, reasoning_content=None, tool_calls=[partial]
        )
        stream = [SimpleNamespace(choices=[SimpleNamespace(delta=delta)])]
        create = Mock(return_value=stream)
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )
        with patch.object(self.core, "_client", return_value=client), patch.object(
            self.core.lab_tools, "names", return_value=["record_observation"]
        ), patch.object(
            self.core,
            "_run_tool_with_presentation",
            return_value=({"transcript": "加热到60摄氏度"}, _plan()),
        ):
            chunks = list(self.core.stream_agent([], "c-1"))

        self.assertIn("小科：加热了多长时间？", chunks)
        voice_batch = next(
            chunk for chunk in chunks
            if isinstance(chunk, ToolVoiceDeliveryBatch)
        )
        self.assertEqual(voice_batch.items[0].intent_id, "ask-1")
        self.assertEqual(voice_batch.items[0].voice_text, "加热了多长时间？")
        self.assertEqual(create.call_count, 1)

    def test_run_agent_executes_all_same_turn_tools_before_replying(self):
        calls = [
            SimpleNamespace(
                id="tool-1",
                function=SimpleNamespace(
                    name="record_observation", arguments='{"transcript":"记录"}'
                ),
            ),
            SimpleNamespace(
                id="tool-2",
                function=SimpleNamespace(name="get_current_time", arguments="{}"),
            ),
        ]
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=calls))]
        )
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=Mock(return_value=response))
            )
        )
        executed = []

        def execute(name, args, conversation_id):
            executed.append(name)
            return ({"ok": True}, _plan() if name == "record_observation" else None)

        with patch.object(self.core, "_client", return_value=client), patch.object(
            self.core, "_run_tool_with_presentation", side_effect=execute
        ):
            reply = self.core.run_agent([], "c-1")

        self.assertEqual(executed, ["record_observation", "get_current_time"])
        self.assertEqual(reply, "小科：加热了多长时间？")
        self.assertEqual(client.chat.completions.create.call_count, 1)

    def test_stream_agent_does_not_emit_empty_voice_delivery(self):
        partial = SimpleNamespace(
            index=0,
            id="tool-1",
            function=SimpleNamespace(
                name="record_observation", arguments='{"transcript":"记录"}'
            ),
        )
        delta = SimpleNamespace(
            content=None, reasoning_content=None, tool_calls=[partial]
        )
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=Mock(
                        return_value=[
                            SimpleNamespace(
                                choices=[SimpleNamespace(delta=delta)]
                            )
                        ]
                    )
                )
            )
        )
        with patch.object(self.core, "_client", return_value=client), patch.object(
            self.core.lab_tools, "names", return_value=["record_observation"]
        ), patch.object(
            self.core,
            "_run_tool_with_presentation",
            return_value=({"transcript": "记录"}, _silent_plan()),
        ):
            chunks = list(self.core.stream_agent([], "c-1"))

        self.assertIn("本段结构化处理失败，原始记录已保存。", chunks)
        self.assertFalse(
            any(isinstance(chunk, ToolVoiceDeliveryBatch) for chunk in chunks)
        )


if __name__ == "__main__":
    unittest.main()
