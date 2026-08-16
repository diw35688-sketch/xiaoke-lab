"""严格读取本地JSON实验方案库。"""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from src.core.protocol import (
    ProtocolSubStep,
    PROTOCOL_SCHEMA_VERSION,
    ExperimentProtocol,
    ProtocolError,
    ProtocolStep,
)


class ProtocolStoreError(ProtocolError):
    """实验方案库文件不存在、损坏或不符合严格格式。"""


_LIBRARY_FIELDS = frozenset({"protocols"})
_PROTOCOL_FIELDS = frozenset({
    "protocol_id",
    "title",
    "source",
    "version",
    "steps",
    "schema_version",
})
_STEP_FIELDS = frozenset({
    "step_number",
    "title",
    "instruction",
    "protocol_values",
    "must_record",
    "terms",
    "hazard_note",
    "field_prompts",
})
_OPTIONAL_STEP_FIELDS = frozenset({"field_prompts", "substeps"})


def _require_object(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProtocolStoreError(f"{location}必须是JSON对象。")
    return value


def _require_exact_fields(
    data: Mapping[str, Any],
    expected: frozenset[str],
    location: str,
    *,
    optional: frozenset[str] = frozenset(),
) -> None:
    actual = set(data)
    missing = sorted((expected - optional) - actual)
    extra = sorted(actual - expected - optional)
    if missing or extra:
        raise ProtocolStoreError(
            f"{location}字段不匹配；缺少={missing}，额外={extra}"
        )


def _require_list(value: Any, location: str) -> list[Any]:
    if not isinstance(value, list):
        raise ProtocolStoreError(f"{location}必须是JSON数组。")
    return value


class ProtocolStore:
    """一次加载并只读查询一份严格JSON方案库。"""

    def __init__(self, input_path: str | Path) -> None:
        self.input_path = Path(input_path)
        protocols = self._load()
        by_id = {protocol.protocol_id: protocol for protocol in protocols}
        self._protocols = protocols
        self._by_id = MappingProxyType(by_id)

    def list_all(self) -> tuple[ExperimentProtocol, ...]:
        """按JSON文件中的稳定顺序列出全部方案。"""

        return self._protocols

    def get_by_id(self, protocol_id: str) -> ExperimentProtocol | None:
        """按唯一编号查询方案；不存在时返回None。"""

        if not isinstance(protocol_id, str) or not protocol_id.strip():
            raise ProtocolStoreError("查询的protocol_id不能为空。")
        return self._by_id.get(protocol_id)

    def get(self, protocol_id: str) -> ExperimentProtocol | None:
        """提供简短的按编号查询别名。"""

        return self.get_by_id(protocol_id)

    def _load(self) -> tuple[ExperimentProtocol, ...]:
        if not self.input_path.exists():
            raise ProtocolStoreError(f"方案库文件不存在：{self.input_path}")
        if not self.input_path.is_file():
            raise ProtocolStoreError(f"方案库路径不是文件：{self.input_path}")
        try:
            content = self.input_path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as error:
            raise ProtocolStoreError(f"方案库文件无法读取：{self.input_path}") from error
        try:
            raw_library = json.loads(content)
        except json.JSONDecodeError as error:
            raise ProtocolStoreError(f"方案库文件不是合法JSON：{self.input_path}") from error

        library = _require_object(raw_library, "方案库顶层")
        _require_exact_fields(library, _LIBRARY_FIELDS, "方案库顶层")
        raw_protocols = _require_list(library["protocols"], "protocols")
        if not raw_protocols:
            raise ProtocolStoreError("protocols不能为空。")

        protocols: list[ExperimentProtocol] = []
        protocol_ids: set[str] = set()
        for index, raw_protocol in enumerate(raw_protocols, start=1):
            protocol = self._parse_protocol(raw_protocol, index=index)
            if protocol.protocol_id in protocol_ids:
                raise ProtocolStoreError(
                    f"protocol_id在方案库中重复：{protocol.protocol_id}"
                )
            protocol_ids.add(protocol.protocol_id)
            protocols.append(protocol)
        return tuple(protocols)

    @staticmethod
    def _parse_protocol(raw_protocol: Any, *, index: int) -> ExperimentProtocol:
        location = f"protocols第{index}项"
        data = _require_object(raw_protocol, location)
        _require_exact_fields(data, _PROTOCOL_FIELDS, location)
        raw_steps = _require_list(data["steps"], f"{location}.steps")
        steps = tuple(
            ProtocolStore._parse_step(
                raw_step,
                protocol_index=index,
                step_index=step_index,
            )
            for step_index, raw_step in enumerate(raw_steps, start=1)
        )
        try:
            protocol = ExperimentProtocol(
                protocol_id=data["protocol_id"],
                title=data["title"],
                source=data["source"],
                version=data["version"],
                steps=steps,
                schema_version=data["schema_version"],
            )
        except ProtocolError as error:
            raise ProtocolStoreError(f"{location}无效：{error}") from error
        if protocol.schema_version != PROTOCOL_SCHEMA_VERSION:
            raise ProtocolStoreError(
                f"{location}.schema_version不受支持："
                f"期望{PROTOCOL_SCHEMA_VERSION}，实际{protocol.schema_version}。"
            )
        return protocol

    @staticmethod
    def _parse_step(
        raw_step: Any,
        *,
        protocol_index: int,
        step_index: int,
    ) -> ProtocolStep:
        location = f"protocols第{protocol_index}项.steps第{step_index}项"
        data = _require_object(raw_step, location)
        # 可选字段恒定允许出现或省略：出现时按内容解析，省略时用契约默认值。
        # 不要按"是否已出现某个字段"来切换允许集，那会让新增可选字段互相牵连。
        _require_exact_fields(
            data,
            _STEP_FIELDS,
            location,
            optional=_OPTIONAL_STEP_FIELDS,
        )
        terms = _require_list(data["terms"], f"{location}.terms")
        try:
            return ProtocolStep(
                step_number=data["step_number"],
                title=data["title"],
                instruction=data["instruction"],
                protocol_values=data["protocol_values"],
                must_record=tuple(data["must_record"]),
                terms=tuple(terms),
                hazard_note=data["hazard_note"],
                substeps=tuple(
                    ProtocolSubStep(
                        order=int(item.get("order", index)),
                        text=item.get("text", ""),
                        note=item.get("note"),
                    )
                    for index, item in enumerate(data.get("substeps", []) or [], start=1)
                ),
                field_prompts=data.get("field_prompts", {}),
            )
        except ProtocolError as error:
            raise ProtocolStoreError(f"{location}无效：{error}") from error
