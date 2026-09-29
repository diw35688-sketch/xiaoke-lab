import unittest
from pathlib import Path
import sys
from types import MappingProxyType, SimpleNamespace
from unittest.mock import patch

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

import lab_tools  # noqa: E402
import lab_tools_record  # noqa: E402
from src.core.presentation_intent import (  # noqa: E402
    MessageKind,
    MessagePriority,
    PresentationIntent,
    ScreenTarget,
)


class RecordObservationToolServiceTests(unittest.TestCase):
    def test_tool_uses_shared_service_and_preserves_result_contract(self):
        observation = SimpleNamespace(
            transcript="加热到60摄氏度",
            entities=MappingProxyType({"temperature": "60摄氏度"}),
            missing_fields=("duration",),
            follow_up_question="加热了多长时间？",
            deviations=({"field": "temperature"},),
        )
        shared_result = SimpleNamespace(
            observation_result=observation,
            saved_record=MappingProxyType({"transcript": observation.transcript}),
            intents=(
                PresentationIntent(
                    intent_id="ask-1",
                    kind=MessageKind.CLARIFICATION,
                    args={"question": "加热了多长时间？"},
                    priority=MessagePriority.ACTIVE_QUESTION,
                    screen_target=ScreenTarget.CURRENT_QUESTION,
                    source_segment_id=3,
                ),
            ),
        )
        service = unittest.mock.Mock()
        service.record.return_value = shared_result

        with patch.object(lab_tools, "_build_record_service", return_value=service):
            outcome = lab_tools.call(
                "record_observation", {"transcript": "  加热到60摄氏度  "}
            )

        self.assertTrue(outcome["ok"])
        command = service.record.call_args.args[0]
        self.assertIsInstance(command, lab_tools.RecordCommand)
        self.assertEqual(command.transcript, "  加热到60摄氏度  ")
        self.assertEqual(
            outcome["result"],
            {
                "transcript": "加热到60摄氏度",
                "entities": {"temperature": "60摄氏度"},
                "missing_fields": ["duration"],
                "follow_up_question": "加热了多长时间？",
                "deviations": [{"field": "temperature"}],
            },
        )
        plan = outcome["presentation_plan"]
        self.assertEqual(plan.screen_intents, shared_result.intents)
        self.assertEqual(plan.voice_items[0].voice_text, "加热了多长时间？")

    def test_service_failure_stays_a_structured_tool_error(self):
        service = unittest.mock.Mock()
        service.record.side_effect = OSError("disk full")

        # lab_tools 拆分后，record_observation 的 _build_record_service 在 lab_tools_record 模块内解析
        with patch.object(lab_tools_record, "_build_record_service", return_value=service):
            outcome = lab_tools.call(
                "record_observation", {"transcript": "记录颜色变化"}
            )

        self.assertFalse(outcome["ok"])
        self.assertIn("disk full", outcome["error"])


if __name__ == "__main__":
    unittest.main()
