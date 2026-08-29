"""交互意图的风险等级与执行边界。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.core.interaction_command import InteractionCommandType


class IntentRisk(str, Enum):
    """意图执行错误可能造成的影响。"""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class IntentEvidence(str, Enum):
    """系统为什么认为用户表达了某个意图。"""

    EXACT_RULE = "exact_rule"
    LOCAL_SEMANTIC = "local_semantic"
    LLM_CANDIDATE = "llm_candidate"


class IntentDisposition(str, Enum):
    """候选意图下一步允许进入的处理方式。"""

    PASS_TO_EXPERIMENT = "pass_to_experiment"
    EXECUTE = "execute"
    REQUIRE_CONTEXT = "require_context"
    REQUEST_CONFIRMATION = "request_confirmation"
    DO_NOT_EXECUTE = "do_not_execute"


@dataclass(frozen=True)
class IntentPolicy:
    """一种意图的固定风险属性。"""

    command_type: InteractionCommandType
    risk: IntentRisk
    changes_session_state: bool
    requires_clarification_context: bool
    reversible: bool


@dataclass(frozen=True)
class IntentDecision:
    """意图候选经过风险策略后的结果，不负责真正执行命令。"""

    command_type: InteractionCommandType
    evidence: IntentEvidence
    risk: IntentRisk
    disposition: IntentDisposition
    reason: str

    @property
    def may_execute_now(self) -> bool:
        return self.disposition in {
            IntentDisposition.EXECUTE,
            IntentDisposition.REQUIRE_CONTEXT,
        }


INTENT_POLICIES = {
    InteractionCommandType.NORMAL: IntentPolicy(
        command_type=InteractionCommandType.NORMAL,
        risk=IntentRisk.NONE,
        changes_session_state=False,
        requires_clarification_context=False,
        reversible=True,
    ),
    InteractionCommandType.REVIEW_PENDING: IntentPolicy(
        command_type=InteractionCommandType.REVIEW_PENDING,
        risk=IntentRisk.LOW,
        changes_session_state=False,
        requires_clarification_context=True,
        reversible=True,
    ),
    InteractionCommandType.NEXT_PROTOCOL_STEP: IntentPolicy(
        command_type=InteractionCommandType.NEXT_PROTOCOL_STEP,
        risk=IntentRisk.MEDIUM,
        changes_session_state=True,
        requires_clarification_context=False,
        reversible=True,
    ),
    InteractionCommandType.DEFER_CURRENT: IntentPolicy(
        command_type=InteractionCommandType.DEFER_CURRENT,
        risk=IntentRisk.MEDIUM,
        changes_session_state=True,
        requires_clarification_context=True,
        reversible=True,
    ),
    InteractionCommandType.DEFER_TARGETED: IntentPolicy(
        command_type=InteractionCommandType.DEFER_TARGETED,
        risk=IntentRisk.MEDIUM,
        changes_session_state=True,
        requires_clarification_context=True,
        reversible=True,
    ),
    InteractionCommandType.REACTIVATE_TARGETED: IntentPolicy(
        command_type=InteractionCommandType.REACTIVATE_TARGETED,
        risk=IntentRisk.MEDIUM,
        changes_session_state=True,
        requires_clarification_context=True,
        reversible=True,
    ),
    InteractionCommandType.AFFIRM: IntentPolicy(
        command_type=InteractionCommandType.AFFIRM,
        risk=IntentRisk.MEDIUM,
        changes_session_state=True,
        requires_clarification_context=True,
        reversible=False,
    ),
    InteractionCommandType.DENY: IntentPolicy(
        command_type=InteractionCommandType.DENY,
        risk=IntentRisk.MEDIUM,
        changes_session_state=True,
        requires_clarification_context=True,
        reversible=False,
    ),
    InteractionCommandType.TARGETED_ANSWER: IntentPolicy(
        command_type=InteractionCommandType.TARGETED_ANSWER,
        risk=IntentRisk.MEDIUM,
        changes_session_state=True,
        requires_clarification_context=True,
        reversible=False,
    ),
    InteractionCommandType.END_SESSION: IntentPolicy(
        command_type=InteractionCommandType.END_SESSION,
        risk=IntentRisk.HIGH,
        changes_session_state=True,
        requires_clarification_context=False,
        reversible=False,
    ),
}


class IntentPolicyEvaluator:
    """根据意图类型和证据来源给出执行边界。"""

    @staticmethod
    def evaluate(
        command_type: InteractionCommandType,
        evidence: IntentEvidence,
    ) -> IntentDecision:
        policy = INTENT_POLICIES[command_type]

        if command_type == InteractionCommandType.NORMAL:
            return IntentDecision(
                command_type=command_type,
                evidence=evidence,
                risk=policy.risk,
                disposition=IntentDisposition.PASS_TO_EXPERIMENT,
                reason="普通实验口述继续进入实验记录链路。",
            )

        if evidence == IntentEvidence.EXACT_RULE:
            disposition = (
                IntentDisposition.REQUIRE_CONTEXT
                if policy.requires_clarification_context
                else IntentDisposition.EXECUTE
            )
            return IntentDecision(
                command_type=command_type,
                evidence=evidence,
                risk=policy.risk,
                disposition=disposition,
                reason="精确规则命中，按该意图的上下文要求处理。",
            )

        if command_type == InteractionCommandType.NEXT_PROTOCOL_STEP:
            return IntentDecision(
                command_type=command_type,
                evidence=evidence,
                risk=policy.risk,
                disposition=IntentDisposition.DO_NOT_EXECUTE,
                reason="方案切步只接受本地精确命令，语义候选不得执行。",
            )

        if policy.risk == IntentRisk.LOW:
            return IntentDecision(
                command_type=command_type,
                evidence=evidence,
                risk=policy.risk,
                disposition=IntentDisposition.REQUIRE_CONTEXT,
                reason="低风险只读意图允许语义容错，但仍需业务上下文。",
            )

        if policy.risk == IntentRisk.HIGH:
            return IntentDecision(
                command_type=command_type,
                evidence=evidence,
                risk=policy.risk,
                disposition=IntentDisposition.REQUEST_CONFIRMATION,
                reason="高风险意图不能根据语义候选直接执行。",
            )

        disposition = (
            IntentDisposition.REQUIRE_CONTEXT
            if policy.reversible
            and evidence
            in {
                IntentEvidence.LOCAL_SEMANTIC,
                IntentEvidence.LLM_CANDIDATE,
            }
            else IntentDisposition.DO_NOT_EXECUTE
        )
        reason = (
            "可恢复操作命中，交由上下文层再次校验。"
            if disposition == IntentDisposition.REQUIRE_CONTEXT
            else "状态写入意图证据不足，保留候选但不执行。"
        )
        return IntentDecision(
            command_type=command_type,
            evidence=evidence,
            risk=policy.risk,
            disposition=disposition,
            reason=reason,
        )
