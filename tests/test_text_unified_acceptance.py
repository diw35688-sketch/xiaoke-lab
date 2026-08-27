import unittest

from src.core.clarification_acceptance import ClarificationContextSnapshot
from src.core.unified_acceptance_bypass import (
    UnifiedAcceptanceBypass,
    UnifiedAcceptanceBypassInput,
)
from src.llm.unified_router import UnifiedUnderstandingRouter


class _NeverLLM:
    def understand(self, request):
        raise AssertionError("明确 control 不应调用 LLM")


class TextUnifiedAcceptanceTests(unittest.TestCase):
    def test_text_control_uses_raw_text_without_fake_asr(self):
        bypass = UnifiedAcceptanceBypass(UnifiedUnderstandingRouter(_NeverLLM()))
        result = bypass.inspect(UnifiedAcceptanceBypassInput(
            request_id="text-request",
            session_id="lab-1",
            segment_id=1,
            asr_result=None,
            raw_text="查看待确认问题",
            clarification_context=ClarificationContextSnapshot(),
        ))
        self.assertIsNone(result.execution_request.asr_evidence)
        self.assertEqual(result.execution_request.raw_text, "查看待确认问题")
        self.assertEqual(result.clarification_action.action_type.value, "review")


if __name__ == "__main__":
    unittest.main()
