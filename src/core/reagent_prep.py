# -*- coding: utf-8 -*-
"""试剂配置库的数据合同：一种可配制的常用试剂/缓冲液。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


class ReagentPrepError(ValueError):
    """试剂配置数据不满足正式合同。"""


def _require_non_blank_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReagentPrepError(f"{field_name}不能为空。")
    return value.strip()


def _normalize_string_or_none(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_non_blank_string(value, field_name)


@dataclass(frozen=True)
class ReagentPrep:
    """一条只读试剂配置方案。

    只保存“怎么配”，不保存“谁配过、什么时候配的”这类运行数据。
    """

    reagent_prep_id: str
    name_zh: str
    purpose: str
    target_concentration: str | None
    target_volume: str | None
    solvent: str | None
    steps: tuple[str, ...]
    storage_condition: str | None
    expiry: str | None
    hazard_reagents: tuple[str, ...]
    source: str
    source_url: str | None
    review_status: str

    def __post_init__(self) -> None:
        _require_non_blank_string(self.reagent_prep_id, "reagent_prep_id")
        _require_non_blank_string(self.name_zh, "name_zh")
        _require_non_blank_string(self.purpose, "purpose")
        object.__setattr__(
            self,
            "target_concentration",
            _normalize_string_or_none(
                self.target_concentration, "target_concentration"
            ),
        )
        object.__setattr__(
            self,
            "target_volume",
            _normalize_string_or_none(self.target_volume, "target_volume"),
        )
        object.__setattr__(
            self,
            "solvent",
            _normalize_string_or_none(self.solvent, "solvent"),
        )
        if not isinstance(self.steps, tuple):
            raise ReagentPrepError("steps 必须是字符串元组。")
        if not self.steps:
            raise ReagentPrepError("steps 不能为空。")
        normalized_steps = tuple(
            _require_non_blank_string(step, f"steps[{index}]")
            for index, step in enumerate(self.steps, start=1)
        )
        object.__setattr__(self, "steps", normalized_steps)
        object.__setattr__(
            self,
            "storage_condition",
            _normalize_string_or_none(
                self.storage_condition, "storage_condition"
            ),
        )
        object.__setattr__(
            self,
            "expiry",
            _normalize_string_or_none(self.expiry, "expiry"),
        )
        if not isinstance(self.hazard_reagents, tuple):
            raise ReagentPrepError("hazard_reagents 必须是元组。")
        normalized_hazards = tuple(
            _require_non_blank_string(item, "hazard_reagents")
            for item in self.hazard_reagents
        )
        if len(normalized_hazards) != len(set(normalized_hazards)):
            raise ReagentPrepError("hazard_reagents 不得重复。")
        object.__setattr__(self, "hazard_reagents", normalized_hazards)
        _require_non_blank_string(self.source, "source")
        object.__setattr__(
            self,
            "source_url",
            _normalize_string_or_none(self.source_url, "source_url"),
        )
        if self.review_status not in {"UNREVIEWED", "REVIEWED"}:
            raise ReagentPrepError(
                "review_status 只能是 UNREVIEWED 或 REVIEWED。"
            )

    def to_dict(self) -> dict:
        """转回 JSON 可写结构。"""

        return {
            "reagent_prep_id": self.reagent_prep_id,
            "name_zh": self.name_zh,
            "purpose": self.purpose,
            "target_concentration": self.target_concentration,
            "target_volume": self.target_volume,
            "solvent": self.solvent,
            "steps": list(self.steps),
            "storage_condition": self.storage_condition,
            "expiry": self.expiry,
            "hazard_reagents": list(self.hazard_reagents),
            "source": self.source,
            "source_url": self.source_url,
            "review_status": self.review_status,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "ReagentPrep":
        if not isinstance(data, dict):
            raise ReagentPrepError("试剂配置项必须是 JSON 对象。")
        return cls(
            reagent_prep_id=data.get("reagent_prep_id", ""),
            name_zh=data.get("name_zh", ""),
            purpose=data.get("purpose", ""),
            target_concentration=data.get("target_concentration"),
            target_volume=data.get("target_volume"),
            solvent=data.get("solvent"),
            steps=tuple(data.get("steps", [])),
            storage_condition=data.get("storage_condition"),
            expiry=data.get("expiry"),
            hazard_reagents=tuple(data.get("hazard_reagents", [])),
            source=data.get("source", ""),
            source_url=data.get("source_url"),
            review_status=data.get("review_status", "UNREVIEWED"),
        )
