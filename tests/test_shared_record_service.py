import unittest
from datetime import datetime, timezone
from pathlib import Path
import sys
from types import SimpleNamespace

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from record_service import (  # noqa: E402
    RecordCommand,
    RecordPersistenceError,
    SharedRecordService,
)


NOW = datetime(2026, 8, 23, 18, 0, tzinfo=timezone.utc)
FOLLOW_UP = {
    "missing_fields": ["duration"],
    "follow_up_question": "加热了多长时间？",
    "deviations": [],
}


class SharedRecordServiceTests(unittest.TestCase):
    def _service(
        self,
        *,
        llm_result=None,
        rule_result=None,
        evaluation=FOLLOW_UP,
        step=None,
        save=None,
        calls=None,
    ):
        calls = calls if calls is not None else []
        llm_result = llm_result or {
            "events": [
                {"entities": {"temperature": "60摄氏度"}}
            ],
            "degraded": False,
        }
        rule_result = rule_result or SimpleNamespace(
            temperature=None, duration=None
        )
        step = step or {"mode": "protocol", "index": 1}

        def mark(name, value):
            calls.append(name)
            return value

        def default_save(item):
            calls.append("save")
            return dict(item)

        service = SharedRecordService(
            current_session_id=lambda: mark("session", "session-1"),
            next_segment_id=lambda session: mark("segment", 3),
            list_records=lambda session: mark(
                "context", [{"transcript": "先加入试剂"}]
            ),
            extract_entities_llm=lambda *args, **kwargs: mark(
                "llm", llm_result
            ),
            extract_entities_rule=lambda text, terms: mark(
                "rule", rule_result
            ),
            current_terms=lambda: mark("terms", ("加热",)),
            evaluate=lambda entities: mark("evaluate", evaluation),
            step_view=lambda: mark("step", step),
            save_record=save or default_save,
            clock=lambda: mark("clock", NOW),
            request_id_factory=lambda: mark("request_id", "web-fixed"),
        )
        return service, calls

    def test_structured_record_is_saved_before_success_result_and_intents(self):
        service, calls = self._service()

        result = service.record(RecordCommand("  加热到60摄氏度  "))

        self.assertEqual(result.saved_record["transcript"], "加热到60摄氏度")
        self.assertTrue(result.observation_result.persisted)
        self.assertEqual(result.intents[0].kind.value, "clarification")
        self.assertLess(calls.index("evaluate"), calls.index("save"))
        self.assertLess(calls.index("save"), calls.index("request_id"))

    def test_recent_context_is_forwarded_oldest_to_newest(self):
        captured = []
        service, _ = self._service()
        service._extract_entities_llm = lambda *args, **kwargs: (
            captured.append(kwargs["recent_context"])
            or {"events": [], "degraded": False}
        )

        service.record(RecordCommand("记录颜色变化"))

        self.assertEqual(captured, [("先加入试剂",)])

    def test_free_mode_preserves_unified_follow_up_after_save(self):
        """统一理解的语义追问不能被自由模式的空方案评估覆盖。"""

        calls = []
        service, calls = self._service(
            calls=calls,
            llm_result={
                "events": [
                    {
                        "entities": {
                            "action": "加热",
                            "object": "样品",
                        },
                        "missing_fields": ["duration"],
                    }
                ],
                "should_ask_follow_up": True,
                "follow_up_question": "样品加热了多长时间？",
                "input_kind": "experiment",
                "degraded": False,
            },
            evaluation={
                "missing_fields": [],
                "follow_up_question": None,
                "follow_up_required": False,
                "deviations": [],
            },
            step={"mode": "free", "protocol": None, "step": None},
        )

        result = service.record(RecordCommand("加热样品"))

        self.assertEqual(result.observation_result.missing_fields, ("duration",))
        self.assertEqual(
            result.observation_result.follow_up_question,
            "样品加热了多长时间？",
        )
        self.assertEqual(
            result.saved_record["evaluation"]["missing_fields"],
            ["duration"],
        )
        self.assertEqual(
            result.saved_record["evaluation"]["follow_up_question"],
            "样品加热了多长时间？",
        )
        self.assertEqual(result.intents[0].kind.value, "clarification")
        self.assertLess(calls.index("save"), calls.index("request_id"))

    def test_protocol_mode_keeps_deterministic_follow_up_authority(self):
        service, _ = self._service(
            llm_result={
                "events": [
                    {
                        "entities": {"action": "加热"},
                        "missing_fields": ["temperature"],
                    }
                ],
                "should_ask_follow_up": True,
                "follow_up_question": "模型问题不应覆盖方案问题。",
                "input_kind": "experiment",
                "degraded": False,
            },
            evaluation=FOLLOW_UP,
            step={"mode": "protocol", "index": 1},
        )

        result = service.record(RecordCommand("加热样品"))

        self.assertEqual(result.observation_result.missing_fields, ("duration",))
        self.assertEqual(
            result.observation_result.follow_up_question,
            "加热了多长时间？",
        )

    def test_llm_failure_uses_rule_fallback_and_preserves_error_evidence(self):
        def failing_llm(*args, **kwargs):
            raise RuntimeError("model offline")

        service, _ = self._service(
            rule_result=SimpleNamespace(temperature="60摄氏度"),
        )
        service._extract_entities_llm = failing_llm

        result = service.record(RecordCommand("加热到60摄氏度"))

        self.assertEqual(result.saved_record["extraction_source"], "rule")
        self.assertIn("model offline", result.saved_record["extraction"]["error"])
        self.assertEqual(
            result.observation_result.entities["temperature"], "60摄氏度"
        )

    def test_save_failure_produces_no_success_projection(self):
        calls = []

        def fail_save(item):
            calls.append("save")
            raise OSError("disk full")

        service, calls = self._service(save=fail_save, calls=calls)

        with self.assertRaisesRegex(RecordPersistenceError, "disk full"):
            service.record(RecordCommand("加热到60摄氏度"))

        self.assertNotIn("request_id", calls)

    def test_degraded_saved_record_produces_record_ack_intent(self):
        service, _ = self._service(
            llm_result={"events": [], "degraded": True},
            rule_result=SimpleNamespace(temperature=None, duration=None),
            evaluation={
                "missing_fields": [],
                "follow_up_question": None,
                "deviations": [],
            },
        )

        result = service.record(RecordCommand("溶液颜色变蓝"))

        self.assertEqual(result.observation_result.structure_status.value, "degraded")
        self.assertEqual(result.intents[0].kind.value, "record_ack")

    def test_result_is_immutable_and_contains_no_rendered_messages(self):
        service, _ = self._service()
        result = service.record(RecordCommand("加热到60摄氏度"))

        with self.assertRaises(TypeError):
            result.saved_record["transcript"] = "changed"
        self.assertNotIn("messages", result.saved_record)
        self.assertFalse(hasattr(service, "render"))
        self.assertFalse(hasattr(service, "play"))

    def test_invalid_command_and_dependency_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "transcript"):
            RecordCommand("   ")
        service, _ = self._service()
        with self.assertRaisesRegex(TypeError, "command"):
            service.record("text")


if __name__ == "__main__":
    unittest.main()
