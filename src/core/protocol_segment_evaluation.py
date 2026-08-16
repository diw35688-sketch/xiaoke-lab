"""把方案步骤评估结果适配成追问链可消费的纯数据。"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from src.core.protocol import ProtocolStep, SourcedFieldValue, materialize_field_values
from src.core.protocol_deviations import ProtocolDeviation, detect_protocol_deviations
from src.core.protocol_missing_fields import compute_missing_fields
from src.core.protocol_session import ProtocolSessionState
from src.llm.schemas import ExperimentEntities


_NO_PROMPT_FALLBACK = "请补充现场记录：{field_name}。"


@dataclass(frozen=True)
class SegmentEvaluation:
    """一次口述实体相对于当前方案步骤的确定性评估。"""

    missing_fields: tuple[str, ...]
    follow_up_question: str | None
    deviations: tuple[ProtocolDeviation, ...]
    sourced_values: Mapping[str, SourcedFieldValue]
    follow_up_required: bool


def evaluate_segment(
    state: ProtocolSessionState,
    entities: ExperimentEntities,
) -> SegmentEvaluation:
    """评估一段实体；自由模式完全不让方案介入旧链路。"""

    if not isinstance(state, ProtocolSessionState):
        raise TypeError("state必须是ProtocolSessionState。")
    if not isinstance(entities, ExperimentEntities):
        raise TypeError("entities必须是ExperimentEntities。")

    step = state.current_step()
    if step is None:
        return SegmentEvaluation(
            missing_fields=(),
            follow_up_question=None,
            deviations=(),
            sourced_values=MappingProxyType({}),
            follow_up_required=False,
        )

    missing_fields = compute_missing_fields(step, entities)
    deviations = detect_protocol_deviations(step, entities)
    sourced_values = materialize_field_values(step, entities)
    question = _build_follow_up_question(step, missing_fields)
    return SegmentEvaluation(
        missing_fields=missing_fields,
        follow_up_question=question,
        deviations=deviations,
        sourced_values=sourced_values,
        follow_up_required=bool(missing_fields),
    )


def _build_follow_up_question(step: ProtocolStep, missing_fields: tuple[str, ...]) -> str | None:
    if not missing_fields:
        return None
    prompts = [
        step.field_prompts.get(
            field_name, _NO_PROMPT_FALLBACK.format(field_name=field_name)
        )
        for field_name in missing_fields
    ]
    if len(prompts) == 1:
        return prompts[0]
    return " ".join(prompts)
