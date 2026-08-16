"""从已加载方案库中生成不可变的实验方案选择结果。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from src.core.protocol import ExperimentProtocol, ProtocolError


class ProtocolSelectionError(ProtocolError):
    """实验方案选择值无效或目标不存在。"""


class ProtocolSelectionMode(str, Enum):
    """用户选择具体方案或保留原有自由记录模式。"""

    SELECTED = "selected"
    FREE = "free"


class ProtocolCatalog(Protocol):
    """方案选择逻辑所需的最小只读库接口。"""

    def list_all(self) -> tuple[ExperimentProtocol, ...]: ...

    def get_by_id(
        self,
        protocol_id: str,
    ) -> ExperimentProtocol | None: ...


@dataclass(frozen=True)
class ProtocolSelection:
    """一次只读选择，明确区分选中方案和自由记录。"""

    mode: ProtocolSelectionMode
    protocol: ExperimentProtocol | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.mode, ProtocolSelectionMode):
            raise ProtocolSelectionError("mode必须是ProtocolSelectionMode。")
        if self.mode == ProtocolSelectionMode.SELECTED:
            if not isinstance(self.protocol, ExperimentProtocol):
                raise ProtocolSelectionError(
                    "selected结果必须包含ExperimentProtocol。"
                )
        elif self.protocol is not None:
            raise ProtocolSelectionError(
                "free结果不能携带实验方案。"
            )

    @classmethod
    def selected(
        cls,
        protocol: ExperimentProtocol,
    ) -> "ProtocolSelection":
        return cls(
            mode=ProtocolSelectionMode.SELECTED,
            protocol=protocol,
        )

    @classmethod
    def free_mode(cls) -> "ProtocolSelection":
        return cls(mode=ProtocolSelectionMode.FREE)

    @property
    def is_free_mode(self) -> bool:
        return self.mode == ProtocolSelectionMode.FREE

    @property
    def has_protocol(self) -> bool:
        return self.mode == ProtocolSelectionMode.SELECTED


def select_protocol(
    catalog: ProtocolCatalog,
    selection: int | str | None,
) -> ProtocolSelection:
    """按1起序号或protocol_id选择；None保留自由记录模式。"""

    if selection is None:
        return ProtocolSelection.free_mode()

    if isinstance(selection, bool):
        raise ProtocolSelectionError("方案序号不能是布尔值。")

    if isinstance(selection, int):
        if selection <= 0:
            raise ProtocolSelectionError("方案序号必须从1开始。")
        protocols = catalog.list_all()
        if selection > len(protocols):
            raise ProtocolSelectionError(
                f"方案序号超出范围：{selection}。"
            )
        return ProtocolSelection.selected(
            protocols[selection - 1]
        )

    if isinstance(selection, str):
        if not selection.strip():
            raise ProtocolSelectionError("protocol_id不能为空。")
        protocol = catalog.get_by_id(selection)
        if protocol is None:
            raise ProtocolSelectionError(
                f"未找到实验方案：{selection}"
            )
        return ProtocolSelection.selected(protocol)

    raise ProtocolSelectionError(
        "方案选择值必须是序号、protocol_id或None。"
    )
