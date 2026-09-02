"""无编号回答的确定性兜底。

纯函数层：不依赖 LLM、不做任何 I/O，只根据
"待确认问题数量 + 文本是否提供问题缺失字段"做确定性判断。
用途：统一链把短事实句判为弃权(abstention)时，兜底决定它是否
其实是对"唯一待确认问题"的回答；任何不满足条件的输入
（多问题/无问题/字段不匹配/实验记录）一律返回非回答，
绝不把实验记录路由成回答。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from src.core.pending_clarification import PendingClarification

# 演示实验的核心实体字段的确定性提取模式。
# 只覆盖本项目 demo 会用到的字段；不试图做通用 NLP。
_FIELD_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("temperature", re.compile(r"\d+(?:\.\d+)?\s*(?:摄氏度|℃|°C|度)")),
    ("duration", re.compile(r"\d+(?:\.\d+)?\s*(?:分钟|小时|秒|min|h)")),
    ("amount_value", re.compile(r"\d+(?:\.\d+)?\s*(?:毫升|微升|升|μl|ul|ml|l)")),
    ("amount_unit", re.compile(r"(?:毫升|微升|升|μl|ul|ml|l)")),
    ("concentration", re.compile(r"\d+(?:\.\d+)?\s*(?:mol/l|mmol/l|摩尔每升)")),
)

# "短句"的操作化边界：超过该长度视为复合句（可能是实验操作），不兜底。
_MAX_ANSWER_TEXT_LENGTH = 20

_EXPLICIT_QUESTION_REFERENCE = re.compile(r"(?:问题|第)\s*[一二三四五六七八九十\d]+")
_OPERATION_WORDS = (
    "加入", "移取", "称取", "称量", "加热", "冷却", "搅拌", "混匀",
    "过滤", "离心", "滴定", "洗涤", "转移", "配制", "保存", "放入",
)
_NATURAL_VALUE_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "temperature": (
        re.compile(r"\d+(?:\.\d+)?\s*(?:摄氏度|℃|°C|度)"),
        re.compile(r"[零一二两三四五六七八九十百]+\s*(?:摄氏度|度)"),
        re.compile(r"^(?:室温|常温|冰浴|沸水浴)$"),
    ),
    "duration": (
        re.compile(r"\d+(?:\.\d+)?\s*(?:分钟|小时|秒|min|h)"),
        re.compile(r"[零一二两三四五六七八九十百]+\s*(?:分钟|小时|秒)"),
        re.compile(r"^(?:半小时|一刻钟|过夜|隔夜)$"),
    ),
    "observation": (
        re.compile(
            r"^(?:无色|白色|乳白色|粉红色|红色|橙色|黄色|绿色|蓝色|"
            r"紫色|黑色|棕色|褐色|透明|澄清|浑浊|有沉淀|无沉淀|"
            r"产生气泡|有气泡|无气泡)$"
        ),
    ),
    "condition": (
        re.compile(r"^(?:室温|常温|冰浴|冷藏|冷冻|避光|密封)$"),
        re.compile(r"^(?:室温|常温|冷藏|冷冻|避光|密封).{0,4}$"),
    ),
    "amount_value": (
        re.compile(
            r"^\d+(?:\.\d+)?\s*(?:毫升|微升|升|毫克|微克|克|千克|"
            r"mL|ml|uL|µL|L|mg|ug|µg|g|kg|滴)$"
        ),
        re.compile(
            r"^[零一二两三四五六七八九十百]+\s*"
            r"(?:毫升|微升|升|毫克|微克|克|千克|滴)$"
        ),
    ),
    "amount_unit": (
        re.compile(
            r"^\d+(?:\.\d+)?\s*(?:毫升|微升|升|毫克|微克|克|千克|"
            r"mL|ml|uL|µL|L|mg|ug|µg|g|kg|滴)$"
        ),
        re.compile(
            r"^[零一二两三四五六七八九十百]+\s*"
            r"(?:毫升|微升|升|毫克|微克|克|千克|滴)$"
        ),
    ),
    "concentration": (
        re.compile(r"^\d+(?:\.\d+)?\s*(?:mol/L|mmol/L|摩尔每升|%)$", re.I),
    ),
}


@dataclass(frozen=True)
class UnnumberedAnswerDecision:
    """兜底判断结果；字段为空时表示不作为回答。"""

    is_answer: bool
    fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.is_answer and self.fields:
            raise ValueError("非回答判定不能携带字段。")


def decide_natural_short_answer(
    *,
    pending_questions: Sequence["PendingClarification"],
    text: str,
    current_segment_id: int,
) -> UnnumberedAnswerDecision:
    """识别唯一当前问题后的自然值短答，并拒绝歧义或操作陈述。

    与旧的数值字段兜底不同，本函数允许“粉红色”“过夜”“室温”等没有
    字段名的值。只有值与一个或一组不可分割的数量字段唯一兼容时才接住；
    同时兼容两个语义槽位（如 temperature/condition）的输入不会猜。
    """

    if len(pending_questions) != 1:
        return UnnumberedAnswerDecision(is_answer=False)
    if not isinstance(text, str):
        return UnnumberedAnswerDecision(is_answer=False)
    normalized = text.strip().strip("。！!？?")
    if not normalized or len(normalized) > _MAX_ANSWER_TEXT_LENGTH:
        return UnnumberedAnswerDecision(is_answer=False)
    if _EXPLICIT_QUESTION_REFERENCE.search(normalized):
        return UnnumberedAnswerDecision(is_answer=False)
    if any(word in normalized for word in _OPERATION_WORDS):
        return UnnumberedAnswerDecision(is_answer=False)

    question = pending_questions[0]
    if question.source_segment_id + 1 != current_segment_id:
        return UnnumberedAnswerDecision(is_answer=False)

    compatible = tuple(
        field_name
        for field_name in question.missing_fields
        if any(
            pattern.search(normalized)
            for pattern in _NATURAL_VALUE_PATTERNS.get(field_name, ())
        )
    )
    if not compatible:
        return UnnumberedAnswerDecision(is_answer=False)

    # 数量的值和单位来自同一份证据，允许一起补；其他多槽位命中属于歧义。
    if len(compatible) > 1 and set(compatible) != {"amount_value", "amount_unit"}:
        return UnnumberedAnswerDecision(is_answer=False)
    return UnnumberedAnswerDecision(is_answer=True, fields=compatible)


def extract_entity_fields(text: str) -> tuple[str, ...]:
    """从文本中确定性提取命中的实体字段名（只判存在，不做值归一化）。"""

    if not isinstance(text, str) or not text.strip():
        return ()

    found: list[str] = []
    for field_name, pattern in _FIELD_PATTERNS:
        if pattern.search(text) and field_name not in found:
            found.append(field_name)
    return tuple(found)


def decide_unnumbered_answer(
    *,
    pending_questions: Sequence["PendingClarification"],
    text: str,
    current_segment_id: int,
) -> UnnumberedAnswerDecision:
    """判定一段无编号文本是否是对唯一待确认问题的回答。

    规则（全部满足才算回答）：
    1. 恰好一个待确认问题（多个或零个都不猜）；
    2. 文本是短句（长度上限），避免冗长陈述；
    3. 问题必须紧邻：问题来源段 + 1 == 当前段，
       否则无编号口述可能是隔了几段的新实验事实，须带编号；
    4. 文本提供了该问题缺失字段中的至少一个；
    5. 文本提供的所有字段都属于该问题缺失字段
       （夹带无关字段 = 新实验事实，如"加入5毫升缓冲液，加热到60摄氏度"）。

    不满足任何一条 → 非回答（保持原分类）。这保证了
    "加入5毫升缓冲液"这类实验记录（字段不匹配）绝不会被当作回答。
    """

    if len(pending_questions) != 1:
        return UnnumberedAnswerDecision(is_answer=False)

    if not isinstance(text, str) or not text.strip():
        return UnnumberedAnswerDecision(is_answer=False)
    if len(text) > _MAX_ANSWER_TEXT_LENGTH:
        return UnnumberedAnswerDecision(is_answer=False)

    question = pending_questions[0]
    # 规则3：问题必须紧邻（来源段+1 == 当前段）。
    if question.source_segment_id + 1 != current_segment_id:
        return UnnumberedAnswerDecision(is_answer=False)

    extracted = extract_entity_fields(text)
    if not extracted:
        return UnnumberedAnswerDecision(is_answer=False)

    missing = set(question.missing_fields)
    # 答案只能提供问题缺的字段：夹带无关字段（体积/浓度等）视为实验陈述。
    if not set(extracted).issubset(missing):
        return UnnumberedAnswerDecision(is_answer=False)
    matched = tuple(
        field_name
        for field_name in question.missing_fields
        if field_name in extracted
    )
    if not matched:
        return UnnumberedAnswerDecision(is_answer=False)

    return UnnumberedAnswerDecision(is_answer=True, fields=matched)
