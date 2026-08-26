# -*- coding: utf-8 -*-
"""web/agent 提示词合同测试：防"假记录"规则被误删。

背景（WEB-AGENT-FAKE-RECORD-01）：聊天 agent 曾对实验口述口头回复"已记录"
却不调用 record_observation 工具，导致 lab_records 无记录（数据丢失隐患）。
修复 = INSTRUCTIONS 强制"描述实验操作必须调工具，工具成功才能说已记录"。
本测试保护该规则与工具注册不被回归。
"""

import sys
import unittest
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

import agent.core  # noqa: E402


class AgentPromptContractTests(unittest.TestCase):
    def test_experiment_policy_mandates_record_tool(self):
        self.assertIn("record_observation", agent.core.EXPERIMENT_RECORD_POLICY)
        self.assertIn(
            "必须调用 record_observation", agent.core.EXPERIMENT_RECORD_POLICY
        )

    def test_instructions_forbid_claiming_recorded_without_tool(self):
        self.assertIn("只有工具返回成功", agent.core.EXPERIMENT_RECORD_POLICY)

    def test_instructions_gate_recorded_claim_on_tool_success(self):
        self.assertIn(
            "只有工具返回成功", agent.core.EXPERIMENT_RECORD_POLICY
        )
        self.assertIn(
            "失败必须如实说明未保存", agent.core.EXPERIMENT_RECORD_POLICY
        )

    def test_chat_policy_forbids_recording_and_record_tool_is_hidden(self):
        self.assertIn("不能调用 record_observation", agent.core.CHAT_POLICY)
        names = [
            item["function"]["name"]
            for item in agent.core._tools_for_mode(agent.core.InteractionMode.CHAT)
        ]
        self.assertNotIn("record_observation", names)

    def test_chat_policy_requests_one_visible_speakable_answer_within_budget(self):
        self.assertIn("最多50个中文字符", agent.core.CHAT_POLICY)
        self.assertIn("不要使用Markdown", agent.core.CHAT_POLICY)
        self.assertIn("不要先写长回答再附摘要", agent.core.CHAT_POLICY)

    def test_record_observation_registered_in_tools(self):
        names = [t["function"]["name"] for t in agent.core.TOOLS]
        self.assertIn("record_observation", names)

    def test_record_observation_schema_requires_transcript(self):
        tool = next(
            t for t in agent.core.TOOLS
            if t["function"]["name"] == "record_observation"
        )
        props = tool["function"]["parameters"]["properties"]
        self.assertIn("transcript", props)
        self.assertIn(
            "transcript", tool["function"]["parameters"]["required"]
        )


if __name__ == "__main__":
    unittest.main()
