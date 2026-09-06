"""任务层上下文：告诉统一理解器"现在在做哪个实验的第几步"。

为什么需要这一层
----------------
2026-08-30 诊断：统一理解器此前只拿到 5 个字段（本轮原文、最近事件、
session_active、待确认编号、当前编号），**看不到方案与当前步骤**。
用户点"开始实验"后，`domain.step_view()` 的结果只喂给了前端画卡片，
从未进入提示词。于是模型在"不知道你在做什么"的前提下给一句话分类，
听错术语、认不出指代、把本步该关注的量当成闲聊——即"聊天很费劲"的主因。

这一层解决什么、不解决什么
--------------------------
只解决**接地与消歧**：让模型知道本步在做什么、该出现哪些量、专业术语怎么写，
从而听得准、分得对。

**不参与决策**：缺哪项、偏差多少、能不能进下一步，全部由
`domain.evaluate_for_state()` 确定性判定。模型不得代劳，也不得把
"预期值"当作"已发生的事实"写进事件——那是拿方案编造记录，比听错更危险。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


def _clean(value: Any) -> str | None:
    """把任意输入收敛成非空字符串或 None，避免空白污染提示词。"""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_tuple(values: Any) -> tuple[str, ...]:
    if not values:
        return ()
    if isinstance(values, (str, bytes)):
        single = _clean(values)
        return (single,) if single else ()
    out = []
    for item in values:
        text = _clean(item)
        if text and text not in out:
            out.append(text)
    return tuple(out)


@dataclass(frozen=True)
class TaskContext:
    """当前实验任务的只读快照。free 模式下所有字段为空，代表"自由记录"。"""

    mode: str = "free"
    protocol_title: str | None = None
    step_number: int | None = None
    total_steps: int | None = None
    step_title: str | None = None
    step_instruction: str | None = None
    expected_values: tuple[tuple[str, str], ...] = ()
    must_record: tuple[str, ...] = ()
    recorded_fields: tuple[str, ...] = ()
    missing_fields: tuple[str, ...] = ()
    hazard_note: str | None = None
    terms: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.mode not in ("free", "protocol"):
            raise ValueError("TaskContext.mode 只能是 free 或 protocol。")
        if self.mode == "protocol":
            if self.step_number is None or self.step_number <= 0:
                raise ValueError("方案模式必须有正整数步号。")
            if not self.protocol_title:
                raise ValueError("方案模式必须有方案标题。")

    @property
    def is_free(self) -> bool:
        return self.mode == "free"

    @classmethod
    def free(cls) -> "TaskContext":
        return cls(mode="free")

    @classmethod
    def from_step_view(cls, view: Mapping[str, Any] | None) -> "TaskContext":
        """由 `domain.step_view()` 的返回值构造；结构不符一律退回自由模式。

        宽容解析是刻意的：任务层缺失只该让模型少知道一点，
        绝不能让一次口述因为视图字段变动而整轮失败。
        """
        if not isinstance(view, Mapping) or view.get("mode") != "protocol":
            return cls.free()
        step = view.get("step")
        protocol = view.get("protocol")
        if not isinstance(step, Mapping) or not isinstance(protocol, Mapping):
            return cls.free()
        try:
            number = int(step.get("number"))
        except (TypeError, ValueError):
            return cls.free()
        title = _clean(protocol.get("title"))
        if number <= 0 or not title:
            return cls.free()

        raw_expected = step.get("protocol_values")
        expected: list[tuple[str, str]] = []
        if isinstance(raw_expected, Mapping):
            for key, value in raw_expected.items():
                name, text = _clean(key), _clean(value)
                if name and text:
                    expected.append((name, text))

        try:
            total = int(protocol.get("total_steps"))
        except (TypeError, ValueError):
            total = None

        return cls(
            mode="protocol",
            protocol_title=title,
            step_number=number,
            total_steps=total if total and total > 0 else None,
            step_title=_clean(step.get("title")),
            step_instruction=_clean(step.get("instruction")),
            expected_values=tuple(expected),
            must_record=_clean_tuple(step.get("must_record")),
            recorded_fields=_clean_tuple(step.get("recorded")),
            missing_fields=_clean_tuple(step.get("missing")),
            hazard_note=_clean(step.get("hazard_note")),
            terms=_clean_tuple(step.get("terms")),
        )

    def to_prompt_payload(self) -> dict[str, Any] | None:
        """编码成提示词里的 JSON 数据；自由模式返回 None（不占提示词预算）。"""
        if self.is_free:
            return None
        payload: dict[str, Any] = {
            "protocol_title": self.protocol_title,
            "step_number": self.step_number,
        }
        if self.total_steps is not None:
            payload["total_steps"] = self.total_steps
        for key, value in (
            ("step_title", self.step_title),
            ("step_instruction", self.step_instruction),
            ("hazard_note", self.hazard_note),
        ):
            if value:
                payload[key] = value
        if self.expected_values:
            payload["expected_values"] = dict(self.expected_values)
        for key, value in (
            ("must_record", self.must_record),
            ("already_recorded", self.recorded_fields),
            ("still_missing", self.missing_fields),
            ("glossary", self.terms),
        ):
            if value:
                payload[key] = list(value)
        return payload
