"""呈现文案目录：把语义意图翻译成指定模式的最终文字。"""

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from src.core.presentation_intent import MessageKind, PresentationIntent


class RecordAckResult(str, Enum):
    """实验记录回执的三种真实结果。"""

    RECORDED = "recorded"
    DEGRADED = "degraded"
    FAILED = "failed"


class ConfirmationAckResult(str, Enum):
    """问题确认回执的两种真实结果。"""

    ANSWERED = "answered"
    CONFIRMED = "confirmed"


class ProgramStatus(str, Enum):
    """程序级用户可见状态；不与会话内业务阶段混用。"""

    STARTING = "starting"
    READY = "ready"
    WAITING = "waiting"
    EXITED = "exited"


@dataclass(frozen=True)
class ReviewItem:
    """查看结果里的一条待确认项（只读快照）。"""

    display_number: int
    is_deferred: bool
    question: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.display_number, int)
            or isinstance(self.display_number, bool)
            or self.display_number <= 0
        ):
            raise ValueError("display_number 必须是正整数。")
        if not isinstance(self.is_deferred, bool):
            raise TypeError("is_deferred 必须是布尔值。")
        if not self.question.strip():
            raise ValueError("question 不能为空。")


@dataclass(frozen=True)
class EventPreview:
    """规范记录预览：只透传 normalized_text，不新增模型调用。"""

    normalized_text: str

    def __post_init__(self) -> None:
        if not isinstance(self.normalized_text, str):
            raise TypeError("normalized_text 必须是字符串。")
        if not self.normalized_text.strip():
            raise ValueError("normalized_text 不能为空。")


_FIELD_LABELS = {
    "action": "操作",
    "object": "对象",
    "instrument": "仪器",
    "amount_value": "用量",
    "amount_unit": "单位",
    "concentration": "浓度",
    "temperature": "温度",
    "duration": "时间",
    "condition": "条件",
    "observation": "观察",
}


_PASSTHROUGH_KINDS = frozenset({
    MessageKind.TRANSCRIPT,
    MessageKind.STAGE_SUMMARY,
    MessageKind.SYSTEM_ISSUE,
})


def copy_for_intent(
    intent: PresentationIntent,
    *,
    ui_mode: str,
) -> str:
    """生成最终文案；支持记录回执、追问、回答/确认回执、暂缓、查看列表与固定提示。"""

    _validate_ui_mode(ui_mode)
    if intent.kind == MessageKind.PROGRAM_STATUS:
        return _copy_program_status(intent)
    if intent.kind == MessageKind.WAKE_ACK:
        return _copy_wake_ack(intent)
    if intent.kind in _PASSTHROUGH_KINDS:
        return _copy_passthrough(intent)
    if intent.kind == MessageKind.RECORD_ACK:
        return _copy_record_ack(intent, ui_mode)
    if intent.kind == MessageKind.CLARIFICATION:
        return _copy_clarification(intent, ui_mode)
    if intent.kind == MessageKind.CONFIRMATION_ACK:
        return _copy_confirmation_ack(intent, ui_mode)
    if intent.kind == MessageKind.NO_ACTION_FEEDBACK:
        return _copy_no_action_feedback(intent, ui_mode)
    if intent.kind == MessageKind.CLARIFICATION_DEFERRED:
        return _copy_deferred(intent, ui_mode)
    if intent.kind == MessageKind.CLARIFICATION_REVIEW:
        return _copy_review(intent)
    if intent.kind == MessageKind.SESSION_CLOSING_SUMMARY:
        return _copy_session_closing_summary(intent)
    raise ValueError(f"文案目录暂不支持消息类型 {intent.kind.value}。")


def _validate_ui_mode(ui_mode: str) -> None:
    if ui_mode not in {"user", "admin"}:
        raise ValueError("ui_mode 必须是 user 或 admin。")


def _copy_program_status(intent: PresentationIntent) -> str:
    try:
        status = ProgramStatus(intent.args["status"])
    except KeyError as error:
        raise ValueError("PROGRAM_STATUS 缺少 status 参数。") from error
    except ValueError as error:
        raise ValueError("PROGRAM_STATUS 的 status 参数不受支持。") from error

    return {
        ProgramStatus.STARTING: "实验语音智能体正在启动，请稍候。",
        ProgramStatus.READY: (
            "实验语音智能体已就绪，正在等待唤醒。"
            "按 Ctrl+C 可以退出程序。"
        ),
        ProgramStatus.WAITING: (
            "已返回待机。可以再次说“小科小科”开始新会话；"
            "按 Ctrl+C 退出程序。"
        ),
        ProgramStatus.EXITED: "已退出实验语音智能体。",
    }[status]


def _copy_wake_ack(intent: PresentationIntent) -> str:
    keyword = intent.args.get("keyword")
    if not isinstance(keyword, str) or not keyword.strip():
        raise ValueError("WAKE_ACK 必须包含非空 keyword。")
    return f"唤醒成功：{keyword.strip()}"


def _copy_passthrough(intent: PresentationIntent) -> str:
    """固定提示类消息透传 args["text"]，不做翻译。"""

    text = intent.args.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"{intent.kind.value} 必须包含非空 text。")
    return text


def _with_source(base: str, intent: PresentationIntent, ui_mode: str) -> str:
    """admin 模式追加来源口述编号；调用方保证 base 不含句尾标点。"""

    if ui_mode == "admin" and intent.source_segment_id is not None:
        return f"{base}（来源口述 {intent.source_segment_id}）。"
    if base.endswith(("。", "！", "？", "；")):
        return base
    return f"{base}。"


def _copy_record_ack(intent: PresentationIntent, ui_mode: str) -> str:
    try:
        result = RecordAckResult(intent.args["result"])
    except KeyError as error:
        raise ValueError("RECORD_ACK 缺少 result 参数。") from error
    except ValueError as error:
        raise ValueError("RECORD_ACK 的 result 参数不受支持。") from error

    if result == RecordAckResult.RECORDED:
        step_number = _require_positive_int(intent.args, "step_number")
        previews = intent.args.get("event_previews", ())
        if not _is_event_preview_tuple(previews):
            raise ValueError(
                "RECORD_ACK 的 event_previews 必须是 EventPreview 元组。"
            )
        if previews:
            preview_text = "；".join(
                item.normalized_text for item in previews
            )
            base = f"已记录实验步骤 {step_number}：{preview_text}"
        else:
            base = f"已记录实验步骤 {step_number}"
    elif result == RecordAckResult.DEGRADED:
        base = "原始记录已保存，结构化处理暂时不可用"
    else:
        base = "本段结构化处理失败，原始记录已保存"

    return _with_source(base, intent, ui_mode)


def _copy_clarification(intent: PresentationIntent, ui_mode: str) -> str:
    question = intent.args.get("question")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("CLARIFICATION 必须包含非空 question。")

    base = f"小科：{question}"
    if ui_mode == "admin" and intent.source_segment_id is not None:
        return f"{base}（来源口述 {intent.source_segment_id}）"
    return base


def _copy_confirmation_ack(intent: PresentationIntent, ui_mode: str) -> str:
    try:
        result = ConfirmationAckResult(intent.args["result"])
    except KeyError as error:
        raise ValueError("CONFIRMATION_ACK 缺少 result 参数。") from error
    except ValueError as error:
        raise ValueError("CONFIRMATION_ACK 的 result 参数不受支持。") from error

    display_number = _require_positive_int(intent.args, "display_number")

    if result == ConfirmationAckResult.CONFIRMED:
        base = _copy_confirmed(display_number, intent.args)
    else:
        base = _copy_answered(display_number, intent.args)

    return _with_source(base, intent, ui_mode)


def _copy_confirmed(display_number: int, args: Mapping[str, object]) -> str:
    resolved = args.get("resolved", False)
    if not isinstance(resolved, bool):
        raise ValueError("CONFIRMED 的 resolved 必须是布尔值。")
    remaining_fields = args.get("remaining_fields", ())
    if not _is_field_tuple(remaining_fields):
        raise ValueError(
            "CONFIRMED 的 remaining_fields 必须是字段名字符串元组。"
        )

    if resolved:
        return f"已确认并补充问题 {display_number}，问题已解决"
    if remaining_fields:
        labels = "、".join(_translate_fields(remaining_fields))
        return f"已确认问题 {display_number}，仍需补充：{labels}"
    return f"已确认问题 {display_number}"


def _copy_answered(display_number: int, args: Mapping[str, object]) -> str:
    resolved = args.get("resolved", False)
    if not isinstance(resolved, bool):
        raise ValueError("ANSWERED 的 resolved 必须是布尔值。")
    remaining_fields = args.get("remaining_fields", ())
    if not _is_field_tuple(remaining_fields):
        raise ValueError(
            "ANSWERED 的 remaining_fields 必须是字段名字符串元组。"
        )

    if resolved:
        return f"已补充问题 {display_number}，问题已解决"
    if remaining_fields:
        labels = "、".join(_translate_fields(remaining_fields))
        return f"已补充问题 {display_number}，仍需补充：{labels}"
    return f"已补充问题 {display_number}，仍需确认"


def _copy_no_action_feedback(intent: PresentationIntent, ui_mode: str) -> str:
    reason = intent.args.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("NO_ACTION_FEEDBACK 必须包含非空 reason。")

    if "编号不存在" in reason:
        base = "没有找到你指定的问题编号，请先查看当前待确认问题"
    elif "缺少答案" in reason:
        base = "请说明要回答的内容，例如“问题1，50毫升”"
    elif "当前没有" in reason:
        base = "当前没有可以执行这个操作的问题"
    elif "弃权" in reason or "没把握" in reason:
        base = "我听到了，但没把握安全地执行，请换个说法试试"
    else:
        base = "我听到了，但暂时无法处理这句话"

    return _with_source(base, intent, ui_mode)


def _copy_deferred(intent: PresentationIntent, ui_mode: str) -> str:
    display_number = _require_positive_int(intent.args, "display_number")
    base = f"问题 {display_number} 已暂缓"
    return _with_source(base, intent, ui_mode)


def _copy_review(intent: PresentationIntent) -> str:
    """查看列表不区分 user/admin：列表本身就是定位信息。"""

    items = intent.args.get("items")
    if not isinstance(items, tuple) or not all(
        isinstance(item, ReviewItem) for item in items
    ):
        raise ValueError("CLARIFICATION_REVIEW 的 items 必须是 ReviewItem 元组。")

    if not items:
        return "当前没有待确认问题。"

    lines = [f"当前共有 {len(items)} 个待确认问题："]
    for item in items:
        status = "已暂缓" if item.is_deferred else "待回答"
        lines.append(f"- 问题 {item.display_number}（{status}）：{item.question}")
    return "\n".join(lines)


def _copy_session_closing_summary(intent: PresentationIntent) -> str:
    """生成 END_ONLY 单一结束摘要。

    摘要同时承载已记录实验步骤数和未解决待确认项，避免结束阶段
    再另行投递 CLARIFICATION_REVIEW。
    """

    experiment_step_count = intent.args.get("experiment_step_count")
    if (
        not isinstance(experiment_step_count, int)
        or isinstance(experiment_step_count, bool)
        or experiment_step_count < 0
    ):
        raise ValueError("experiment_step_count 必须是非负整数。")

    items = intent.args.get("pending_items")
    if not isinstance(items, tuple) or not all(
        isinstance(item, ReviewItem) for item in items
    ):
        raise ValueError(
            "SESSION_CLOSING_SUMMARY 的 pending_items 必须是 ReviewItem 元组。"
        )

    lines = [
        "实验记录会话已结束。",
        f"本次共记录 {experiment_step_count} 个实验步骤。",
    ]
    if not items:
        lines.append("没有待确认问题。")
        return "\n".join(lines)

    lines.append(f"仍有 {len(items)} 个待确认问题：")
    for item in items:
        status = "已暂缓" if item.is_deferred else "待回答"
        lines.append(f"- 问题 {item.display_number}（{status}）：{item.question}")
    return "\n".join(lines)


def _require_positive_int(args: Mapping[str, object], key: str) -> int:
    value = args.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{key} 必须是正整数。")
    return value


def _is_field_tuple(value: object) -> bool:
    if not isinstance(value, tuple):
        return False
    return all(isinstance(item, str) and item.strip() for item in value)


def _is_event_preview_tuple(value: object) -> bool:
    return isinstance(value, tuple) and all(
        isinstance(item, EventPreview) for item in value
    )


def _translate_fields(fields: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(_FIELD_LABELS.get(field, field) for field in fields)
