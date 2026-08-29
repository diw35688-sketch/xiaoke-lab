import re
from dataclasses import dataclass
from enum import Enum


class InteractionCommandType(str, Enum):
    """用户口述中可能包含的控制意图。"""

    NORMAL = "normal"
    END_SESSION = "end_session"
    DEFER_CURRENT = "defer_current"
    REVIEW_PENDING = "review_pending"
    NEXT_PROTOCOL_STEP = "next_protocol_step"
    AFFIRM = "affirm"
    DENY = "deny"
    TARGETED_ANSWER = "targeted_answer"
    DEFER_TARGETED = "defer_targeted"
    REACTIVATE_TARGETED = "reactivate_targeted"


@dataclass(frozen=True)
class InteractionCommand:
    """
    纯文本解析结果。

    解析器只描述候选意图。需要待确认项上下文的命令，必须由
    ReplyCoordinator 再判断是否可以执行。
    """

    command_type: InteractionCommandType
    raw_text: str
    normalized_text: str
    target_question_number: int | None = None
    answer_text: str | None = None

    def __post_init__(self) -> None:
        if self.command_type in {
            InteractionCommandType.TARGETED_ANSWER,
            InteractionCommandType.DEFER_TARGETED,
            InteractionCommandType.REACTIVATE_TARGETED,
        }:
            if (
                self.target_question_number is None
                or self.target_question_number <= 0
            ):
                raise ValueError(
                    "指定问题命令必须包含大于 0 的问题编号。"
                )
        elif self.target_question_number is not None:
            raise ValueError(
                "只有指定问题命令可以包含问题编号。"
            )

    @property
    def is_control_candidate(self) -> bool:
        return self.command_type != InteractionCommandType.NORMAL

    @property
    def requires_clarification_context(self) -> bool:
        return self.command_type in {
            InteractionCommandType.DEFER_CURRENT,
            InteractionCommandType.DEFER_TARGETED,
            InteractionCommandType.REACTIVATE_TARGETED,
            InteractionCommandType.REVIEW_PENDING,
            InteractionCommandType.AFFIRM,
            InteractionCommandType.DENY,
            InteractionCommandType.TARGETED_ANSWER,
        }


class InteractionCommandParser:
    """使用保守、确定性的规则解析交互命令。"""

    # SenseVoice 的 rich_transcription_postprocess 会把识别到的
    # 情绪标签转换成这些句尾符号。它们不属于用户口述的命令文字，
    # 因此只在命令匹配副本中移除，raw_text 始终原样保留。
    SENSEVOICE_TRAILING_EMOTIONS = "😊😔😡😰🤢😮"

    END_SESSION_COMMANDS = {
        "结束实验记录",
        "结束记录",
        "结束本次实验",
        "退出实验记录",
        "结束实验",

        # 只保留真实验收中观察到的 ASR 变体。
        "接受实验记录",
    }

    DEFER_CURRENT_COMMANDS = {
        "这个先跳过",
        "当前问题先跳过",
        "这个问题先跳过",
        "稍后再问",
        "稍后回答",
        "暂时无法回答",
        # 真实验收中观察到的自然变体
        "先问下一个",
        "这个问题先放着",
    }

    # 安全前缀+后缀匹配：以这些前缀开头 AND 以这些后缀结尾 → DEFER
    # "跳过过滤步骤继续加热"不以任何安全前缀开头 → 安全
    _DEFER_SAFE_STARTS = (
        "我先", "可先", "能先",
        "这个先", "那个先", "这条先",
        "当前先",
    )
    _DEFER_SAFE_ENDS = ("跳过", "先跳过", "跳过去", "跳过吗", "跳过吧")

    REVIEW_PENDING_COMMANDS = {
        "查看待确认问题",
        "查看未解决问题",
        "还有哪些问题",
        "重复待确认问题",
    }

    NEXT_PROTOCOL_STEP_COMMANDS = {
        "下一步",
        "进入下一步",
        "继续下一步",
    }

    AFFIRM_EXACT = {
        "是",
        "是的",
        "对",
        "对的",
        "正确",
        "没错",
        "确认",
    }

    # "确认/否定 + 实体"：确定性判定"是不是确认/否定"（动作），实体抽取交给执行器 LLM 提取器。
    # 比原 "是的是" 宽——能抓住"是的，50微升"（不要求实体以"是"开头）。
    # 刻意不收 "对"/"是" 前缀："对溶液…""是什么" 会误判成确认。
    AFFIRM_PREFIXES = (
        "是的",
        "没错",
        "确认",
    )

    DENY_EXACT = {
        "不是",
        "不对",
        "错误",
        "否",
    }

    DENY_PREFIXES = (
        "不是",
        "不对",
        "错误",
    )

    TARGET_PATTERNS = (
        re.compile(
            r"^(?:回答)?问题"
            r"(?P<number>\d+|[一二三四五六七八九十]+)"
            r"(?P<answer>.*)$"
        ),
        re.compile(
            r"^(?:回答)?第?"
            r"(?P<number>\d+|[一二三四五六七八九十]+)"
            r"个?问题(?P<answer>.*)$"
        ),
    )

    # 按编号暂缓：问题N先跳过 / 第N个问题先跳过（N 支持数字或中文）
    DEFER_TARGETED_PATTERNS = (
        re.compile(
            r"^问题(?P<number>\d+|[一二三四五六七八九十]+)"
            r"(?:先跳过|先暂缓|跳过|暂缓)$"
        ),
        re.compile(
            r"^第?(?P<number>\d+|[一二三四五六七八九十]+)"
            r"个问题(?:先跳过|先暂缓|跳过|暂缓)$"
        ),
    )

    REACTIVATE_TARGETED_PATTERNS = (
        re.compile(
            r"^(?:继续|恢复)(?:回答)?问题"
            r"(?P<number>\d+|[一二三四五六七八九十]+)$"
        ),
        re.compile(
            r"^(?:继续|恢复)(?:回答)?第?"
            r"(?P<number>\d+|[一二三四五六七八九十]+)"
            r"个?问题$"
        ),
    )

    @classmethod
    def parse(
        cls,
        text: str,
    ) -> InteractionCommand:
        raw_text = text
        normalized = cls.normalize(text)

        if normalized in cls.END_SESSION_COMMANDS:
            return cls._simple_command(
                InteractionCommandType.END_SESSION,
                raw_text,
                normalized,
            )

        if (
            normalized in cls.DEFER_CURRENT_COMMANDS
            or cls._match_defer_natural(normalized)
        ):
            return cls._simple_command(
                InteractionCommandType.DEFER_CURRENT,
                raw_text,
                normalized,
            )

        if (
            normalized in cls.REVIEW_PENDING_COMMANDS
            or cls._match_review_natural(normalized)
        ):
            return cls._simple_command(
                InteractionCommandType.REVIEW_PENDING,
                raw_text,
                normalized,
            )

        if normalized in cls.NEXT_PROTOCOL_STEP_COMMANDS:
            return cls._simple_command(
                InteractionCommandType.NEXT_PROTOCOL_STEP,
                raw_text,
                normalized,
            )

        defer_targeted = cls._parse_defer_targeted(
            raw_text,
            normalized,
        )
        if defer_targeted is not None:
            return defer_targeted

        reactivate_targeted = cls._parse_reactivate_targeted(
            raw_text,
            normalized,
        )
        if reactivate_targeted is not None:
            return reactivate_targeted

        targeted_answer = cls._parse_targeted_answer(
            raw_text,
            normalized,
        )
        if targeted_answer is not None:
            return targeted_answer

        if (
            normalized in cls.AFFIRM_EXACT
            or normalized.startswith(cls.AFFIRM_PREFIXES)
        ):
            return cls._simple_command(
                InteractionCommandType.AFFIRM,
                raw_text,
                normalized,
                answer_text=normalized,
            )

        if (
            normalized in cls.DENY_EXACT
            or normalized.startswith(cls.DENY_PREFIXES)
        ):
            return cls._simple_command(
                InteractionCommandType.DENY,
                raw_text,
                normalized,
                answer_text=normalized,
            )

        return cls._simple_command(
            InteractionCommandType.NORMAL,
            raw_text,
            normalized,
        )

    @staticmethod
    def normalize(text: str) -> str:
        """
        为命令匹配移除空白、常见标点和句尾情绪符号。

        这里只生成匹配副本，不修改需要持久化的 ASR 原文。
        SenseVoice 的声音事件符号（如掌声、咳嗽）不会被移除。
        """

        normalized = re.sub(
            r"[\s，。！？、,.!?；;：:]",
            "",
            text,
        )
        return normalized.rstrip(
            InteractionCommandParser.SENSEVOICE_TRAILING_EMOTIONS
        )

    @classmethod
    def _parse_defer_targeted(
        cls,
        raw_text: str,
        normalized: str,
    ) -> InteractionCommand | None:
        for pattern in cls.DEFER_TARGETED_PATTERNS:
            match = pattern.fullmatch(normalized)
            if match is None:
                continue

            number = cls._parse_question_number(
                match.group("number")
            )
            if number is None or number <= 0:
                return None

            return InteractionCommand(
                command_type=InteractionCommandType.DEFER_TARGETED,
                raw_text=raw_text,
                normalized_text=normalized,
                target_question_number=number,
            )

        return None

    @classmethod
    def _parse_targeted_answer(
        cls,
        raw_text: str,
        normalized: str,
    ) -> InteractionCommand | None:
        for pattern in cls.TARGET_PATTERNS:
            match = pattern.fullmatch(normalized)
            if match is None:
                continue

            number = cls._parse_question_number(
                match.group("number")
            )
            if number is None or number <= 0:
                return None

            answer = match.group("answer").strip() or None

            return InteractionCommand(
                command_type=(
                    InteractionCommandType.TARGETED_ANSWER
                ),
                raw_text=raw_text,
                normalized_text=normalized,
                target_question_number=number,
                answer_text=answer,
            )

        return None

    @classmethod
    def _parse_reactivate_targeted(
        cls,
        raw_text: str,
        normalized: str,
    ) -> InteractionCommand | None:
        for pattern in cls.REACTIVATE_TARGETED_PATTERNS:
            match = pattern.fullmatch(normalized)
            if match is None:
                continue

            number = cls._parse_question_number(match.group("number"))
            if number is None or number <= 0:
                return None

            return InteractionCommand(
                command_type=InteractionCommandType.REACTIVATE_TARGETED,
                raw_text=raw_text,
                normalized_text=normalized,
                target_question_number=number,
            )

        return None

    @staticmethod
    def _parse_question_number(
        text: str,
    ) -> int | None:
        if text.isdigit():
            return int(text)

        digits = {
            "一": 1,
            "二": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
        }

        if text == "十":
            return 10
        if len(text) == 2 and text[0] == "十":
            return 10 + digits.get(text[1], 0)
        if len(text) == 2 and text[1] == "十":
            return digits.get(text[0], 0) * 10
        if len(text) == 3 and text[1] == "十":
            return (
                digits.get(text[0], 0) * 10
                + digits.get(text[2], 0)
            )

        return digits.get(text)

    @classmethod
    def _match_defer_natural(cls, normalized: str) -> bool:
        return (
            normalized.startswith(cls._DEFER_SAFE_STARTS)
            and normalized.endswith(cls._DEFER_SAFE_ENDS)
        )

    @classmethod
    def _match_review_natural(cls, normalized: str) -> bool:
        # "还有/还有什么/有没有" + "问题"或"什么" → 询问剩余项
        if normalized.startswith(("还有", "有没有")) and (
            "问题" in normalized or "什么" in normalized
        ):
            return True

        # "看看/看一下/想看/我想看" + "缺/少/什么" → 想查看缺失信息
        if normalized.startswith(("看看", "看一下", "想看", "我想看")) and any(
            keyword in normalized for keyword in ("缺", "少", "什么")
        ):
            return True

        return False

    @staticmethod
    def _simple_command(
        command_type: InteractionCommandType,
        raw_text: str,
        normalized_text: str,
        *,
        answer_text: str | None = None,
    ) -> InteractionCommand:
        return InteractionCommand(
            command_type=command_type,
            raw_text=raw_text,
            normalized_text=normalized_text,
            answer_text=answer_text,
        )
