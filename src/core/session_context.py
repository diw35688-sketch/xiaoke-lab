from collections import deque

from src.llm.schemas import (
    ExperimentEvent,
    ExperimentEventType,
    LLMAnalysisResult,
)


class SessionContext:
    """
    当前实验会话的短期上下文。

    只保存在内存中，不负责文件持久化。
    每次开始新实验会话时创建新实例。
    """

    def __init__(
        self,
        max_events: int = 8,
    ) -> None:
        if max_events <= 0:
            raise ValueError(
                "max_events 必须大于 0。"
            )

        self.max_events = max_events

        self._items: deque[str] = deque(
            maxlen=max_events
        )

    def add_analysis(
        self,
        result: LLMAnalysisResult,
    ) -> None:
        """
        将一次 LLM 分析中的事件
        加入当前会话上下文。

        一段口述可能产生多个事件，
        因此需要逐个加入。
        """

        if not result.events:
            raise ValueError(
                "分析结果中没有事件，"
                "无法更新上下文。"
            )

        for event in result.events:
            context_text = (
                self._event_to_context_text(
                    event
                )
            )

            if context_text:
                self._items.append(
                    context_text
                )

    def as_prompt_context(
        self,
    ) -> tuple[str, ...]:
        """
        返回不可变的上下文快照，
        供 LLM 提示词使用。

        返回 tuple 可以避免调用方
        意外修改内部上下文。
        """

        return tuple(self._items)

    def clear(self) -> None:
        """
        清空当前会话上下文。

        正常情况下每次新会话直接创建
        新的 SessionContext；
        clear 主要用于测试或手动重置。
        """

        self._items.clear()

    def to_snapshot(self) -> dict[str, object]:
        return {"max_events": self.max_events, "items": list(self._items)}

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, object]) -> "SessionContext":
        max_events = int(snapshot.get("max_events", 8))
        context = cls(max_events=max_events)
        items = snapshot.get("items", [])
        if not isinstance(items, list) or any(
            not isinstance(item, str) for item in items
        ):
            raise ValueError("SessionContext items 快照必须是字符串列表。")
        context._items.extend(items)
        return context

    def __len__(self) -> int:
        return len(self._items)

    @staticmethod
    def _event_to_context_text(
        event: ExperimentEvent,
    ) -> str:
        """
        将一个事件转换为适合提示词的短文本。

        正常事件使用 normalized_text；
        降级 NOTE 使用 raw_text，
        避免把未经验证的推断传给下一轮模型。
        """

        if (
            event.event_type
            == ExperimentEventType.NOTE
        ):
            text = event.raw_text
        else:
            text = event.normalized_text

        text = text.strip()

        if not text:
            return ""

        return (
            f"[{event.event_type.value}] "
            f"{text}"
        )
