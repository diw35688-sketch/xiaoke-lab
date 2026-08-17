# -*- coding: utf-8 -*-
"""试剂配置库的严格读取与整份写回。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.core.reagent_prep import ReagentPrep, ReagentPrepError
from src.config import DATA_DIR

REAGENT_PREP_FILE = DATA_DIR / "reagent_prep" / "reagent_prep_library.json"
REAGENT_PREP_SCHEMA_VERSION = 1


def _require_object(value: Any, location: str) -> dict:
    if not isinstance(value, dict):
        raise ReagentPrepError(f"{location} 必须是 JSON 对象。")
    return value


class ReagentPrepStore:
    """从本地 JSON 加载试剂配置库，并提供严格新增与写回。"""

    def __init__(self, path: Path | str = REAGENT_PREP_FILE) -> None:
        self._path = Path(path)
        if not self._path.is_file():
            raise ReagentPrepError(f"找不到试剂配置库：{self._path}")
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ReagentPrepError(
                f"试剂配置库不是合法 JSON：{error}"
            ) from error

        library = _require_object(raw, "试剂配置库顶层")
        version = library.get("schema_version")
        if version != REAGENT_PREP_SCHEMA_VERSION:
            raise ReagentPrepError(
                "试剂配置库 schema_version 不符："
                f"期望 {REAGENT_PREP_SCHEMA_VERSION}，实际 {version}。"
            )
        entries = library.get("reagent_preps")
        if not isinstance(entries, list):
            raise ReagentPrepError("reagent_preps 必须是列表。")
        if not entries:
            raise ReagentPrepError("reagent_preps 不能为空。")

        preps: list[ReagentPrep] = []
        ids: set[str] = set()
        for index, item in enumerate(entries, start=1):
            data = _require_object(item, f"第{index}条试剂配置")
            prep = ReagentPrep.from_dict(data)
            if prep.reagent_prep_id in ids:
                raise ReagentPrepError(
                    "reagent_prep_id 重复："
                    f"{prep.reagent_prep_id}"
                )
            ids.add(prep.reagent_prep_id)
            preps.append(prep)
        self._preps = tuple(preps)
        self._by_id = {p.reagent_prep_id: p for p in self._preps}

    @property
    def path(self) -> Path:
        return self._path

    def list_all(self) -> tuple[ReagentPrep, ...]:
        return self._preps

    def get_by_id(self, reagent_prep_id: str) -> ReagentPrep | None:
        if not isinstance(reagent_prep_id, str) or not reagent_prep_id.strip():
            raise ReagentPrepError("查询的 reagent_prep_id 不能为空。")
        return self._by_id.get(reagent_prep_id)

    def add(self, prep: ReagentPrep) -> None:
        """严格写入一条新配方；id 重复则整笔拒绝。"""

        if self._by_id.get(prep.reagent_prep_id) is not None:
            raise ReagentPrepError(
                "reagent_prep_id 已存在："
                f"{prep.reagent_prep_id}"
            )
        library = json.loads(self._path.read_text(encoding="utf-8"))
        library.setdefault("reagent_preps", []).append(prep.to_dict())
        self._path.write_text(
            json.dumps(library, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._preps = tuple(self._preps + (prep,))
        self._by_id[prep.reagent_prep_id] = prep

    def add_many(self, preps: list[ReagentPrep]) -> None:
        """批量写入；任一 id 重复则全部拒绝，不写半成品。"""

        existing = set(self._by_id)
        for prep in preps:
            if prep.reagent_prep_id in existing:
                raise ReagentPrepError(
                    "reagent_prep_id 已存在："
                    f"{prep.reagent_prep_id}"
                )
            existing.add(prep.reagent_prep_id)
        for prep in preps:
            self.add(prep)
