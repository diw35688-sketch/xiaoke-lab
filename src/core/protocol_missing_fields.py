"""根据实验方案步骤确定性计算尚未提供的现场实测字段。"""

from __future__ import annotations

from collections.abc import Set
from dataclasses import fields

from src.core.protocol import EXPERIMENT_ENTITY_FIELD_NAMES, ProtocolError, ProtocolStep
from src.llm.schemas import ExperimentEntities


def compute_missing_fields(
    step: ProtocolStep,
    provided_entities: ExperimentEntities | Set[str],
) -> tuple[str, ...]:
    """只按must_record原顺序返回尚未提供的现场实测字段。"""

    if not isinstance(step, ProtocolStep):
        raise ProtocolError("step必须是ProtocolStep。")
    if not step.must_record:
        return ()
    provided_fields = _provided_field_names(provided_entities)
    return tuple(
        field_name for field_name in step.must_record if field_name not in provided_fields
    )


def _provided_field_names(
    provided_entities: ExperimentEntities | Set[str],
) -> frozenset[str]:
    if isinstance(provided_entities, ExperimentEntities):
        provided: set[str] = set()
        for field_info in fields(ExperimentEntities):
            value = getattr(provided_entities, field_info.name)
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            provided.add(field_info.name)
        return frozenset(provided)
    if not isinstance(provided_entities, Set) or isinstance(provided_entities, (str, bytes)):
        raise ProtocolError("provided_entities必须是ExperimentEntities或字段名集合。")
    invalid_types = sorted(repr(field_name) for field_name in provided_entities if not isinstance(field_name, str))
    if invalid_types:
        raise ProtocolError(f"已提供字段名必须是字符串：{invalid_types}")
    unknown = sorted(set(provided_entities) - EXPERIMENT_ENTITY_FIELD_NAMES)
    if unknown:
        raise ProtocolError(f"已提供字段集合包含未知实体字段：{unknown}")
    return frozenset(provided_entities)
