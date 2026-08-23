# -*- coding: utf-8 -*-
"""实验室能力工具集：每个能力自描述、自注册，模型可直接调用。

参考 deepseek-harness 的「everything is a plugin」范式：
能力 = 名称 + 用途说明 + 参数 schema + 处理函数，集中注册、统一分发，
而不是把工具定义硬编码在调用处。新增能力只需在此文件加一个 @tool。

安全边界：
- 只读类工具（查安全、查步骤）可直接执行。
- 会改变会话状态的工具（切方案、推进步骤）也执行，但结果回传给用户可见。
- 任何工具都不写业务文件、不产生不可撤销副作用。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

import domain
import llm_bridge
from record_service import RecordCommand, SharedRecordService
from src.core.presentation_delivery import (
    PresentationDeliveryPlan,
    build_delivery_plan,
)
from src.core.rule_entity_extraction import extract_entities
from datetime import datetime, timedelta
import threading
import uuid

from database.lab_record_store import (
    current_session_id,
    list_records,
    next_segment_id,
    save_record,
)

_REGISTRY: dict = {}


@dataclass(frozen=True)
class PresentedToolResult:
    """Tool payload plus its deterministic, backend-owned presentation plan."""

    payload: Mapping[str, object]
    presentation_plan: PresentationDeliveryPlan

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))
        if not isinstance(self.presentation_plan, PresentationDeliveryPlan):
            raise TypeError("presentation_plan 必须是 PresentationDeliveryPlan。")

# 计时器（内存态，足够单机网页演示使用）
_timers: dict = {}
_timers_lock = threading.Lock()
_record_lock = threading.Lock()

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "results"
STEP_IMPROVEMENTS_FILE = RESULTS_DIR / "step_improvements.jsonl"


def tool(name: str, description: str, parameters: dict,
         kind: str = "other", title: str = "", present=None):
    """把一个函数注册成模型可调用的工具。

    参考 deepseek-harness 的 presentCall/presentResult 范式：工具自己声明
    「这次调用在界面上长什么样」，UI 按统一词汇渲染卡片，不为每个工具写特例。

    kind  取 read / execute / search / other，决定卡片图标与配色。
    title 是卡片标题模板，可用 {参数名} 占位。
    present 可选，接收 (args, result) 返回卡片摘要行列表。
    """
    def wrapper(func):
        _REGISTRY[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
            "handler": func,
            "kind": kind,
            "title": title or name,
            "present": present,
        }
        return func
    return wrapper


def present_call(name: str, arguments: dict) -> dict:
    """待执行卡片：模型刚决定调用、还没执行时显示。"""
    item = _REGISTRY.get(name)
    if item is None:
        return {"card": "generic", "kind": "other", "title": name, "status": "pending"}
    title = item["title"]
    for key, value in (arguments or {}).items():
        title = title.replace("{" + key + "}", str(value))
    return {"card": "generic", "kind": item["kind"], "title": title,
            "raw_input": arguments or {}, "status": "pending"}


def present_result(name: str, arguments: dict, outcome: dict) -> dict:
    """完成卡片：执行后显示结果摘要，失败时显示错误。"""
    view = present_call(name, arguments)
    if not outcome.get("ok"):
        view.update(status="error", lines=[str(outcome.get("error"))])
        return view
    item = _REGISTRY.get(name) or {}
    presenter = item.get("present")
    lines = []
    if presenter:
        try:
            lines = presenter(arguments or {}, outcome.get("result"))
        except Exception:
            lines = []
    view.update(status="done", lines=lines or [])
    return view


def openai_tools() -> list:
    """导出成 OpenAI function-calling 格式。"""
    return [
        {
            "type": "function",
            "function": {
                "name": item["name"],
                "description": item["description"],
                "parameters": item["parameters"],
            },
        }
        for item in _REGISTRY.values()
    ]


def call(name: str, arguments: dict) -> dict:
    """分发工具调用；未知工具与执行异常都返回结构化错误，不抛给主流程。"""
    item = _REGISTRY.get(name)
    if item is None:
        return {"ok": False, "error": "未注册的工具：" + str(name)}
    try:
        result = item["handler"](**(arguments or {}))
        if isinstance(result, PresentedToolResult):
            return {
                "ok": True,
                "result": dict(result.payload),
                "presentation_plan": result.presentation_plan,
            }
        return {"ok": True, "result": result}
    except Exception as error:
        return {"ok": False, "error": f"{type(error).__name__}: {error}"}


def names() -> list:
    return list(_REGISTRY.keys())


# ---------------- 实验方案 ----------------

@tool(
    "list_protocols",
    "列出所有可选的实验方案，包含方案名称、步骤总数和来源。用户问有哪些实验、想做什么实验时调用。",
    {"type": "object", "properties": {}, "additionalProperties": False},
    kind="search", title="查看可选实验方案",
    present=lambda a, r: [f"共 {len(r)} 份方案"] + [f"· {x['title']}（{x['total_steps']} 步）" for x in r[:6]],
)
def _list_protocols():
    return [
        {
            "protocol_id": p.protocol_id,
            "title": p.title,
            "total_steps": len(p.steps),
            "source": p.source,
        }
        for p in domain.protocols().list_all()
    ]


@tool(
    "select_protocol",
    "选择一份实验方案开始实验；protocol_id 传 null 表示自由记录模式（不按方案）。"
    "用户说要做某个实验时调用。",
    {
        "type": "object",
        "properties": {"protocol_id": {"type": ["string", "null"],
                                       "description": "方案ID，null表示自由记录"}},
        "required": ["protocol_id"],
        "additionalProperties": False,
    },
    kind="execute", title="选择实验方案 {protocol_id}",
    present=lambda a, r: ([f"已进入自由记录模式"] if r.get("mode") == "free" else
                          [f"方案：{r['protocol']['title']}",
                           f"共 {r['protocol']['total_steps']} 步，当前第 {r['step']['number']} 步：{r['step']['title']}"]),
)
def _select_protocol(protocol_id=None):
    return domain.step_view(domain.start_session(protocol_id or None))


@tool(
    "get_current_step",
    "查看当前实验进行到第几步、这一步方案规定了什么参数、现场必须记录什么、"
    "以及涉及试剂的安全提示。用户问“现在做到哪了”“这步要注意什么”时调用。",
    {"type": "object", "properties": {}, "additionalProperties": False},
    kind="read", title="查看当前步骤",
    present=lambda a, r: ([f"当前为自由记录模式"] if r.get("mode") == "free" else
                          [f"第 {r['step']['number']}/{r['protocol']['total_steps']} 步：{r['step']['title']}",
                           f"现场必测：{'、'.join(r['step']['must_record']) or '无'}"]
                          + [f"⚠ {s['name']}：{'；'.join(s['statements'][:1])}" for s in r.get("safety", []) if s.get("critical")]),
)
def _get_current_step():
    return domain.step_view(domain.session())


@tool(
    "move_step",
    "推进实验步骤。action 取 next（下一步）、prev（上一步）或 jump（跳到指定步）。"
    "只有用户明确表示要换步骤时才调用，不要自己猜测用户做到哪一步了。",
    {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["next", "prev", "jump"]},
            "step_number": {"type": ["integer", "null"], "description": "jump 时的目标步号"},
        },
        "required": ["action", "step_number"],
        "additionalProperties": False,
    },
    kind="execute", title="推进步骤 {action}",
    present=lambda a, r: ([f"当前为自由记录模式"] if r.get("mode") == "free" else
                          [f"已到第 {r['step']['number']}/{r['protocol']['total_steps']} 步：{r['step']['title']}"]),
)
def _move_step(action, step_number=None):
    return domain.step_view(domain.move(action, step_number))


# ---------------- 实验记录 ----------------

def _current_terms() -> tuple[str, ...]:
    step = domain.session().current_step()
    return tuple(step.terms) if step is not None else ()


def _next_record_segment(session_id: str) -> int:
    with _record_lock:
        return next_segment_id(session_id)


def _save_record_locked(item: dict[str, object]):
    with _record_lock:
        return save_record(item)


def _build_record_service() -> SharedRecordService:
    """Bind tool/runtime dependencies to the shared record application service."""

    return SharedRecordService(
        current_session_id=current_session_id,
        next_segment_id=_next_record_segment,
        list_records=list_records,
        extract_entities_llm=llm_bridge.extract,
        extract_entities_rule=extract_entities,
        current_terms=_current_terms,
        evaluate=domain.evaluate,
        step_view=lambda: domain.step_view(domain.session()),
        save_record=_save_record_locked,
        clock=datetime.now,
        request_id_factory=lambda: f"tool-{uuid.uuid4().hex[:12]}",
    )

@tool(
    "record_observation",
    "记录一段实验口述，系统会抽取其中的数量、单位、浓度、温度、时长等实测值，"
    "并按当前方案判断还缺什么、有没有偏离方案规定值。"
    "用户描述自己刚做了什么操作、测到什么数据时调用。",
    {
        "type": "object",
        "properties": {"transcript": {"type": "string", "description": "用户口述原文"}},
        "required": ["transcript"],
        "additionalProperties": False,
    },
    kind="execute", title="记录实验口述",
    present=lambda a, r: ([f"抽取：{'、'.join(f'{k}={v}' for k, v in r['entities'].items()) or '未抽到结构化字段'}"]
                          + ([f"缺失：{'、'.join(r['missing_fields'])}"] if r["missing_fields"] else ["本步记录已完整"])
                          + [f"⚠ 偏差：{d['field']} 实际 {d['actual_value']}，方案 {d['protocol_value']}" for d in r["deviations"]]),
)
def _record_observation(transcript):
    result = _build_record_service().record(RecordCommand(transcript=transcript))
    observation = result.observation_result
    saved_evaluation = result.saved_record.get("evaluation")
    evaluation = saved_evaluation if isinstance(saved_evaluation, dict) else {}
    payload = {
        "transcript": (
            observation.transcript
            if observation is not None
            else result.saved_record["transcript"]
        ),
        "entities": dict(
            observation.entities
            if observation is not None
            else result.saved_record.get("entities") or {}
        ),
        "missing_fields": list(
            observation.missing_fields
            if observation is not None
            else evaluation.get("missing_fields") or ()
        ),
        "follow_up_question": (
            observation.follow_up_question
            if observation is not None
            else evaluation.get("follow_up_question")
        ),
        "deviations": list(
            observation.deviations
            if observation is not None
            else evaluation.get("deviations") or ()
        ),
    }
    return PresentedToolResult(
        payload=payload,
        presentation_plan=build_delivery_plan(result.intents, ui_mode="user"),
    )


# ---------------- 时间 / 计时 ----------------

@tool(
    "get_current_time",
    "获取当前日期和本地时间。用户问现在几点、今天几号、实验时间安排时调用。",
    {"type": "object", "properties": {}, "additionalProperties": False},
    kind="read", title="查看当前时间",
    present=lambda a, r: [f"当前时间：{r['now']}（{r['weekday']}）"],
)
def _get_current_time():
    now = datetime.now()
    return {
        "now": now.strftime("%Y-%m-%d %H:%M:%S"),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": "星期" + "一二三四五六日"[now.weekday()],
        "unix_seconds": int(now.timestamp()),
    }


@tool(
    "start_timer",
    "启动一个计时器。用户说“计时X分钟/秒”“帮我定时”时调用。",
    {
        "type": "object",
        "properties": {
            "duration_seconds": {"type": "integer", "description": "计时时长（秒）"},
            "label": {"type": "string", "description": "计时器备注，如：水浴加热"},
        },
        "required": ["duration_seconds"],
        "additionalProperties": False,
    },
    kind="execute", title="启动计时器 {label}",
    present=lambda a, r: [f"计时器已启动：{r['label'] or '未命名'}，{r['duration_seconds']} 秒后结束"],
)
def _start_timer(duration_seconds, label=None):
    if not isinstance(duration_seconds, int) or duration_seconds <= 0:
        raise ValueError("duration_seconds 必须是正整数")
    timer_id = str(uuid.uuid4())[:8]
    now = datetime.now()
    end_at = now + timedelta(seconds=duration_seconds)
    timer = {
        "timer_id": timer_id,
        "label": label or "",
        "duration_seconds": duration_seconds,
        "started_at": now.isoformat(timespec="seconds"),
        "end_at": end_at.isoformat(timespec="seconds"),
    }
    with _timers_lock:
        _timers[timer_id] = timer
    return timer


@tool(
    "check_timer",
    "查询计时器剩余时间。用户问“还有多久”“时间到了吗”时调用。",
    {
        "type": "object",
        "properties": {"timer_id": {"type": "string", "description": "start_timer 返回的 timer_id"}},
        "required": ["timer_id"],
        "additionalProperties": False,
    },
    kind="read", title="查看计时器",
    present=lambda a, r: [f"计时器 {r['label'] or r['timer_id']}：{r['remaining_seconds']} 秒剩余"],
)
def _check_timer(timer_id):
    with _timers_lock:
        timer = _timers.get(timer_id)
        if timer is None:
            return {"found": False, "message": "没有找到这个计时器，请重新启动一个。"}
        end_at = datetime.fromisoformat(timer["end_at"])
        remaining = max(0, int((end_at - datetime.now()).total_seconds()))
        return {
            "found": True,
            "timer_id": timer_id,
            "label": timer["label"],
            "duration_seconds": timer["duration_seconds"],
            "started_at": timer["started_at"],
            "end_at": timer["end_at"],
            "remaining_seconds": remaining,
            "finished": remaining <= 0,
        }


@tool(
    "suggest_step_improvement",
    "当用户发现当前实验步骤有更好的做法、更贴近本实验室的操作，或想记录改进建议时调用。"
    "只负责记录，不直接修改方案。",
    {
        "type": "object",
        "properties": {"text": {"type": "string", "description": "用户提出的改进建议原文"}},
        "required": ["text"],
        "additionalProperties": False,
    },
    kind="execute", title="记录步骤改进建议",
    present=lambda a, r: [f"已记录：{r['text']}"],
)
def _suggest_step_improvement(text):
    text = str(text or "").strip()
    if not text:
        raise ValueError("改进建议不能为空")
    state = domain.session()
    step = state.current_step()
    protocol = state.selection.protocol
    item = {
        "at": datetime.now().isoformat(timespec="seconds"),
        "protocol_id": protocol.protocol_id if protocol else None,
        "protocol_title": protocol.title if protocol else None,
        "step_number": step.step_number if step else None,
        "step_title": step.title if step else None,
        "text": text,
    }
    RESULTS_DIR.mkdir(exist_ok=True)
    with STEP_IMPROVEMENTS_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    return item


# ---------------- 试剂安全 ----------------

@tool(
    "check_reagent_safety",
    "查询试剂的危险性信息，包含 CAS 号、GHS 危险性说明和高危提示。"
    "用户问某个试剂有没有毒、要注意什么、能不能直接倒掉时调用。"
    "数据来自 PubChem，未经实验室安全负责人复核，不能替代 MSDS。",
    {
        "type": "object",
        "properties": {"reagent": {"type": "string", "description": "试剂中文名，如 氢氧化钠"}},
        "required": ["reagent"],
        "additionalProperties": False,
    },
    kind="read", title="查询试剂安全：{reagent}",
    present=lambda a, r: ([r["message"]] if not r.get("found") else
                          [f"{r['name']}（CAS {r['cas'] or '未获取'}）"]
                          + ([f"⚠ 高危 {'/'.join(r['critical_codes'])}"] if r["critical"] else ["无高危项"])
                          + r["statements"][:3]),
)
def _check_reagent_safety(reagent):
    store = domain.hazmat()
    found = store.find(reagent) or (store.find_in_text(reagent) or [None])[0]
    if found is None:
        return {
            "found": False,
            "message": "知识库中没有这种试剂，不能据此认为它安全。请查阅 MSDS。",
        }
    return {
        "found": True,
        "name": found.name_zh,
        "cas": found.cas,
        "molecular_formula": found.molecular_formula,
        "critical": found.is_critical,
        "critical_codes": list(found.critical_codes),
        "statements": [s.text for s in found.hazard_statements],
        "disclaimer": store.authority_note,
    }
