"""将统一路由结果转换为不执行副作用的安全分派计划。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.core.intent_policy import IntentDisposition
from src.core.interaction_command import InteractionCommandType
from src.core.unified_understanding import UnifiedInputKind
from src.llm.unified_router import UnifiedRouteResult


class UnifiedDispatchDestination(str, Enum):
    """分派计划允许交给的下游边界。"""

    EXPERIMENT_PIPELINE = "experiment_pipeline"
    CLARIFICATION_CONTEXT = "clarification_context"
    END_SESSION_EXECUTION = "end_session_execution"
    END_SESSION_CONFIRMATION = "end_session_confirmation"
    PROTOCOL_NAVIGATION = "protocol_navigation"
    ABSTENTION = "abstention"
    DEGRADED_NOTE = "degraded_note"


class UnifiedDispatchPermission(str, Enum):
    """下游获得的最小权限；分派器自身不使用这些权限。"""

    FORWARD_EXPERIMENT_ANALYSIS = "forward_experiment_analysis"
    FORWARD_CONTEXT_CANDIDATE = "forward_context_candidate"
    FORWARD_END_EXECUTION_CANDIDATE = (
        "forward_end_execution_candidate"
    )
    REQUEST_END_CONFIRMATION = "request_end_confirmation"
    EXECUTE_PROTOCOL_NAVIGATION = "execute_protocol_navigation"
    NO_ACTION = "no_action"
    FORWARD_DEGRADED_NOTE = "forward_degraded_note"


_DESTINATION_PERMISSIONS = {
    UnifiedDispatchDestination.EXPERIMENT_PIPELINE: (
        UnifiedDispatchPermission.FORWARD_EXPERIMENT_ANALYSIS
    ),
    UnifiedDispatchDestination.CLARIFICATION_CONTEXT: (
        UnifiedDispatchPermission.FORWARD_CONTEXT_CANDIDATE
    ),
    UnifiedDispatchDestination.END_SESSION_EXECUTION: (
        UnifiedDispatchPermission.FORWARD_END_EXECUTION_CANDIDATE
    ),
    UnifiedDispatchDestination.END_SESSION_CONFIRMATION: (
        UnifiedDispatchPermission.REQUEST_END_CONFIRMATION
    ),
    UnifiedDispatchDestination.PROTOCOL_NAVIGATION: (
        UnifiedDispatchPermission.EXECUTE_PROTOCOL_NAVIGATION
    ),
    UnifiedDispatchDestination.ABSTENTION: (
        UnifiedDispatchPermission.NO_ACTION
    ),
    UnifiedDispatchDestination.DEGRADED_NOTE: (
        UnifiedDispatchPermission.FORWARD_DEGRADED_NOTE
    ),
}


def required_permission_for(
    destination: UnifiedDispatchDestination,
) -> UnifiedDispatchPermission:
    """返回目标唯一允许的最小权限，供相邻合同复用。"""

    if not isinstance(destination, UnifiedDispatchDestination):
        raise TypeError("destination必须是UnifiedDispatchDestination。")
    return _DESTINATION_PERMISSIONS[destination]


@dataclass(frozen=True)
class UnifiedDispatchPlan:
    """一份只读分派合同：描述下一站，不代表动作已经执行。"""

    destination: UnifiedDispatchDestination
    permission: UnifiedDispatchPermission
    asr_transcript: str
    route_result: UnifiedRouteResult
    reason: str

    def __post_init__(self) -> None:
        if not self.asr_transcript.strip():
            raise ValueError("asr_transcript不能为空。")
        if self.asr_transcript != self.route_result.raw_text:
            raise ValueError("分派计划必须原样保留路由输入文本。")
        if not self.reason.strip():
            raise ValueError("分派原因不能为空。")
        expected = required_permission_for(self.destination)
        if self.permission != expected:
            raise ValueError("分派目标与最小权限不匹配。")


class UnifiedDispatchPlanner:
    """纯规则规划器：不接收存储、状态机、协调器或TTS依赖。"""

    @classmethod
    def plan(
        cls,
        route_result: UnifiedRouteResult,
    ) -> UnifiedDispatchPlan:
        outcome = route_result.understanding_outcome

        # 外部模型失败或格式失败优先于其降级数据外形。
        if outcome is not None and outcome.degraded:
            return cls._build(
                route_result,
                UnifiedDispatchDestination.DEGRADED_NOTE,
                "统一理解失败，只允许转交降级NOTE并保留口述。",
            )

        if outcome is not None:
            understanding = outcome.value
            if understanding.input_kind == UnifiedInputKind.UNCERTAIN:
                cls._require_normal_decision(route_result)
                return cls._build(
                    route_result,
                    UnifiedDispatchDestination.ABSTENTION,
                    "统一理解明确弃权，不执行也不伪装成实验事实。",
                )
            if understanding.input_kind == UnifiedInputKind.EXPERIMENT:
                cls._require_normal_decision(route_result)
                if (
                    route_result.decision.disposition
                    != IntentDisposition.PASS_TO_EXPERIMENT
                ):
                    raise ValueError("实验理解必须进入实验候选处置。")
                return cls._build(
                    route_result,
                    UnifiedDispatchDestination.EXPERIMENT_PIPELINE,
                    "结构化实验理解只转交实验处理链路。",
                )

            control_type = understanding.control.intent.command_type
            if control_type != route_result.decision.command_type:
                raise ValueError("控制候选与风险决策的意图类型不一致。")

        disposition = route_result.decision.disposition
        if disposition == IntentDisposition.REQUIRE_CONTEXT:
            return cls._build(
                route_result,
                UnifiedDispatchDestination.CLARIFICATION_CONTEXT,
                "需要待确认上下文复核，分派器不修改问题状态。",
            )
        if disposition == IntentDisposition.EXECUTE:
            if (
                route_result.decision.command_type
                == InteractionCommandType.NEXT_PROTOCOL_STEP
                and route_result.exact_command is not None
            ):
                return cls._build(
                    route_result,
                    UnifiedDispatchDestination.PROTOCOL_NAVIGATION,
                    "精确下一步命令只授权方案导航边界执行。",
                )
            if (
                route_result.decision.command_type
                != InteractionCommandType.END_SESSION
                or route_result.exact_command is None
            ):
                raise ValueError("只有精确结束命令可形成执行候选。")
            return cls._build(
                route_result,
                UnifiedDispatchDestination.END_SESSION_EXECUTION,
                "精确结束命令只形成下游执行候选，分派器不结束会话。",
            )
        if disposition == IntentDisposition.REQUEST_CONFIRMATION:
            if (
                route_result.decision.command_type
                != InteractionCommandType.END_SESSION
            ):
                raise ValueError("只有高风险结束候选请求结束确认。")
            return cls._build(
                route_result,
                UnifiedDispatchDestination.END_SESSION_CONFIRMATION,
                "LLM高风险结束候选必须先请求用户确认。",
            )
        if disposition == IntentDisposition.DO_NOT_EXECUTE:
            return cls._build(
                route_result,
                UnifiedDispatchDestination.ABSTENTION,
                "控制候选证据不足，保留路由证据但不执行。",
            )

        raise ValueError(
            "路由结果的分支与风险处置不能形成安全分派。"
        )

    @staticmethod
    def _require_normal_decision(
        route_result: UnifiedRouteResult,
    ) -> None:
        if (
            route_result.decision.command_type
            != InteractionCommandType.NORMAL
        ):
            raise ValueError("非控制理解必须对应NORMAL风险决策。")

    @staticmethod
    def _build(
        route_result: UnifiedRouteResult,
        destination: UnifiedDispatchDestination,
        reason: str,
    ) -> UnifiedDispatchPlan:
        return UnifiedDispatchPlan(
            destination=destination,
            permission=required_permission_for(destination),
            asr_transcript=route_result.raw_text,
            route_result=route_result,
            reason=reason,
        )
