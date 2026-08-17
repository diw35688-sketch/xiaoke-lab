"""把已验证的ClarificationAction安全转换为ReplyCoordinator状态变更。"""

from __future__ import annotations

import json
from dataclasses import dataclass

from src.core.clarification_acceptance import (
    ClarificationAction,
    ClarificationActionType,
    ClarificationMutationPermission,
)
from src.core.reply_coordinator import ReplyCoordinator


_ANSWER_ENTITY_EXTRACTION_PROMPT = """\
从用户回答中提取实验实体字段的值。只返回一个JSON对象，不要输出其他内容。
每个字段的值只能是非空字符串或null；数值也保留为字符串。
{
  "action": null,
  "object": null,
  "instrument": null,
  "amount_value": null,
  "amount_unit": null,
  "concentration": null,
  "temperature": null,
  "duration": null,
  "condition": null,
  "observation": null
}"""

_ENTITY_FIELDS = frozenset({
    "action", "object", "instrument",
    "amount_value", "amount_unit", "concentration",
    "temperature", "duration", "condition", "observation",
})


class AnswerEntityExtractor:
    """用轻量LLM调用从用户回答中提取实体字段名。"""

    def __init__(self, llm_client) -> None:
        self._client = llm_client

    def extract(self, answer_text: str) -> set[str]:
        """返回 answer_text 中出现的非空实体字段名集合。"""

        user_prompt = json.dumps(
            {"answer_text": answer_text},
            ensure_ascii=False,
        )
        generation = self._client.generate_json(
            system_prompt=_ANSWER_ENTITY_EXTRACTION_PROMPT,
            user_prompt=user_prompt,
        )
        try:
            data = json.loads(generation.content)
        except json.JSONDecodeError:
            return set()
        if not isinstance(data, dict):
            return set()

        supplied: set[str] = set()
        for field_name in _ENTITY_FIELDS:
            value = data.get(field_name)
            if isinstance(value, str) and value.strip():
                supplied.add(field_name)
        return supplied


_STATE_CHANGING_ACTIONS = frozenset({
    ClarificationActionType.CREATE,
    ClarificationActionType.DEFER,
    ClarificationActionType.ANSWER,
    ClarificationActionType.CONFIRM,
    ClarificationActionType.REJECT_SUGGESTION,
})


@dataclass(frozen=True)
class ClarificationExecutionResult:
    """一次动作执行的结果，无论成功、被拒绝还是跳过。"""

    request_id: str
    session_id: str
    segment_id: int
    action_type: ClarificationActionType
    state_changed: bool
    reason: str
    affected_clarification_id: str | None = None
    affected_display_number: int | None = None
    answer_text_received: bool = False
    remaining_fields: tuple[str, ...] = ()
    resolved: bool = False


class ClarificationExecutor:
    """只把已验证的ClarificationAction翻译成ReplyCoordinator调用。"""

    def __init__(
        self,
        reply_coordinator: ReplyCoordinator,
        entity_extractor: AnswerEntityExtractor | None = None,
    ) -> None:
        self._coordinator = reply_coordinator
        self._entity_extractor = entity_extractor

    def execute(
        self,
        action: ClarificationAction,
    ) -> ClarificationExecutionResult:
        self._validate_action(action)

        if action.action_type == ClarificationActionType.NO_ACTION:
            return self._result(action, state_changed=False,
                                reason="NO_ACTION 无需状态变更。")

        if action.action_type == ClarificationActionType.REVIEW:
            return self._result(action, state_changed=False,
                                reason="REVIEW 是只读动作，不产生状态变更。")

        if action.action_type == ClarificationActionType.CREATE:
            return self._execute_create(action)

        if action.action_type == ClarificationActionType.DEFER:
            return self._execute_targeted(action, "defer")

        if action.action_type == ClarificationActionType.ANSWER:
            return self._execute_answer(action)

        if action.action_type == ClarificationActionType.CONFIRM:
            return self._execute_confirm(action)

        if action.action_type == ClarificationActionType.REJECT_SUGGESTION:
            return self._execute_targeted(action, "confirm")

        raise ValueError(f"未知动作类型：{action.action_type}")

    def _execute_create(
        self,
        action: ClarificationAction,
    ) -> ClarificationExecutionResult:
        new = self._coordinator.register_clarification(
            segment_id=action.segment_id,
            raw_text=action.asr_transcript,
            question=action.question,
            missing_fields=action.missing_fields,
            requires_confirmation=action.requires_confirmation,
            clarification_id_prefix="unified",
        )
        return self._result(
            action,
            state_changed=True,
            reason=(
                f"已创建待确认问题 {new.display_number}："
                f"{new.question}"
            ),
            affected_clarification_id=new.clarification_id,
            affected_display_number=new.display_number,
        )

    def _execute_targeted(
        self,
        action: ClarificationAction,
        operation: str,
    ) -> ClarificationExecutionResult:
        try:
            if operation == "defer":
                updated = self._coordinator.defer_clarification(
                    clarification_id=action.target_clarification_id,
                    expected_revision=action.expected_revision,
                    segment_id=action.segment_id,
                )
            else:
                updated = self._coordinator.confirm_clarification(
                    clarification_id=action.target_clarification_id,
                    expected_revision=action.expected_revision,
                    segment_id=action.segment_id,
                )
        except ValueError as error:
            return self._result(
                action,
                state_changed=False,
                reason=str(error),
            )

        return self._result(
            action,
            state_changed=True,
            reason=(
                f"{action.action_type.value} 操作完成，"
                f"问题 {updated.display_number} 状态已更新。"
            ),
            affected_clarification_id=updated.clarification_id,
            affected_display_number=updated.display_number,
        )

    def _execute_confirm(
        self,
        action: ClarificationAction,
    ) -> ClarificationExecutionResult:
        try:
            target = self._coordinator._find_clarification(
                action.target_clarification_id,
            )
            if target is None:
                return self._result(
                    action,
                    state_changed=False,
                    reason=f"未找到目标问题：{action.target_clarification_id}",
                )
            if target.revision != action.expected_revision:
                return self._result(
                    action,
                    state_changed=False,
                    reason=(
                        f"待确认项版本已变更（期望 {action.expected_revision}，"
                        f"当前 {target.revision}），拒绝过期确认。"
                    ),
                )
            if not target.is_active:
                return self._result(
                    action,
                    state_changed=False,
                    reason="只能确认 ACTIVE 状态的待确认项。",
                )
            if not target.requires_confirmation:
                return self._result(
                    action,
                    state_changed=False,
                    reason="待确认项不需要确认。",
                )
        except ValueError as error:
            return self._result(
                action,
                state_changed=False,
                reason=str(error),
            )

        supplied_fields: set[str] = set()
        if action.supplied_entity_fields:
            supplied_fields = set(action.supplied_entity_fields)
        elif self._entity_extractor is not None and action.answer_text:
            supplied_fields = self._entity_extractor.extract(
                action.answer_text
            )

        updated = target
        if supplied_fields:
            try:
                updated = self._coordinator.answer_clarification(
                    clarification_id=action.target_clarification_id,
                    expected_revision=action.expected_revision,
                    segment_id=action.segment_id,
                    supplied_fields=supplied_fields,
                )
            except ValueError as error:
                return self._result(
                    action,
                    state_changed=False,
                    reason=str(error),
                )

        try:
            updated = self._coordinator.confirm_clarification(
                clarification_id=action.target_clarification_id,
                expected_revision=updated.revision,
                segment_id=action.segment_id,
            )
        except ValueError as error:
            return self._result(
                action,
                state_changed=False,
                reason=str(error),
            )

        if not updated.is_unresolved:
            resolved_note = " 问题已解决。"
            resolved = True
            remaining_fields: tuple[str, ...] = ()
        elif updated.missing_fields:
            resolved_note = (
                f" 仍需补充：{'、'.join(updated.missing_fields)}。"
            )
            resolved = False
            remaining_fields = tuple(updated.missing_fields)
        else:
            resolved_note = ""
            resolved = False
            remaining_fields = ()

        if supplied_fields:
            detail = (
                f"已确认问题 {updated.display_number} 并补充字段"
                f" {sorted(supplied_fields)}。"
                f"{resolved_note}"
            )
        else:
            detail = (
                f"已确认问题 {updated.display_number}。"
                f"{resolved_note}"
            )
        return self._result(
            action,
            state_changed=True,
            reason=detail,
            affected_clarification_id=updated.clarification_id,
            affected_display_number=updated.display_number,
            answer_text_received=bool(supplied_fields),
            remaining_fields=remaining_fields,
            resolved=resolved,
        )

    def _execute_answer(
        self,
        action: ClarificationAction,
    ) -> ClarificationExecutionResult:
        try:
            target = self._coordinator._find_clarification(
                action.target_clarification_id,
            )
            if target is None:
                return self._result(
                    action,
                    state_changed=False,
                    reason=f"未找到目标问题：{action.target_clarification_id}",
                )
            if target.revision != action.expected_revision:
                return self._result(
                    action,
                    state_changed=False,
                    reason=(
                        f"待确认项版本已变更（期望 {action.expected_revision}，"
                        f"当前 {target.revision}），拒绝过期答复。"
                    ),
                )
            if not target.is_active:
                return self._result(
                    action,
                    state_changed=False,
                    reason="只能答复 ACTIVE 状态的待确认项。",
                )
        except ValueError as error:
            return self._result(
                action,
                state_changed=False,
                reason=str(error),
            )

        supplied_fields: set[str] = set()
        if action.supplied_entity_fields:
            # 统一理解在一次LLM调用中已提取实体 → 直接使用
            supplied_fields = set(action.supplied_entity_fields)
        elif self._entity_extractor is not None:
            # 精确路径 → 轻量LLM提取
            supplied_fields = self._entity_extractor.extract(
                action.answer_text
            )
        else:
            return self._result(
                action,
                state_changed=False,
                answer_text_received=True,
                reason=(
                    f"收到对问题 {target.display_number} 的答复"
                    f"\"{action.answer_text}\"，"
                    "但未配置实体提取器，未修改待确认状态。"
                ),
            )

        if not supplied_fields:
            # extractor 返回空或 supplied_entity_fields 为空 → 无字段可填
            return self._result(
                action,
                state_changed=False,
                answer_text_received=True,
                reason=(
                    f"收到对问题 {target.display_number} 的答复"
                    f"\"{action.answer_text}\"，"
                    "但未从中提取到实体字段。"
                ),
            )

        try:
            updated = self._coordinator.answer_clarification(
                clarification_id=action.target_clarification_id,
                expected_revision=action.expected_revision,
                segment_id=action.segment_id,
                supplied_fields=supplied_fields,
            )
        except ValueError as error:
            return self._result(
                action,
                state_changed=False,
                reason=str(error),
            )

        if not updated.is_unresolved:
            resolved_note = " 问题已解决。"
            resolved = True
            remaining_fields: tuple[str, ...] = ()
        elif updated.missing_fields:
            resolved_note = (
                f" 仍需补充：{'、'.join(updated.missing_fields)}。"
            )
            resolved = False
            remaining_fields = tuple(updated.missing_fields)
        else:
            # 字段已补齐但确认尚未完成（requires_confirmation），
            # 不能说"仍需补充：空"，应明确"仍需确认"。
            resolved_note = " 仍需确认。"
            resolved = False
            remaining_fields = ()
        return self._result(
            action,
            state_changed=(updated != target),
            answer_text_received=True,
            reason=(
                f"已将对问题 {updated.display_number} 的答复的实体字段"
                f" {sorted(supplied_fields)} 填入。"
                f"{resolved_note}"
            ),
            affected_clarification_id=updated.clarification_id,
            affected_display_number=updated.display_number,
            remaining_fields=remaining_fields,
            resolved=resolved,
        )

    def _validate_action(self, action: ClarificationAction) -> None:
        if (
            action.action_type in _STATE_CHANGING_ACTIONS
            and not action.requires_evidence_persistence
        ):
            raise ValueError(
                f"{action.action_type.value} 动作要求"
                " requires_evidence_persistence=True，"
                "ClarificationAction 验证层应已拦截此问题。"
            )

    @staticmethod
    def _result(
        action: ClarificationAction,
        *,
        state_changed: bool,
        reason: str,
        affected_clarification_id: str | None = None,
        affected_display_number: int | None = None,
        answer_text_received: bool = False,
        remaining_fields: tuple[str, ...] = (),
        resolved: bool = False,
    ) -> ClarificationExecutionResult:
        return ClarificationExecutionResult(
            request_id=action.request_id,
            session_id=action.session_id,
            segment_id=action.segment_id,
            action_type=action.action_type,
            state_changed=state_changed,
            reason=reason,
            affected_clarification_id=affected_clarification_id,
            affected_display_number=affected_display_number,
            answer_text_received=answer_text_received,
            remaining_fields=remaining_fields,
            resolved=resolved,
        )
