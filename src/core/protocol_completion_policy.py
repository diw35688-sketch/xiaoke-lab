"""Deterministic multi-turn completion policy for one protocol step."""

from __future__ import annotations

from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Mapping

from src.core.clarification_acceptance import (
    ClarificationAction,
    ClarificationActionType,
    ClarificationMutationPermission,
)
from src.core.experiment_acceptance import AcceptedExperimentAnalysis
from src.core.pending_clarification import PendingClarification


@dataclass(frozen=True)
class ObservedFieldValue:
    value: str
    request_id: str
    segment_id: int

    def __post_init__(self) -> None:
        if not self.value.strip() or not self.request_id.strip():
            raise ValueError("累计字段值和 request_id 不能为空。")
        if self.segment_id <= 0:
            raise ValueError("累计字段的 segment_id 必须为正整数。")

    def to_snapshot(self) -> dict[str, object]:
        return {
            "value": self.value,
            "request_id": self.request_id,
            "segment_id": self.segment_id,
        }


@dataclass(frozen=True)
class ProtocolStepFactState:
    protocol_id: str
    protocol_version: str
    step_number: int
    values: Mapping[str, ObservedFieldValue]
    clarification_id: str | None = None

    def __post_init__(self) -> None:
        if not self.protocol_id.strip() or not self.protocol_version.strip():
            raise ValueError("方案身份不能为空。")
        if self.step_number <= 0:
            raise ValueError("方案步骤号必须为正整数。")
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))

    @classmethod
    def empty(
        cls, *, protocol_id: str, protocol_version: str, step_number: int
    ) -> "ProtocolStepFactState":
        return cls(protocol_id, protocol_version, step_number, {})

    @classmethod
    def from_snapshot(
        cls,
        snapshot: Mapping[str, object] | None,
        *,
        protocol_id: str,
        protocol_version: str,
        step_number: int,
    ) -> "ProtocolStepFactState":
        if not snapshot or (
            snapshot.get("protocol_id") != protocol_id
            or snapshot.get("protocol_version") != protocol_version
            or snapshot.get("step_number") != step_number
        ):
            return cls.empty(
                protocol_id=protocol_id,
                protocol_version=protocol_version,
                step_number=step_number,
            )
        raw_values = snapshot.get("values") or {}
        if not isinstance(raw_values, Mapping):
            raise TypeError("protocol_step_facts.values 必须是映射。")
        values = {
            str(name): ObservedFieldValue(
                value=str(item["value"]),
                request_id=str(item["request_id"]),
                segment_id=int(item["segment_id"]),
            )
            for name, item in raw_values.items()
            if isinstance(item, Mapping)
        }
        clarification_id = snapshot.get("clarification_id")
        return cls(
            protocol_id=protocol_id,
            protocol_version=protocol_version,
            step_number=step_number,
            values=values,
            clarification_id=(
                str(clarification_id) if clarification_id is not None else None
            ),
        )

    def merge(
        self,
        contribution: Mapping[str, str],
        *,
        request_id: str,
        segment_id: int,
    ) -> tuple["ProtocolStepFactState", tuple[str, ...]]:
        """Fill empty fields; preserve an older conflicting value for confirmation."""

        merged = dict(self.values)
        conflicts: list[str] = []
        for name, raw_value in contribution.items():
            value = raw_value.strip() if isinstance(raw_value, str) else ""
            if not value:
                continue
            previous = merged.get(name)
            if previous is None:
                merged[name] = ObservedFieldValue(value, request_id, segment_id)
            elif previous.value != value:
                conflicts.append(name)
        return replace(self, values=merged), tuple(conflicts)

    def entity_values(self) -> dict[str, str]:
        return {name: item.value for name, item in self.values.items()}

    def to_snapshot(self) -> dict[str, object]:
        return {
            "protocol_id": self.protocol_id,
            "protocol_version": self.protocol_version,
            "step_number": self.step_number,
            "values": {
                name: item.to_snapshot() for name, item in self.values.items()
            },
            "clarification_id": self.clarification_id,
        }


@dataclass(frozen=True)
class ResolvedProtocolCompletion:
    state: ProtocolStepFactState
    missing_fields: tuple[str, ...]
    deviations: tuple[Mapping[str, object], ...]
    follow_up_required: bool
    follow_up_question: str | None
    action: ClarificationAction | None
    conflicting_fields: tuple[str, ...] = ()


def resolve_protocol_completion(
    *,
    accepted: AcceptedExperimentAnalysis,
    state: ProtocolStepFactState,
    evaluation: Mapping[str, object],
    existing: PendingClarification | None,
    conflicting_fields: tuple[str, ...] = (),
) -> ResolvedProtocolCompletion:
    """Turn one cumulative evaluation into the single final clarification action."""

    missing = tuple(str(item) for item in evaluation.get("missing_fields") or ())
    required = bool(evaluation.get("follow_up_required"))
    question_value = evaluation.get("follow_up_question")
    question = str(question_value) if question_value else None
    deviations = tuple(
        item for item in (evaluation.get("deviations") or ())
        if isinstance(item, Mapping)
    )

    action = None
    if existing is not None and existing.is_unresolved:
        newly_completed = tuple(
            field for field in existing.missing_fields if field not in missing
        )
        if newly_completed:
            action = ClarificationAction(
                request_id=accepted.request_id,
                session_id=accepted.session_id,
                segment_id=accepted.segment_id,
                asr_transcript=accepted.asr_transcript,
                action_type=ClarificationActionType.ANSWER,
                mutation_permission=ClarificationMutationPermission.PREPARE_UPDATE,
                reason="累计实验事实补充了当前方案步骤的待确认字段。",
                requires_evidence_persistence=True,
                target_clarification_id=existing.clarification_id,
                target_display_number=existing.display_number,
                expected_revision=existing.revision,
                answer_text=accepted.asr_transcript,
                supplied_entity_fields=newly_completed,
            )
    elif required:
        if question is None or not question.strip():
            raise ValueError("方案评价要求追问，但缺少确定性问题文本。")
        action = ClarificationAction(
            request_id=accepted.request_id,
            session_id=accepted.session_id,
            segment_id=accepted.segment_id,
            asr_transcript=accepted.asr_transcript,
            action_type=ClarificationActionType.CREATE,
            mutation_permission=ClarificationMutationPermission.PREPARE_CREATE,
            reason="当前方案步骤仍缺少 must_record 字段。",
            requires_evidence_persistence=True,
            question=question,
            missing_fields=missing,
            protocol_id=state.protocol_id,
            protocol_version=state.protocol_version,
            protocol_step_number=state.step_number,
        )

    return ResolvedProtocolCompletion(
        state=state,
        missing_fields=missing,
        deviations=deviations,
        follow_up_required=required,
        follow_up_question=question,
        action=action,
        conflicting_fields=conflicting_fields,
    )
