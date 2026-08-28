import json
import unittest

from src.core.experiment_acceptance import (
    AcceptedExperimentAnalysis,
    ExperimentAcceptanceKind,
)
from src.core.pending_clarification import PendingClarification
from src.core.protocol_completion_policy import (
    ProtocolStepFactState,
    resolve_protocol_completion,
)
from src.llm.schemas import (
    ExperimentEntities,
    ExperimentEvent,
    ExperimentEventType,
    LLMAnalysisResult,
)


def _accepted() -> AcceptedExperimentAnalysis:
    analysis = LLMAnalysisResult(events=[ExperimentEvent(
        ExperimentEventType.OBSERVATION,
        "室温保存", "室温保存",
        entities=ExperimentEntities(condition="室温保存"),
        source_session_id="lab1", source_segment_id=2,
    )])
    payload = analysis.to_dict()
    for event in payload["events"]:
        event.pop("source_session_id", None)
        event.pop("source_segment_id", None)
    return AcceptedExperimentAnalysis(
        request_id="r2", session_id="lab1", segment_id=2,
        asr_transcript="室温保存",
        kind=ExperimentAcceptanceKind.STRUCTURED_EXPERIMENT,
        analysis_json=json.dumps(payload, ensure_ascii=False),
        event_count=1, degraded=False, error=None,
        llm_attempts=1, llm_processing_seconds=.01,
    )


class ProtocolCompletionPolicyTests(unittest.TestCase):
    def test_snapshot_resets_when_step_identity_changes(self):
        old = ProtocolStepFactState.empty(
            protocol_id="p1", protocol_version="1", step_number=1
        )
        old, _ = old.merge(
            {"temperature": "25℃"}, request_id="r1", segment_id=1
        )
        restored = ProtocolStepFactState.from_snapshot(
            old.to_snapshot(), protocol_id="p1",
            protocol_version="1", step_number=2,
        )
        self.assertEqual(restored.entity_values(), {})

    def test_conflict_does_not_silently_overwrite(self):
        state = ProtocolStepFactState.empty(
            protocol_id="p1", protocol_version="1", step_number=1
        )
        state, _ = state.merge(
            {"temperature": "25℃"}, request_id="r1", segment_id=1
        )
        state, conflicts = state.merge(
            {"temperature": "28℃"}, request_id="r2", segment_id=2
        )
        self.assertEqual(state.entity_values()["temperature"], "25℃")
        self.assertEqual(conflicts, ("temperature",))

    def test_existing_question_is_answered_instead_of_duplicated(self):
        state = ProtocolStepFactState.empty(
            protocol_id="p1", protocol_version="1", step_number=1
        )
        state, _ = state.merge(
            {"observation": "透明", "condition": "室温"},
            request_id="r2", segment_id=2,
        )
        existing = PendingClarification(
            clarification_id="q1", display_number=1,
            source_segment_id=1, source_raw_text="溶液透明",
            question="请补充保存条件。", missing_fields=("condition",),
        )
        result = resolve_protocol_completion(
            accepted=_accepted(), state=state,
            evaluation={
                "missing_fields": [], "follow_up_required": False,
                "follow_up_question": None, "deviations": [],
            },
            existing=existing,
        )
        self.assertEqual(result.action.action_type.value, "answer")
        self.assertEqual(result.action.target_clarification_id, "q1")
        self.assertEqual(result.action.supplied_entity_fields, ("condition",))


if __name__ == "__main__":
    unittest.main()
