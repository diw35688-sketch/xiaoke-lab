"""实验方案的数据合同与确定性校验规则。"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from src.llm.schemas import ExperimentEntities
from src.core.protocol_value_equivalence import protocol_values_equivalent


PROTOCOL_SCHEMA_VERSION = 1
EXPERIMENT_ENTITY_FIELD_NAMES = frozenset(
    field_info.name for field_info in fields(ExperimentEntities)
)
class ProtocolError(ValueError):
    """实验方案数据不满足正式合同。"""


class FieldValueSource(str, Enum):
    """实体字段值的可审计来源。"""

    SPOKEN = "SPOKEN"
    PROTOCOL_DEFAULT = "PROTOCOL_DEFAULT"
    DEVIATION = "DEVIATION"


def _require_non_blank_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProtocolError(f"{field_name}必须是非空白字符串。")
    return value


def _require_string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise ProtocolError(f"{field_name}必须是字符串元组。")
    for index, item in enumerate(value, start=1):
        _require_non_blank_string(item, f"{field_name}第{index}项")
    return value


def _normalize_field_names(value: object, field_name: str) -> tuple[str, ...]:
    field_names = _require_string_tuple(value, field_name)
    if len(set(field_names)) != len(field_names):
        raise ProtocolError(f"{field_name}不能重复。")
    unknown = sorted(set(field_names) - EXPERIMENT_ENTITY_FIELD_NAMES)
    if unknown:
        raise ProtocolError(f"{field_name}包含未知实体字段：{unknown}")
    return field_names


def _normalize_field_prompts(
    value: object,
    must_record: tuple[str, ...],
) -> Mapping[str, str]:
    """校验字段缺失追问话术，并转换为只读映射。"""

    if not isinstance(value, Mapping):
        raise ProtocolError("field_prompts必须是字段到字符串的映射。")
    normalized: dict[str, str] = {}
    for key, item in value.items():
        _require_non_blank_string(key, "field_prompts字段名")
        if key not in EXPERIMENT_ENTITY_FIELD_NAMES:
            raise ProtocolError(f"field_prompts包含未知实体字段：{key}")
        if key not in must_record:
            raise ProtocolError(
                f"field_prompts.{key}必须同时出现在must_record里；"
                "protocol_values字段不应配置缺失追问。"
            )
        _require_non_blank_string(item, f"field_prompts.{key}")
        normalized[key] = item
    return MappingProxyType(normalized)


def _normalize_protocol_values(
    value: object,
    field_name: str = "protocol_values",
) -> Mapping[str, str]:
    if not isinstance(value, Mapping):
        raise ProtocolError(f"{field_name}必须是字段到字符串的映射。")
    normalized: dict[str, str] = {}
    for key, item in value.items():
        _require_non_blank_string(key, f"{field_name}字段名")
        _require_non_blank_string(item, f"{field_name}.{key}")
        if key not in EXPERIMENT_ENTITY_FIELD_NAMES:
            raise ProtocolError(f"{field_name}包含未知实体字段：{key}")
        normalized[key] = item
    return MappingProxyType(normalized)


def _normalize_value_aliases(
    value: object,
    protocol_values: Mapping[str, str],
) -> Mapping[str, tuple[str, ...]]:
    """Validate step-local aliases; only loaded protocol steps can activate them."""

    if not isinstance(value, Mapping):
        raise ProtocolError("value_aliases必须是字段到字符串元组的映射。")
    normalized: dict[str, tuple[str, ...]] = {}
    for key, aliases in value.items():
        _require_non_blank_string(key, "value_aliases字段名")
        if key not in protocol_values:
            raise ProtocolError(
                f"value_aliases.{key}必须对应本步骤protocol_values中的字段。"
            )
        checked = _require_string_tuple(aliases, f"value_aliases.{key}")
        if len(set(checked)) != len(checked):
            raise ProtocolError(f"value_aliases.{key}不能重复。")
        normalized[key] = checked
    return MappingProxyType(normalized)


@dataclass(frozen=True)
class ProtocolSubStep:
    """一个大步骤下的操作小步。

    小步只描述"怎么做"，不单独承载 must_record：现场必测字段仍归属大步骤，
    避免同一个字段在多个小步之间重复追问。
    """

    order: int
    text: str
    note: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.order, int)
            or isinstance(self.order, bool)
            or self.order <= 0
        ):
            raise ProtocolError("小步 order 必须是从1开始的正整数。")
        _require_non_blank_string(self.text, "小步内容")
        if self.note is not None:
            _require_non_blank_string(self.note, "小步备注")


@dataclass(frozen=True)
class ProtocolStep:
    """一份实验方案中的只读步骤。

    ``protocol_values`` 是方案作者已经写死的目标值，永不触发追问；
    ``must_record`` 是只有本次实验现场才能产生的实测字段，缺失才追问。
    """

    step_number: int
    title: str
    instruction: str
    protocol_values: Mapping[str, str]
    must_record: tuple[str, ...]
    terms: tuple[str, ...]
    hazard_note: str | None
    field_prompts: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    substeps: tuple[ProtocolSubStep, ...] = ()
    value_aliases: Mapping[str, tuple[str, ...]] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def __post_init__(self) -> None:
        if (
            not isinstance(self.step_number, int)
            or isinstance(self.step_number, bool)
            or self.step_number <= 0
        ):
            raise ProtocolError("step_number必须是从1开始的正整数。")
        _require_non_blank_string(self.title, "步骤标题")
        _require_non_blank_string(self.instruction, "步骤原文")
        normalized_must_record = _normalize_field_names(self.must_record, "must_record")
        normalized_protocol_values = _normalize_protocol_values(self.protocol_values)
        normalized_value_aliases = _normalize_value_aliases(
            self.value_aliases, normalized_protocol_values
        )
        normalized_field_prompts = _normalize_field_prompts(
            self.field_prompts, normalized_must_record
        )
        _require_string_tuple(self.terms, "terms")
        if self.hazard_note is not None:
            _require_non_blank_string(self.hazard_note, "hazard_note")
        object.__setattr__(self, "must_record", normalized_must_record)
        object.__setattr__(self, "protocol_values", normalized_protocol_values)
        object.__setattr__(self, "value_aliases", normalized_value_aliases)
        if not isinstance(self.substeps, tuple):
            raise ProtocolError("substeps 必须是 ProtocolSubStep 元组。")
        for index, sub_step in enumerate(self.substeps, start=1):
            if not isinstance(sub_step, ProtocolSubStep):
                raise ProtocolError(f"substeps 第{index}项必须是 ProtocolSubStep。")
            if sub_step.order != index:
                raise ProtocolError(
                    "小步 order 必须从1开始严格连续；"
                    f"第{index}项实际为{sub_step.order}。"
                )
        object.__setattr__(self, "field_prompts", normalized_field_prompts)


@dataclass(frozen=True)
class SourcedFieldValue:
    """不可变的实体字段快照，明确保存值的来源。"""

    field_name: str
    value: str
    source: FieldValueSource

    def __post_init__(self) -> None:
        _require_non_blank_string(self.field_name, "字段名")
        if self.field_name not in EXPERIMENT_ENTITY_FIELD_NAMES:
            raise ProtocolError(f"字段名包含未知实体字段：{self.field_name}")
        _require_non_blank_string(self.value, f"字段值.{self.field_name}")
        if not isinstance(self.source, FieldValueSource):
            raise ProtocolError("source必须是FieldValueSource。")


def _is_present(value: object) -> bool:
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def materialize_field_values(
    step: ProtocolStep,
    actual_entities: ExperimentEntities,
) -> Mapping[str, SourcedFieldValue]:
    """合并现场实体与方案默认值，现场值永远优先且保留来源。"""

    if not isinstance(step, ProtocolStep):
        raise ProtocolError("step必须是ProtocolStep。")
    if not isinstance(actual_entities, ExperimentEntities):
        raise ProtocolError("actual_entities必须是ExperimentEntities。")

    result: dict[str, SourcedFieldValue] = {}
    for field_info in fields(ExperimentEntities):
        field_name = field_info.name
        actual_value = getattr(actual_entities, field_name)
        protocol_value = step.protocol_values.get(field_name)
        if _is_present(actual_value):
            source = (
                FieldValueSource.DEVIATION
                if protocol_value is not None and not protocol_values_equivalent(
                    field_name,
                    protocol_value,
                    actual_value,
                    aliases=step.value_aliases.get(field_name, ()),
                )
                else FieldValueSource.SPOKEN
            )
            result[field_name] = SourcedFieldValue(field_name, actual_value, source)
        elif protocol_value is not None:
            result[field_name] = SourcedFieldValue(
                field_name,
                protocol_value,
                FieldValueSource.PROTOCOL_DEFAULT,
            )
    return MappingProxyType(result)


@dataclass(frozen=True)
class ExperimentProtocol:
    """一份可由程序读取和校验的只读实验方案。"""

    protocol_id: str
    title: str
    source: str
    version: str
    steps: tuple[ProtocolStep, ...]
    schema_version: int

    def __post_init__(self) -> None:
        _require_non_blank_string(self.protocol_id, "protocol_id")
        _require_non_blank_string(self.title, "方案标题")
        _require_non_blank_string(self.source, "方案来源")
        _require_non_blank_string(self.version, "方案版本")
        if not isinstance(self.steps, tuple):
            raise ProtocolError("steps必须是ProtocolStep元组。")
        if not self.steps:
            raise ProtocolError("steps不能为空。")
        for index, step in enumerate(self.steps, start=1):
            if not isinstance(step, ProtocolStep):
                raise ProtocolError(f"steps第{index}项必须是ProtocolStep。")
            if step.step_number != index:
                raise ProtocolError(
                    "step_number必须从1开始严格连续；"
                    f"第{index}项实际为{step.step_number}。"
                )
        if (
            not isinstance(self.schema_version, int)
            or isinstance(self.schema_version, bool)
            or self.schema_version <= 0
        ):
            raise ProtocolError("schema_version必须是正整数。")
