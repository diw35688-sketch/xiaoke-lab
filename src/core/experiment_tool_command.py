"""Conservative command gate for tools used during experiment recording."""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ExperimentToolCommand:
    """A sentence-initial XiaoKe address and the command that follows it."""

    matched: bool
    raw_text: str
    command_text: str | None = None

    def __post_init__(self) -> None:
        if self.matched:
            if not isinstance(self.command_text, str) or not self.command_text.strip():
                raise ValueError("命中实验工具指令时 command_text 必须为非空字符串。")
        elif self.command_text is not None:
            raise ValueError("未命中实验工具指令时 command_text 必须为 None。")


class ExperimentToolCommandParser:
    """Only a sentence-initial explicit address may enter the tool agent."""

    _TRAILING_EMOTIONS = "😊😔😡😰🤢😮"
    _PREFIX = re.compile(r"^\s*(?:小科小科|小科)(?:\s|[，,。.!！?？:：、])*", re.UNICODE)
    _LEADING_SEPARATORS = " \t\r\n，,。.!！?？:：、"

    @classmethod
    def parse(cls, text: str) -> ExperimentToolCommand:
        if not isinstance(text, str):
            raise TypeError("text 必须是字符串。")
        match = cls._PREFIX.match(text)
        if match is None:
            return ExperimentToolCommand(False, text)
        command = text[match.end():].strip(cls._LEADING_SEPARATORS)
        command = command.rstrip(cls._TRAILING_EMOTIONS).strip()
        if not command:
            return ExperimentToolCommand(False, text)
        return ExperimentToolCommand(True, text, command)
