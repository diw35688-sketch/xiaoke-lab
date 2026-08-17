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
    def test_instructions_mandate_record_tool(self):
        self.assertIn("record_observation", agent.core.INSTRUCTIONS)
        self.assertIn(
            "必须调用 record_observation 工具", agent.core.INSTRUCTIONS
        )

    def test_instructions_forbid_claiming_recorded_without_tool(self):
        self.assertIn(
            "禁止不调用工具就直接回复", agent.core.INSTRUCTIONS
        )
        self.assertIn("已记录", agent.core.INSTRUCTIONS)

    def test_instructions_gate_recorded_claim_on_tool_success(self):
        self.assertIn(
            "只有 record_observation 返回成功", agent.core.INSTRUCTIONS
        )
        self.assertIn(
            "必须如实说明记录未保存成功", agent.core.INSTRUCTIONS
        )

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
