# -*- coding: utf-8 -*-
"""web/llm_bridge.py 统一链桥接的单测：不依赖网络与真实设置。

覆盖：experiment 分支（实体卡片透传）、control 分支（只带标签）、
uncertain 分支（只带标签）、模型失败降级（NOTE 卡片 + degraded）、
非法 JSON 降级、recent_context 空白过滤与透传。
"""

import json
import sys
import unittest
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

import llm_bridge  # noqa: E402
from src.llm.client import LLMClientError, LLMGenerationResult  # noqa: E402
from src.llm.unified_processor import UnifiedUnderstandingProcessor  # noqa: E402


def _response(kind, branch):
    data = {
        "input_kind": kind,
        "experiment": None,
        "control": None,
        "uncertain": None,
    }
    data[kind] = branch
    return json.dumps(data, ensure_ascii=False)


EXPERIMENT_BRANCH = {
    "analysis": {
        "events": [{
            "event_type": "operation",
            "raw_text": "加入五毫升缓冲液。",
            "normalized_text": "加入五毫升缓冲液。",
            "entities": {
                "action": "加入", "object": "缓冲液", "instrument": None,
                "amount_value": "5", "amount_unit": "毫升", "concentration": None,
                "temperature": None, "duration": None, "condition": None,
                "observation": None,
            },
            "missing_fields": [],
            "needs_confirmation": False,
            "confirmation_reason": None,
        }],
        "should_ask_follow_up": False,
        "follow_up_question": None,
        "assistant_reply": "已记录。",
    }
}


class FakeLLMClient:
    """固定返回测试者指定的 JSON，模拟真实模型。"""

    def __init__(self, content=None, error=None):
        self.content = content
        self.error = error
        self.calls = []

    def generate_json(self, *, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        if self.error is not None:
            raise self.error
        return LLMGenerationResult(
            content=self.content,
            attempts=2,
            processing_seconds=1.25,
        )


def _install(content=None, error=None):
    llm_bridge._processor = UnifiedUnderstandingProcessor(
        FakeLLMClient(content=content, error=error)
    )
    return llm_bridge._processor._client


class WebLlmBridgeTests(unittest.TestCase):
    def setUp(self):
        llm_bridge._processor = None

    def test_experiment_branch_returns_entity_cards(self):
        _install(content=_response("experiment", EXPERIMENT_BRANCH))
        result = llm_bridge.extract(
            "加入五毫升缓冲液。", session_id="session-1", segment_id=1
        )

        self.assertFalse(result["degraded"])
        self.assertEqual(result["input_kind"], "experiment")
        self.assertEqual(len(result["events"]), 1)
        event = result["events"][0]
        self.assertEqual(event["event_type"], "operation")
        self.assertEqual(event["entities"]["action"], "加入")
        self.assertEqual(event["entities"]["amount_value"], "5")
        self.assertEqual(result["assistant_reply"], "已记录。")
        self.assertEqual(result["llm_attempts"], 2)
        self.assertEqual(result["llm_seconds"], 1.25)

    def test_control_branch_returns_label_without_cards(self):
        _install(content=_response("control", {"intent": {
            "status": "matched",
            "command_type": "review_pending",
            "target_question_number": None,
            "answer_text": None,
            "reason": "用户希望查看问题。",
        }}))
        result = llm_bridge.extract(
            "帮我看看待确认的问题", session_id="session-1", segment_id=2
        )

        self.assertFalse(result["degraded"])
        self.assertEqual(result["input_kind"], "control")
        self.assertEqual(result["events"], [])
        self.assertIsNone(result["assistant_reply"])

    def test_experiment_branch_preserves_semantic_follow_up_contract(self):
        branch = json.loads(json.dumps(EXPERIMENT_BRANCH, ensure_ascii=False))
        analysis = branch["analysis"]
        analysis["events"][0]["raw_text"] = "加热到六十摄氏度"
        analysis["events"][0]["normalized_text"] = "加热到六十摄氏度"
        analysis["events"][0]["missing_fields"] = ["duration"]
        analysis["should_ask_follow_up"] = True
        analysis["follow_up_question"] = "加热了多长时间？"
        _install(content=_response("experiment", branch))

        result = llm_bridge.extract(
            "加热到六十摄氏度", session_id="session-1", segment_id=8
        )

        self.assertEqual(result["events"][0]["missing_fields"], ["duration"])
        self.assertTrue(result["should_ask_follow_up"])
        self.assertEqual(result["follow_up_question"], "加热了多长时间？")

    def test_uncertain_branch_returns_label_without_cards(self):
        _install(content=_response("uncertain", {"reason": "语义不足。"}))
        result = llm_bridge.extract(
            "这个差不多了。", session_id="session-1", segment_id=3
        )

        self.assertFalse(result["degraded"])
        self.assertEqual(result["input_kind"], "uncertain")
        self.assertEqual(result["events"], [])

    def test_client_failure_degrades_to_note_card(self):
        error = LLMClientError("timeout", attempts=2, processing_seconds=3.5)
        _install(error=error)
        result = llm_bridge.extract(
            "加热到六十度", session_id="session-1", segment_id=4
        )

        self.assertTrue(result["degraded"])
        self.assertIn("LLMClientError", result["error"])
        # 降级仍按未分类 NOTE 卡片返回，input_kind 保持 experiment 分支
        self.assertEqual(result["input_kind"], "experiment")
        self.assertEqual(len(result["events"]), 1)
        note = result["events"][0]
        self.assertEqual(note["event_type"], "note")
        self.assertEqual(note["raw_text"], "加热到六十度")
        self.assertIsNone(note["entities"]["action"])

    def test_invalid_json_degrades_without_raising(self):
        _install(content="not-json")
        result = llm_bridge.extract(
            "离心三分钟", session_id="session-1", segment_id=5
        )

        self.assertTrue(result["degraded"])
        self.assertIn("UnifiedUnderstandingError", result["error"])
        self.assertEqual(result["events"][0]["event_type"], "note")

    def test_recent_context_strips_blank_entries(self):
        client = _install(content=_response("experiment", EXPERIMENT_BRANCH))
        llm_bridge.extract(
            "加入五毫升缓冲液。",
            session_id="session-1",
            segment_id=6,
            recent_context=("刚才记录了离心。", "   ", ""),
        )

        _, user_prompt = client.calls[0]
        payload = json.loads(user_prompt.split("\n", 1)[1])
        self.assertEqual(payload["recent_context"], ["刚才记录了离心。"])

    def test_recent_context_passed_through_to_llm(self):
        client = _install(content=_response("experiment", EXPERIMENT_BRANCH))
        llm_bridge.extract(
            "再加热五分钟。",
            session_id="session-1",
            segment_id=7,
            recent_context=("先加入缓冲液。",),
        )

        _, user_prompt = client.calls[0]
        payload = json.loads(user_prompt.split("\n", 1)[1])
        self.assertEqual(payload["current_asr_raw_text"], "再加热五分钟。")
        self.assertEqual(payload["recent_context"], ["先加入缓冲液。"])


if __name__ == "__main__":
    unittest.main()
