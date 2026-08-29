"""把统一分派或已采用实验结果转换为无副作用待确认动作计划。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.core.experiment_acceptance import (
    AcceptedExperimentAnalysis,
    ExperimentAcceptanceKind,
)
from src.core.interaction_command import (
    InteractionCommand,
    InteractionCommandType,
)
from src.core.pending_clarification import PendingClarification
from src.core.unified_dispatch import (
    UnifiedDispatchDestination,
    UnifiedDispatchPermission,
)
from src.core.unified_dispatch_execution import DispatchExecutionRequest


class ClarificationActionType(str, Enum):
    CREATE = "create"
    REVIEW = "review"
    DEFER = "defer"
    ANSWER = "answer"
    CONFIRM = "confirm"
    REJECT_SUGGESTION = "reject_suggestion"
    REACTIVATE = "reactivate"
    NO_ACTION = "no_action"


class ClarificationMutationPermission(str, Enum):
    NONE = "none"
    READ_ONLY = "read_only"
    PREPARE_CREATE = "prepare_create"
    PREPARE_UPDATE = "prepare_update"


_ACTION_PERMISSIONS = {
    ClarificationActionType.CREATE: (
        ClarificationMutationPermission.PREPARE_CREATE
    ),
    ClarificationActionType.REVIEW: ClarificationMutationPermission.READ_ONLY,
    ClarificationActionType.DEFER: (
        ClarificationMutationPermission.PREPARE_UPDATE
    ),
    ClarificationActionType.ANSWER: (
        ClarificationMutationPermission.PREPARE_UPDATE
    ),
    ClarificationActionType.CONFIRM: (
        ClarificationMutationPermission.PREPARE_UPDATE
    ),
    ClarificationActionType.REJECT_SUGGESTION: (
        ClarificationMutationPermission.PREPARE_UPDATE
    ),
    ClarificationActionType.REACTIVATE: (
        ClarificationMutationPermission.PREPARE_UPDATE
    ),
    ClarificationActionType.NO_ACTION: ClarificationMutationPermission.NONE,
}

_ENTITY_CARRYING_ACTION_TYPES = frozenset({
    ClarificationActionType.ANSWER,
    ClarificationActionType.CONFIRM,
    ClarificationActionType.REJECT_SUGGESTION,
})


@dataclass(frozen=True)
class ClarificationContextSnapshot:
    """动作规划时看到的不可变待确认上下文。"""

    unresolved: tuple[PendingClarification, ...] = ()
    current_clarification_id: str | None = None

    def __post_init__(self) -> None:
        ids = [item.clarification_id for item in self.unresolved]
        numbers = [item.display_number for item in self.unresolved]
        if len(ids) != len(set(ids)):
            raise ValueError("上下文中的clarification_id不得重复。")
        if len(numbers) != len(set(numbers)):
            raise ValueError("上下文中的display_number不得重复。")
        if any(not item.is_unresolved for item in self.unresolved):
            raise ValueError("上下文只能包含未解决问题。")
        if self.current_clarification_id is not None:
            current = self.find_by_id(self.current_clarification_id)
            if current is None or not current.is_active:
                raise ValueError("当前问题必须是上下文中的ACTIVE问题。")

    def find_by_id(self, clarification_id: str) -> PendingClarification | None:
        return next(
            (
                item
                for item in self.unresolved
                if item.clarification_id == clarification_id
            ),
            None,
        )

    def find_by_number(self, number: int) -> PendingClarification | None:
        return next(
            (item for item in self.unresolved if item.display_number == number),
            None,
        )

    @property
    def current(self) -> PendingClarification | None:
        if self.current_clarification_id is None:
            return None
        return self.find_by_id(self.current_clarification_id)


@dataclass(frozen=True)
class ClarificationAction:
    """只读动作计划；PREPARE权限也不代表状态已经改变。"""

    request_id: str
    session_id: str
    segment_id: int
    asr_transcript: str
    action_type: ClarificationActionType
    mutation_permission: ClarificationMutationPermission
    reason: str
    requires_evidence_persistence: bool
    target_clarification_id: str | None = None
    target_display_number: int | None = None
    expected_revision: int | None = None
    answer_text: str | None = None
    question: str | None = None
    missing_fields: tuple[str, ...] = ()
    requires_confirmation: bool = False
    supplied_entity_fields: tuple[str, ...] = ()
    protocol_id: str | None = None
    protocol_version: str | None = None
    protocol_step_number: int | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.request_id, "request_id"),
            (self.session_id, "session_id"),
            (self.asr_transcript, "asr_transcript"),
            (self.reason, "reason"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name}不能为空。")
        if self.segment_id <= 0 or isinstance(self.segment_id, bool):
            raise ValueError("segment_id必须是正整数。")
        if self.mutation_permission != _ACTION_PERMISSIONS[self.action_type]:
            raise ValueError("待确认动作与最小修改权限不匹配。")
        if not isinstance(self.requires_evidence_persistence, bool):
            raise TypeError("requires_evidence_persistence必须是布尔值。")
        if len(self.missing_fields) != len(set(self.missing_fields)):
            raise ValueError("missing_fields不得重复。")
        if any(not field.strip() for field in self.missing_fields):
            raise ValueError("missing_fields不能包含空字段。")

        target_values = (
            self.target_clarification_id,
            self.target_display_number,
            self.expected_revision,
        )
        needs_target = self.action_type in {
            ClarificationActionType.DEFER,
            ClarificationActionType.ANSWER,
            ClarificationActionType.CONFIRM,
            ClarificationActionType.REJECT_SUGGESTION,
            ClarificationActionType.REACTIVATE,
        }
        if needs_target:
            if any(value is None for value in target_values):
                raise ValueError("更新待确认项的动作必须包含完整目标身份。")
            if self.target_display_number <= 0 or self.expected_revision <= 0:
                raise ValueError("目标编号和预期revision必须是正整数。")
            if not self.requires_evidence_persistence:
                raise ValueError("状态更新动作必须先要求保存本轮ASR证据。")
        elif any(value is not None for value in target_values):
            raise ValueError("非更新动作不能夹带目标身份。")

        if self.action_type in {
            ClarificationActionType.ANSWER,
            ClarificationActionType.CONFIRM,
            ClarificationActionType.REJECT_SUGGESTION,
        }:
            if self.answer_text is None or not self.answer_text.strip():
                raise ValueError("回答类动作必须包含非空answer_text。")
        elif self.answer_text is not None:
            raise ValueError("非回答动作不能夹带answer_text。")

        if self.supplied_entity_fields:
            if self.action_type not in _ENTITY_CARRYING_ACTION_TYPES:
                raise ValueError(
                    "只有回答类动作（ANSWER/CONFIRM/REJECT_SUGGESTION）可携带supplied_entity_fields。"
                )
            if len(self.supplied_entity_fields) != len(
                set(self.supplied_entity_fields)
            ):
                raise ValueError("supplied_entity_fields不得重复。")
            if any(not f.strip() for f in self.supplied_entity_fields):
                raise ValueError("supplied_entity_fields不能包含空字段名。")

        if self.action_type == ClarificationActionType.CREATE:
            if self.question is None or not self.question.strip():
                raise ValueError("CREATE动作必须包含问题文本。")
            if not self.missing_fields and not self.requires_confirmation:
                raise ValueError("CREATE动作必须有缺失字段或确认请求。")
            if not self.requires_evidence_persistence:
                raise ValueError("CREATE动作必须先要求保存来源ASR证据。")
        elif (
            self.question is not None
            or self.missing_fields
            or self.requires_confirmation
        ):
            raise ValueError("非CREATE动作不能夹带新问题字段。")

        protocol_scope = (
            self.protocol_id,
            self.protocol_version,
            self.protocol_step_number,
        )
        if any(value is not None for value in protocol_scope):
            if self.action_type != ClarificationActionType.CREATE:
                raise ValueError("只有CREATE动作可以设置新问题的方案归属。")
            if any(value is None for value in protocol_scope):
                raise ValueError("方案归属必须同时包含方案、版本和步骤号。")
            if not self.protocol_id.strip() or not self.protocol_version.strip():
                raise ValueError("方案归属身份不能为空。")
            if self.protocol_step_number <= 0:
                raise ValueError("方案归属步骤号必须为正整数。")


class ClarificationActionPlanner:
    """只规划动作，不读取或修改ReplyCoordinator。"""

    @classmethod
    def from_dispatch(
        cls,
        request: DispatchExecutionRequest,
        context: ClarificationContextSnapshot,
    ) -> ClarificationAction:
        if request.permission == UnifiedDispatchPermission.NO_ACTION:
            if request.destination != UnifiedDispatchDestination.ABSTENTION:
                raise ValueError("NO_ACTION必须来自abstention分派。")
            return cls._no_action(
                request,
                "风险策略明确弃权，不能根据模型候选修改待确认状态。",
            )
        if (
            request.destination
            != UnifiedDispatchDestination.CLARIFICATION_CONTEXT
            or request.permission
            != UnifiedDispatchPermission.FORWARD_CONTEXT_CANDIDATE
        ):
            raise ValueError("待确认动作只能接收上下文分派或安全弃权。")

        command = cls._command_from_request(request)
        # LLM 路径可能已在一次调用中完成实体提取
        supplied_entities = cls._extract_supplied_entities(request)
        command_type = command.command_type
        if command_type == InteractionCommandType.REVIEW_PENDING:
            return cls._build(
                request,
                ClarificationActionType.REVIEW,
                reason="只读查看当前未解决问题。",
                requires_evidence_persistence=True,
            )
        if command_type == InteractionCommandType.DEFER_CURRENT:
            return cls._target_or_no_action(
                request,
                context.current,
                ClarificationActionType.DEFER,
                reason="准备暂缓当前ACTIVE问题。",
            )
        if command_type == InteractionCommandType.DEFER_TARGETED:
            number = command.target_question_number
            target = (
                context.find_by_number(number)
                if number is not None
                else None
            )
            return cls._target_or_no_action(
                request,
                target,
                ClarificationActionType.DEFER,
                reason="准备按编号暂缓指定问题。",
            )
        if command_type == InteractionCommandType.REACTIVATE_TARGETED:
            number = command.target_question_number
            target = context.find_by_number(number) if number is not None else None
            if target is None:
                return cls._no_action(request, "指定的问题编号不存在。")
            if target.status.value != "deferred":
                return cls._no_action(request, "指定问题当前不是已暂缓状态。")
            return cls._target_or_no_action(
                request,
                target,
                ClarificationActionType.REACTIVATE,
                reason="准备按编号恢复已暂缓问题。",
            )
        if command_type in {
            InteractionCommandType.AFFIRM,
            InteractionCommandType.DENY,
        }:
            target = context.current
            if target is None or not target.requires_confirmation:
                return cls._no_action(
                    request,
                    "当前没有可确认或否定的ACTIVE建议。",
                )
            action_type = (
                ClarificationActionType.CONFIRM
                if command_type == InteractionCommandType.AFFIRM
                else ClarificationActionType.REJECT_SUGGESTION
            )
            return cls._target_or_no_action(
                request,
                target,
                action_type,
                answer_text=command.answer_text or command.raw_text,
                supplied_entity_fields=supplied_entities,
                reason="准备处理当前问题的明确确认答复。",
            )
        if command_type == InteractionCommandType.TARGETED_ANSWER:
            number = command.target_question_number
            target = (
                context.find_by_number(number)
                if number is not None
                else None
            )
            if target is None:
                return cls._no_action(request, "指定的问题编号不存在。")
            if not command.answer_text:
                return cls._no_action(request, "指定问题答复缺少答案内容。")
            action_type = (
                ClarificationActionType.CONFIRM
                if target.requires_confirmation
                and _is_explicit_confirmation(command.answer_text)
                else ClarificationActionType.ANSWER
            )
            return cls._target_or_no_action(
                request,
                target,
                action_type,
                answer_text=command.answer_text,
                supplied_entity_fields=supplied_entities,
                reason="准备把明确编号的答复交给目标问题。",
            )
        raise ValueError("该控制类型不属于待确认动作采用范围。")

    @classmethod
    def from_end_confirmation(
        cls,
        request: DispatchExecutionRequest,
    ) -> ClarificationAction:
        """结束确认不是待确认问题动作，只产生无副作用的 NO_ACTION。"""

        return cls._no_action(
            request,
            "LLM 识别到结束意图，需用户确认后才能结束会话。",
        )

    @classmethod
    def from_end_execution(
        cls,
        request: DispatchExecutionRequest,
    ) -> ClarificationAction:
        """精确结束命令不是澄清问题，只产生显式结束计划。"""

        return cls._no_action(
            request,
            "已采用用户的精确结束实验记录命令。",
        )

    @classmethod
    def from_protocol_navigation(
        cls,
        request: DispatchExecutionRequest,
    ) -> ClarificationAction:
        """方案导航不修改待确认问题，只留下可审计的无动作计划。"""

        return cls._no_action(
            request,
            "已采用用户的精确下一步命令，交由方案导航边界处理。",
        )

    @classmethod
    def from_experiment(
        cls,
        accepted: AcceptedExperimentAnalysis,
    ) -> ClarificationAction:
        if accepted.kind == ExperimentAcceptanceKind.DEGRADED_EVIDENCE_NOTE:
            return cls._no_action_from_accepted(
                accepted,
                "降级NOTE只保留证据，不自动创建待确认问题。",
            )
        analysis = accepted.materialize_analysis()
        if not analysis.should_ask_follow_up:
            return cls._no_action_from_accepted(
                accepted,
                "实验分析不需要追问。",
            )
        question = analysis.follow_up_question
        if question is None or not question.strip():
            raise ValueError("需要追问的已采用分析缺少问题文本。")
        missing_fields: list[str] = []
        requires_confirmation = False
        for event in analysis.events:
            for field_name in event.missing_fields:
                if field_name not in missing_fields:
                    missing_fields.append(field_name)
            requires_confirmation |= event.needs_confirmation
        return ClarificationAction(
            request_id=accepted.request_id,
            session_id=accepted.session_id,
            segment_id=accepted.segment_id,
            asr_transcript=accepted.asr_transcript,
            action_type=ClarificationActionType.CREATE,
            mutation_permission=ClarificationMutationPermission.PREPARE_CREATE,
            reason="已采用实验分析需要创建一个可追溯问题。",
            requires_evidence_persistence=True,
            question=question,
            missing_fields=tuple(missing_fields),
            requires_confirmation=requires_confirmation,
        )

    @classmethod
    def _extract_supplied_entities(
        cls,
        request: DispatchExecutionRequest,
    ) -> tuple[str, ...]:
        route = request.plan.route_result
        if route.exact_command is not None:
            return ()  # 精确路径没有 LLM 提取的实体
        understanding = route.understanding_outcome.value
        if understanding.control is not None:
            return understanding.control.supplied_entities
        return ()

    @classmethod
    def _command_from_request(
        cls,
        request: DispatchExecutionRequest,
    ) -> InteractionCommand:
        route = request.plan.route_result
        if route.exact_command is not None:
            return route.exact_command
        understanding = route.understanding_outcome.value
        candidate = understanding.control.intent
        return InteractionCommand(
            command_type=candidate.command_type,
            raw_text=request.raw_text,
            normalized_text=request.raw_text,
            target_question_number=candidate.target_question_number,
            answer_text=candidate.answer_text,
        )

    @classmethod
    def _target_or_no_action(
        cls,
        request: DispatchExecutionRequest,
        target: PendingClarification | None,
        action_type: ClarificationActionType,
        *,
        reason: str,
        answer_text: str | None = None,
        supplied_entity_fields: tuple[str, ...] = (),
    ) -> ClarificationAction:
        if target is None:
            return cls._no_action(request, "当前没有符合条件的目标问题。")
        return cls._build(
            request,
            action_type,
            reason=reason,
            requires_evidence_persistence=True,
            target=target,
            answer_text=answer_text,
            supplied_entity_fields=supplied_entity_fields,
        )

    @staticmethod
    def _build(
        request: DispatchExecutionRequest,
        action_type: ClarificationActionType,
        *,
        reason: str,
        requires_evidence_persistence: bool,
        target: PendingClarification | None = None,
        answer_text: str | None = None,
        supplied_entity_fields: tuple[str, ...] = (),
    ) -> ClarificationAction:
        return ClarificationAction(
            request_id=request.request_id,
            session_id=request.session_id,
            segment_id=request.segment_id,
            asr_transcript=request.raw_text,
            action_type=action_type,
            mutation_permission=_ACTION_PERMISSIONS[action_type],
            reason=reason,
            requires_evidence_persistence=requires_evidence_persistence,
            supplied_entity_fields=supplied_entity_fields,
            target_clarification_id=(
                target.clarification_id if target is not None else None
            ),
            target_display_number=(
                target.display_number if target is not None else None
            ),
            expected_revision=(target.revision if target is not None else None),
            answer_text=answer_text,
        )

    @classmethod
    def _no_action(
        cls,
        request: DispatchExecutionRequest,
        reason: str,
    ) -> ClarificationAction:
        return cls._build(
            request,
            ClarificationActionType.NO_ACTION,
            reason=reason,
            requires_evidence_persistence=False,
        )

    @staticmethod
    def _no_action_from_accepted(
        accepted: AcceptedExperimentAnalysis,
        reason: str,
    ) -> ClarificationAction:
        return ClarificationAction(
            request_id=accepted.request_id,
            session_id=accepted.session_id,
            segment_id=accepted.segment_id,
            asr_transcript=accepted.asr_transcript,
            action_type=ClarificationActionType.NO_ACTION,
            mutation_permission=ClarificationMutationPermission.NONE,
            reason=reason,
            requires_evidence_persistence=False,
        )


def _is_explicit_confirmation(answer_text: str) -> bool:
    normalized = answer_text.strip()
    return normalized in {"是", "是的", "对", "对的", "确认", "没错", "正确"}
