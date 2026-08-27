"""LLM意图分类接口与严格候选数据结构。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol

from src.core.intent_policy import IntentEvidence
from src.core.interaction_command import InteractionCommandType


class IntentClassifierError(RuntimeError):
    """意图分类器调用失败或返回非法结果。"""


class IntentCandidateStatus(str, Enum):
    """模型是否有足够依据给出一个意图候选。"""

    MATCHED = "matched"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class IntentClassificationInput:
    """分类一段ASR文本所需的最小会话上下文。"""

    raw_text: str
    session_active: bool
    pending_question_numbers: tuple[int, ...] = ()
    current_question_number: int | None = None

    def __post_init__(self) -> None:
        if not self.raw_text.strip():
            raise ValueError("意图分类输入不能为空。")
        if any(number <= 0 for number in self.pending_question_numbers):
            raise ValueError("待确认问题编号必须大于0。")
        if len(set(self.pending_question_numbers)) != len(
            self.pending_question_numbers
        ):
            raise ValueError("待确认问题编号不能重复。")
        if (
            self.current_question_number is not None
            and self.current_question_number
            not in self.pending_question_numbers
        ):
            raise ValueError(
                "当前问题必须存在于待确认问题编号中。"
            )


@dataclass(frozen=True)
class IntentCandidate:
    """分类器返回的候选含义，不代表系统已授权执行。"""

    status: IntentCandidateStatus = IntentCandidateStatus.MATCHED
    command_type: InteractionCommandType | None = None
    target_question_number: int | None = None
    answer_text: str | None = None
    reason: str | None = None
    evidence: IntentEvidence = IntentEvidence.LLM_CANDIDATE

    REQUIRED_FIELDS = frozenset({
        "status",
        "command_type",
        "target_question_number",
        "answer_text",
        "reason",
    })

    def __post_init__(self) -> None:
        if self.evidence != IntentEvidence.LLM_CANDIDATE:
            raise ValueError(
                "IntentCandidate只能表示LLM候选证据。"
            )
        if self.status == IntentCandidateStatus.MATCHED:
            if self.command_type is None:
                raise ValueError(
                    "matched候选必须包含command_type。"
                )
        elif self.command_type is not None:
            raise ValueError(
                "uncertain候选的command_type必须为null。"
            )
        if self.status == IntentCandidateStatus.UNCERTAIN and (
            self.target_question_number is not None
            or self.answer_text is not None
        ):
            raise ValueError(
                "uncertain候选不能包含目标编号或答案。"
            )
        if self.target_question_number is not None:
            if self.target_question_number <= 0:
                raise ValueError("目标问题编号必须大于0。")
            if self.command_type not in {
                InteractionCommandType.TARGETED_ANSWER,
                InteractionCommandType.REACTIVATE_TARGETED,
            }:
                raise ValueError(
                    "只有指定问题答复或恢复命令可以包含目标问题编号。"
                )
        if (
            self.command_type in {
                InteractionCommandType.TARGETED_ANSWER,
                InteractionCommandType.REACTIVATE_TARGETED,
            }
            and self.target_question_number is None
        ):
            raise ValueError("指定问题答复或恢复命令必须包含目标问题编号。")
        if self.answer_text is not None and not self.answer_text.strip():
            raise ValueError("answer_text不能是空白字符串。")
        if (
            self.answer_text is not None
            and self.command_type
            not in {
                InteractionCommandType.AFFIRM,
                InteractionCommandType.DENY,
                InteractionCommandType.TARGETED_ANSWER,
            }
        ):
            raise ValueError(
                "只有确认答复可以包含answer_text。"
            )
        if self.reason is not None and not self.reason.strip():
            raise ValueError("reason不能是空白字符串。")

    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, Any],
    ) -> "IntentCandidate":
        """严格解析模型JSON；缺字段和额外字段都拒绝。"""

        actual_fields = set(data)
        missing = cls.REQUIRED_FIELDS - actual_fields
        extra = actual_fields - cls.REQUIRED_FIELDS
        if missing:
            raise IntentClassifierError(
                f"意图候选缺少字段：{sorted(missing)}"
            )
        if extra:
            raise IntentClassifierError(
                f"意图候选包含额外字段：{sorted(extra)}"
            )

        try:
            status = IntentCandidateStatus(data["status"])
        except (TypeError, ValueError) as error:
            raise IntentClassifierError(
                "status不受支持。"
            ) from error

        raw_command_type = data["command_type"]
        if raw_command_type is None:
            command_type = None
        else:
            try:
                command_type = InteractionCommandType(raw_command_type)
            except (TypeError, ValueError) as error:
                raise IntentClassifierError(
                    "command_type不受支持。"
                ) from error

        target = data["target_question_number"]
        if target is not None and (
            not isinstance(target, int) or isinstance(target, bool)
        ):
            raise IntentClassifierError(
                "target_question_number必须是整数或null。"
            )

        for field_name in ("answer_text", "reason"):
            value = data[field_name]
            if value is not None and not isinstance(value, str):
                raise IntentClassifierError(
                    f"{field_name}必须是字符串或null。"
                )

        try:
            return cls(
                status=status,
                command_type=command_type,
                target_question_number=target,
                answer_text=data["answer_text"],
                reason=data["reason"],
            )
        except ValueError as error:
            raise IntentClassifierError(str(error)) from error


class IntentClassifier(Protocol):
    """真实LLM、假实现或未来本地模型共同遵守的接口。"""

    def classify(
        self,
        request: IntentClassificationInput,
    ) -> IntentCandidate: ...


class FakeIntentClassifier:
    """供单元与集成测试使用的确定性分类器。"""

    def __init__(
        self,
        responses: Mapping[str, IntentCandidate] | None = None,
        *,
        default: IntentCandidate | None = None,
        error: Exception | None = None,
    ) -> None:
        self._responses = dict(responses or {})
        self._default = default or IntentCandidate(
            command_type=InteractionCommandType.NORMAL,
            reason="Fake默认返回普通实验口述。",
        )
        self._error = error
        self.requests: list[IntentClassificationInput] = []

    def classify(
        self,
        request: IntentClassificationInput,
    ) -> IntentCandidate:
        self.requests.append(request)
        if self._error is not None:
            raise self._error
        return self._responses.get(request.raw_text, self._default)
