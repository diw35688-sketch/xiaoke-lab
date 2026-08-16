"""会话级实验方案状态：在选定方案与自由记录之间保持不变游标。"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.protocol import ProtocolStep
from src.core.protocol_cursor import ProtocolStepCursor
from src.core.protocol_selection import ProtocolSelection


@dataclass(frozen=True)
class ProtocolSessionState:
    """一次会话的方案选择和当前步骤快照。

    自由模式没有方案，因此 ``cursor``固定为 ``None``；所有导航方法都返回新状态，避免把会话推进藏在原地修改里。
    """

    selection: ProtocolSelection
    cursor: ProtocolStepCursor | None

    def __post_init__(self) -> None:
        if not isinstance(self.selection, ProtocolSelection):
            raise TypeError("selection必须是ProtocolSelection。")
        if self.selection.is_free_mode and self.cursor is not None:
            raise ValueError("自由模式的cursor必须是None。")
        if self.selection.has_protocol:
            if not isinstance(self.cursor, ProtocolStepCursor):
                raise ValueError("选中方案时必须提供ProtocolStepCursor。")
            if self.cursor.protocol is not self.selection.protocol:
                raise ValueError("cursor必须属于selection中的同一份方案。")

    @classmethod
    def start(cls, selection: ProtocolSelection) -> "ProtocolSessionState":
        """从选择结果开始会话；自由模式仍是合法的一等状态。"""

        if not isinstance(selection, ProtocolSelection):
            raise TypeError("selection必须是ProtocolSelection。")
        cursor = (
            ProtocolStepCursor.start(selection.protocol)
            if selection.has_protocol
            else None
        )
        return cls(selection=selection, cursor=cursor)

    def current_step(self) -> ProtocolStep | None:
        """返回当前方案步骤；自由模式返回None。"""

        return None if self.cursor is None else self.cursor.current_step

    @property
    def step_number(self) -> int | None:
        """返回当前步骤号；自由模式没有步骤号。"""

        return None if self.cursor is None else self.cursor.current_step_number

    def next(self) -> "ProtocolSessionState":
        """推进到下一步；自由模式保持等价的新状态。"""

        return self._with_cursor(None if self.cursor is None else self.cursor.next())

    def prev(self) -> "ProtocolSessionState":
        """回到上一步；自由模式保持等价的新状态。"""

        return self._with_cursor(None if self.cursor is None else self.cursor.prev())

    def jump_to(self, step_number: int) -> "ProtocolSessionState":
        """跳到指定步骤；自由模式不参与步骤定位并保持不变。"""

        return self._with_cursor(
            None if self.cursor is None else self.cursor.jump_to(step_number)
        )

    def _with_cursor(self, cursor: ProtocolStepCursor | None) -> "ProtocolSessionState":
        return type(self)(selection=self.selection, cursor=cursor)
