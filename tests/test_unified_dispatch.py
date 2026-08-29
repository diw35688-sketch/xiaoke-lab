import unittest
from dataclasses import FrozenInstanceError

from src.core.intent_classifier import IntentCandidate
from src.core.intent_policy import (
    IntentEvidence,
    IntentPolicyEvaluator,
)
from src.core.interaction_command import (
    InteractionCommand,
    InteractionCommandType,
)
from src.core.unified_dispatch import (
    UnifiedDispatchDestination,
    UnifiedDispatchPermission,
    UnifiedDispatchPlan,
    UnifiedDispatchPlanner,
)
from src.core.unified_understanding import (
    ControlUnderstanding,
    ExperimentUnderstanding,
    UnifiedUnderstandingResult,
    UncertainUnderstanding,
    build_degraded_understanding,
)
from src.llm.processor import ProcessOutcome
from src.llm.schemas import LLMAnalysisResult
from src.llm.unified_router import UnifiedRouteResult


RAW_TEXT = "用户忠实转写。"


def exact_route(command_type, raw_text=RAW_TEXT):
    command = InteractionCommand(
        command_type=command_type,
        raw_text=raw_text,
        normalized_text=raw_text,
    )
    return UnifiedRouteResult(
        exact_command=command,
        decision=IntentPolicyEvaluator.evaluate(
            command_type,
            IntentEvidence.EXACT_RULE,
        ),
    )


def understanding_route(understanding, command_type, degraded=False):
    return UnifiedRouteResult(
        understanding_outcome=ProcessOutcome(
            value=understanding,
            degraded=degraded,
            error="fake failure" if degraded else None,
        ),
        decision=IntentPolicyEvaluator.evaluate(
            command_type,
            IntentEvidence.LLM_CANDIDATE,
        ),
    )


def control_route(command_type, **candidate_fields):
    candidate = IntentCandidate(
        command_type=command_type,
        reason="Fake控制候选。",
        **candidate_fields,
    )
    understanding = UnifiedUnderstandingResult(
        raw_text=RAW_TEXT,
        control=ControlUnderstanding(candidate),
    )
    return understanding_route(
        understanding,
        command_type,
    )


class UnifiedDispatchPlannerTests(unittest.TestCase):
    def test_exact_next_step_gets_only_protocol_navigation_permission(self):
        plan = UnifiedDispatchPlanner.plan(
            exact_route(InteractionCommandType.NEXT_PROTOCOL_STEP)
        )

        self.assertEqual(
            plan.destination,
            UnifiedDispatchDestination.PROTOCOL_NAVIGATION,
        )
        self.assertEqual(
            plan.permission,
            UnifiedDispatchPermission.EXECUTE_PROTOCOL_NAVIGATION,
        )

    def test_llm_next_step_candidate_cannot_execute(self):
        plan = UnifiedDispatchPlanner.plan(
            control_route(InteractionCommandType.NEXT_PROTOCOL_STEP)
        )

        self.assertEqual(plan.destination, UnifiedDispatchDestination.ABSTENTION)
        self.assertEqual(plan.permission, UnifiedDispatchPermission.NO_ACTION)

    def test_experiment_goes_only_to_experiment_pipeline(self):
        understanding = UnifiedUnderstandingResult(
            raw_text=RAW_TEXT,
            experiment=ExperimentUnderstanding(
                LLMAnalysisResult(events=[])
            ),
        )

        plan = UnifiedDispatchPlanner.plan(
            understanding_route(
                understanding,
                InteractionCommandType.NORMAL,
            )
        )

        self.assertEqual(
            plan.destination,
            UnifiedDispatchDestination.EXPERIMENT_PIPELINE,
        )
        self.assertEqual(
            plan.permission,
            UnifiedDispatchPermission.FORWARD_EXPERIMENT_ANALYSIS,
        )

    def test_exact_context_command_is_forwarded_not_executed(self):
        plan = UnifiedDispatchPlanner.plan(
            exact_route(InteractionCommandType.REVIEW_PENDING)
        )

        self.assertEqual(
            plan.destination,
            UnifiedDispatchDestination.CLARIFICATION_CONTEXT,
        )

    def test_llm_low_risk_review_can_enter_context(self):
        plan = UnifiedDispatchPlanner.plan(
            control_route(InteractionCommandType.REVIEW_PENDING)
        )

        self.assertEqual(
            plan.permission,
            UnifiedDispatchPermission.FORWARD_CONTEXT_CANDIDATE,
        )

    def test_llm_targeted_answer_abstains_without_state_write(self):
        plan = UnifiedDispatchPlanner.plan(control_route(
            InteractionCommandType.TARGETED_ANSWER,
            target_question_number=2,
            answer_text="五分钟",
        ))

        self.assertEqual(
            plan.destination,
            UnifiedDispatchDestination.ABSTENTION,
        )
        self.assertEqual(
            plan.permission,
            UnifiedDispatchPermission.NO_ACTION,
        )

    def test_exact_end_and_llm_end_have_different_destinations(self):
        exact_plan = UnifiedDispatchPlanner.plan(
            exact_route(InteractionCommandType.END_SESSION)
        )
        llm_plan = UnifiedDispatchPlanner.plan(
            control_route(InteractionCommandType.END_SESSION)
        )

        self.assertEqual(
            exact_plan.destination,
            UnifiedDispatchDestination.END_SESSION_EXECUTION,
        )
        self.assertEqual(
            llm_plan.destination,
            UnifiedDispatchDestination.END_SESSION_CONFIRMATION,
        )

    def test_uncertain_explicitly_abstains(self):
        understanding = UnifiedUnderstandingResult(
            raw_text=RAW_TEXT,
            uncertain=UncertainUnderstanding("证据不足。"),
        )

        plan = UnifiedDispatchPlanner.plan(
            understanding_route(
                understanding,
                InteractionCommandType.NORMAL,
            )
        )

        self.assertEqual(
            plan.destination,
            UnifiedDispatchDestination.ABSTENTION,
        )

    def test_degraded_result_has_priority_over_experiment_shape(self):
        degraded = build_degraded_understanding(
            raw_text=RAW_TEXT,
            session_id="session-1",
            segment_id=1,
            reason="timeout",
        )

        plan = UnifiedDispatchPlanner.plan(
            understanding_route(
                degraded,
                InteractionCommandType.NORMAL,
                degraded=True,
            )
        )

        self.assertEqual(
            plan.destination,
            UnifiedDispatchDestination.DEGRADED_NOTE,
        )

    def test_plan_preserves_transcript_and_is_immutable(self):
        plan = UnifiedDispatchPlanner.plan(
            exact_route(
                InteractionCommandType.REVIEW_PENDING,
                raw_text="查看待确认问题。",
            )
        )

        self.assertEqual(plan.asr_transcript, "查看待确认问题。")
        with self.assertRaises(FrozenInstanceError):
            plan.reason = "改写"

    def test_plan_rejects_destination_permission_mismatch(self):
        route = exact_route(InteractionCommandType.REVIEW_PENDING)

        with self.assertRaisesRegex(ValueError, "最小权限不匹配"):
            UnifiedDispatchPlan(
                destination=(
                    UnifiedDispatchDestination.CLARIFICATION_CONTEXT
                ),
                permission=UnifiedDispatchPermission.NO_ACTION,
                asr_transcript=RAW_TEXT,
                route_result=route,
                reason="非法组合。",
            )

    def test_malformed_route_decision_is_rejected(self):
        understanding = UnifiedUnderstandingResult(
            raw_text=RAW_TEXT,
            experiment=ExperimentUnderstanding(
                LLMAnalysisResult(events=[])
            ),
        )
        malformed = understanding_route(
            understanding,
            InteractionCommandType.REVIEW_PENDING,
        )

        with self.assertRaisesRegex(ValueError, "NORMAL风险决策"):
            UnifiedDispatchPlanner.plan(malformed)


if __name__ == "__main__":
    unittest.main()
