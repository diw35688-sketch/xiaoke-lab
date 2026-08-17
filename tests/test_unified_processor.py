import json
import unittest

from src.core.interaction_command import InteractionCommandType
from src.core.unified_prompts import (
    UNIFIED_UNDERSTANDING_SYSTEM_PROMPT,
    build_unified_understanding_user_prompt,
)
from src.core.unified_understanding import (
    UnifiedInputKind,
    UnifiedUnderstandingInput,
)
from src.llm.client import LLMClientError, LLMGenerationResult
from src.llm.schemas import ExperimentEventType
from src.llm.unified_processor import UnifiedUnderstandingProcessor


RAW_TEXT = "我还有什么没有回答？"


class FakeLLMClient:
    def __init__(self, content=None, error=None):
        self.content = content
        self.error = error
        self.calls = []

    def generate_json(self, *, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        if self.error is not None:
            raise self.error
        return LLMGenerationResult(self.content, 2, 1.25)


def request(raw_text=RAW_TEXT):
    return UnifiedUnderstandingInput(
        raw_text=raw_text,
        session_active=True,
        session_id="session-1",
        segment_id=3,
        recent_context=("刚才记录了离心步骤。",),
        pending_question_numbers=(1, 2),
        current_question_number=2,
    )


def response(kind, branch):
    data = {
        "input_kind": kind,
        "experiment": None,
        "control": None,
        "uncertain": None,
    }
    data[kind] = branch
    return json.dumps(data, ensure_ascii=False)


class UnifiedPromptTests(unittest.TestCase):
    def test_system_prompt_defines_closed_non_executing_contract(self):
        prompt = UNIFIED_UNDERSTANDING_SYSTEM_PROMPT
        for required in (
            "experiment", "control", "uncertain", "严格互斥",
            "不执行控制命令", "execute_now", "逐字复制",
            "不可信数据", "数值也必须保留为字符串",
            "体积、浓度、温度或时间",
            "缺乏足够依据",
        ):
            self.assertIn(required, prompt)

    def test_system_prompt_keeps_answer_and_asr_error_rules(self):
        prompt = UNIFIED_UNDERSTANDING_SYSTEM_PROMPT
        for required in (
            "仅当待确认问题只有一个",
            "缺失的字段",
            "不得当作回答",
            "不得自动归属",
            "targeted_answer",
            "疑似同音错词",
            "needs_confirmation=true",
            "confirmation_reason",
        ):
            self.assertIn(required, prompt)

    def test_user_prompt_serializes_context_as_untrusted_data(self):
        prompt = build_unified_understanding_user_prompt(request())
        payload = json.loads(prompt.split("\n", 1)[1])

        self.assertEqual(payload["current_asr_raw_text"], RAW_TEXT)
        self.assertEqual(payload["pending_question_numbers"], [1, 2])
        self.assertEqual(
            payload["recent_context"],
            ["刚才记录了离心步骤。"],
        )
        self.assertNotIn("session_id", payload)
        self.assertNotIn("segment_id", payload)


class UnifiedUnderstandingInputTests(unittest.TestCase):
    def test_rejects_invalid_source_or_question_context(self):
        with self.assertRaisesRegex(ValueError, "session_id"):
            UnifiedUnderstandingInput("文本", True, " ", 1)
        with self.assertRaisesRegex(ValueError, "正整数"):
            UnifiedUnderstandingInput("文本", True, "s", 0)
        with self.assertRaisesRegex(ValueError, "必须存在"):
            UnifiedUnderstandingInput(
                "文本", True, "s", 1,
                pending_question_numbers=(1,),
                current_question_number=2,
            )


class UnifiedUnderstandingProcessorTests(unittest.TestCase):
    def test_parses_experiment_and_injects_source_identity(self):
        raw_text = "加入五毫升缓冲液。"
        analysis = {
            "events": [{
                "event_type": "operation",
                "raw_text": raw_text,
                "normalized_text": raw_text,
                "entities": {
                    "action": "加入", "object": "缓冲液",
                    "instrument": None, "amount_value": "5",
                    "amount_unit": "毫升", "concentration": None,
                    "temperature": None, "duration": None,
                    "condition": None, "observation": None,
                },
                "missing_fields": [],
                "needs_confirmation": False,
                "confirmation_reason": None,
            }],
            "should_ask_follow_up": False,
            "follow_up_question": None,
            "assistant_reply": "已记录。",
        }
        outcome = UnifiedUnderstandingProcessor(FakeLLMClient(
            response("experiment", {"analysis": analysis})
        )).understand(request(raw_text))

        self.assertFalse(outcome.degraded)
        self.assertEqual(outcome.value.input_kind, UnifiedInputKind.EXPERIMENT)
        event = outcome.value.experiment.analysis.events[0]
        self.assertEqual(event.raw_text, raw_text)
        self.assertEqual(event.source_session_id, "session-1")
        self.assertEqual(event.source_segment_id, 3)

    def test_parses_control_and_preserves_metrics(self):
        content = response("control", {"intent": {
            "status": "matched",
            "command_type": "review_pending",
            "target_question_number": None,
            "answer_text": None,
            "reason": "用户希望查看问题。",
        }})
        client = FakeLLMClient(content)

        outcome = UnifiedUnderstandingProcessor(client).understand(request())

        self.assertFalse(outcome.degraded)
        self.assertEqual(outcome.value.input_kind, UnifiedInputKind.CONTROL)
        self.assertEqual(
            outcome.value.control.intent.command_type,
            InteractionCommandType.REVIEW_PENDING,
        )
        self.assertEqual(outcome.llm_attempts, 2)
        self.assertEqual(outcome.llm_processing_seconds, 1.25)
        self.assertEqual(len(client.calls), 1)

    def test_parses_clean_uncertain_without_control_candidate(self):
        outcome = UnifiedUnderstandingProcessor(FakeLLMClient(
            response("uncertain", {"reason": "语义不足。"})
        )).understand(request("这个差不多了。"))

        self.assertFalse(outcome.degraded)
        self.assertEqual(outcome.value.input_kind, UnifiedInputKind.UNCERTAIN)
        self.assertIsNone(outcome.value.control)

    def test_invalid_output_degrades_to_note_without_control(self):
        outcome = UnifiedUnderstandingProcessor(
            FakeLLMClient("not-json")
        ).understand(request())

        self.assertTrue(outcome.degraded)
        self.assertIn("UnifiedUnderstandingError", outcome.error)
        self.assertIsNone(outcome.value.control)
        event = outcome.value.experiment.analysis.events[0]
        self.assertEqual(event.event_type, ExperimentEventType.NOTE)
        self.assertEqual(event.raw_text, RAW_TEXT)
        self.assertEqual(outcome.llm_attempts, 2)

    def test_unexpected_error_is_logged_not_printed(self):
        with self.assertLogs(
            "src.llm.unified_processor", level="ERROR"
        ) as captured:
            outcome = UnifiedUnderstandingProcessor(
                FakeLLMClient(error=RuntimeError("boom"))
            ).understand(request())

        self.assertTrue(outcome.degraded)
        self.assertIn("非契约异常", "\n".join(captured.output))

    def test_client_failure_degrades_and_keeps_failure_metrics(self):
        error = LLMClientError(
            "timeout", attempts=2, processing_seconds=3.5
        )
        outcome = UnifiedUnderstandingProcessor(
            FakeLLMClient(error=error)
        ).understand(request())

        self.assertTrue(outcome.degraded)
        self.assertIsNone(outcome.value.control)
        self.assertEqual(outcome.value.raw_text, RAW_TEXT)
        self.assertEqual(outcome.llm_attempts, 2)
        self.assertEqual(outcome.llm_processing_seconds, 3.5)


if __name__ == "__main__":
    unittest.main()
