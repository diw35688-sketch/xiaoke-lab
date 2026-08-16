"""试剂安全知识库的严格读取与按文本匹配。

数据事实（CAS、分子式、GHS分类）来自 PubChem，可逐条溯源；
H码中文表述依据 GB 30000 系列。本模块只做读取和匹配，不生成任何安全结论。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from src.config import HAZMAT_FILE, HAZMAT_SCHEMA_VERSION


class HazmatStoreError(ValueError):
    """试剂安全知识库数据不满足正式合同。"""


@dataclass(frozen=True)
class HazardStatement:
    """一条GHS危险性说明。"""

    code: str
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not self.code.strip():
            raise HazmatStoreError("H码必须是非空白字符串。")
        if not isinstance(self.text, str) or not self.text.strip():
            raise HazmatStoreError(f"{self.code}的中文表述不能为空。")


@dataclass(frozen=True)
class ReagentSafety:
    """一种试剂的只读安全信息快照。"""

    name_zh: str
    name_en: str
    cas: str | None
    molecular_formula: str | None
    molecular_weight: str | None
    signal_word: str | None
    hazard_statements: tuple[HazardStatement, ...]
    critical_codes: tuple[str, ...]
    review_status: str
    source_url: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.name_zh, str) or not self.name_zh.strip():
            raise HazmatStoreError("试剂中文名不能为空。")
        if self.review_status not in {"UNREVIEWED", "REVIEWED"}:
            raise HazmatStoreError(
                f"review_status只能是UNREVIEWED或REVIEWED，实际为{self.review_status!r}。"
            )

    @property
    def is_critical(self) -> bool:
        """是否含需要现场重点提醒的高危项。"""

        return bool(self.critical_codes)

    def critical_statements(self) -> tuple[HazardStatement, ...]:
        """只返回高危类别对应的说明，避免现场警告过载。"""

        critical = set(self.critical_codes)
        return tuple(s for s in self.hazard_statements if s.code in critical)


def _require_object(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HazmatStoreError(f"{location}必须是JSON对象。")
    return value


class HazmatStore:
    """从本地JSON加载试剂安全知识库，并支持按文本匹配。"""

    def __init__(self, path: Path | str = HAZMAT_FILE) -> None:
        self._path = Path(path)
        if not self._path.is_file():
            raise HazmatStoreError(f"找不到试剂安全知识库：{self._path}")
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise HazmatStoreError(f"试剂安全知识库不是合法JSON：{error}") from error

        library = _require_object(raw, "知识库顶层")
        version = library.get("schema_version")
        if version != HAZMAT_SCHEMA_VERSION:
            raise HazmatStoreError(
                f"试剂安全知识库schema_version不符：期望{HAZMAT_SCHEMA_VERSION}，实际{version}。"
            )
        entries = library.get("reagents")
        if not isinstance(entries, list):
            raise HazmatStoreError("reagents必须是列表。")

        reagents: list[ReagentSafety] = []
        for index, item in enumerate(entries, start=1):
            data = _require_object(item, f"第{index}种试剂")
            ghs = _require_object(data.get("ghs", {}), f"第{index}种试剂的ghs")
            statements = tuple(
                HazardStatement(s["code"], s["text"])
                for s in ghs.get("hazard_statements_zh", [])
            )
            reagents.append(
                ReagentSafety(
                    name_zh=data.get("name_zh", ""),
                    name_en=data.get("name_en", ""),
                    cas=data.get("cas"),
                    molecular_formula=data.get("molecular_formula"),
                    molecular_weight=str(data.get("molecular_weight"))
                    if data.get("molecular_weight") is not None
                    else None,
                    signal_word=ghs.get("signal_word"),
                    hazard_statements=statements,
                    critical_codes=tuple(data.get("critical_codes", [])),
                    review_status=data.get("review_status", "UNREVIEWED"),
                    source_url=(data.get("provenance") or {}).get("url"),
                )
            )

        names = [r.name_zh for r in reagents]
        if len(set(names)) != len(names):
            raise HazmatStoreError("试剂中文名不能重复。")
        self._reagents = tuple(reagents)

    @property
    def authority_note(self) -> str:
        """知识库的效力声明，展示时必须一并给出。"""

        return (
            "数据来自 PubChem，H码中文依据 GB 30000 系列；"
            "未经实验室安全负责人复核，不替代 MSDS 与实验室 SOP。"
        )

    def all_reagents(self) -> tuple[ReagentSafety, ...]:
        return self._reagents

    def find(self, name: str) -> ReagentSafety | None:
        """按中文名精确匹配一种试剂。"""

        if not isinstance(name, str):
            raise HazmatStoreError("试剂名必须是字符串。")
        for reagent in self._reagents:
            if reagent.name_zh == name.strip():
                return reagent
        return None

    def find_in_text(self, *texts: str) -> tuple[ReagentSafety, ...]:
        """从步骤原文或术语中找出出现过的试剂。

        采用最长名优先，避免"硫酸铜"命中后"五水硫酸铜"重复报出。
        """

        blob = " ".join(t for t in texts if isinstance(t, str) and t.strip())
        if not blob:
            return ()
        hits: list[ReagentSafety] = []
        for reagent in sorted(
            self._reagents, key=lambda r: len(r.name_zh), reverse=True
        ):
            if reagent.name_zh in blob:
                if any(reagent.name_zh in h.name_zh for h in hits):
                    continue
                hits.append(reagent)
        return tuple(sorted(hits, key=lambda r: r.name_zh))
