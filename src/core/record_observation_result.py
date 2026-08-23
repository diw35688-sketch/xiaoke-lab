"""实验口述成功落盘后的共享业务结果合同。

该合同供 `/record` 与聊天工具 `record_observation` 共同使用；不包含 HTTP
messages、工具卡片或 TTS 字段。保存失败不构造本对象，由调用方保留异常语义。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class ExtractionSource(str, Enum):
    LLM = "llm"
    RULE = "rule"
    DEGRADED = "degraded"
    NONE = "none"


class RecordStructureStatus(str, Enum):
    STRUCTURED = "structured"
    DEGRADED = "degraded"


@dataclass(frozen=True)
class RecordObservationResult:
    """一段口述已成功保存后，可供呈现层和不同入口复用的事实。"""

    session_id: str
    segment_id: int
    transcript: str
    entities: Mapping[str, str]
    extraction_source: ExtractionSource
    structure_status: RecordStructureStatus
    missing_fields: tuple[str, ...] = ()
    follow_up_question: str | None = None
    deviations: tuple[Mapping[str, object], ...] = ()

    def __post_init__(self) -> None:
        if not self.session_id.strip():
            raise ValueError("session_id 不能为空。")
        if self.segment_id <= 0 or isinstance(self.segment_id, bool):
            raise ValueError("segment_id 必须是正整数。")
        if not self.transcript.strip():
            raise ValueError("transcript 不能为空。")
        if not isinstance(self.extraction_source, ExtractionSource):
            raise TypeError("extraction_source 必须是 ExtractionSource。")
        if not isinstance(self.structure_status, RecordStructureStatus):
            raise TypeError("structure_status 必须是 RecordStructureStatus。")

        entities = dict(self.entities)
        if any(
            not isinstance(key, str) or not key.strip()
            or not isinstance(value, str) or not value.strip()
            for key, value in entities.items()
        ):
            raise ValueError("entities 必须由非空字符串键值组成。")
        object.__setattr__(self, "entities", MappingProxyType(entities))

        if any(
            not isinstance(field, str) or not field.strip()
            for field in self.missing_fields
        ):
            raise ValueError("missing_fields 只能包含非空字段名。")
        if len(set(self.missing_fields)) != len(self.missing_fields):
            raise ValueError("missing_fields 不能重复。")

        if self.follow_up_question is not None and not self.follow_up_question.strip():
            raise ValueError("follow_up_question 不能是空白字符串。")
        if self.missing_fields and self.follow_up_question is None:
            raise ValueError("存在 missing_fields 时必须提供 follow_up_question。")

        deviations = tuple(MappingProxyType(dict(item)) for item in self.deviations)
        object.__setattr__(self, "deviations", deviations)

        degraded_sources = {ExtractionSource.DEGRADED, ExtractionSource.NONE}
        source_is_degraded = self.extraction_source in degraded_sources
        status_is_degraded = self.structure_status == RecordStructureStatus.DEGRADED
        if source_is_degraded != status_is_degraded:
            raise ValueError("结构化状态必须与抽取来源的降级语义一致。")

    @property
    def persisted(self) -> bool:
        """对象只在保存成功后构造，因此该属性恒为 True。"""

        return True

    def as_dict(self) -> dict:
        """生成入口适配器可继续加工的 JSON 可序列化业务字段。"""

        return {
            "session_id": self.session_id,
            "segment_id": self.segment_id,
            "transcript": self.transcript,
            "entities": dict(self.entities),
            "extraction_source": self.extraction_source.value,
            "structure_status": self.structure_status.value,
            "missing_fields": list(self.missing_fields),
            "follow_up_question": self.follow_up_question,
            "deviations": [dict(item) for item in self.deviations],
            "persisted": True,
        }
