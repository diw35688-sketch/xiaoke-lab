# -*- coding: utf-8 -*-
from __future__ import annotations

"""时间/计时/时间引擎（由 lab_tools.py 拆分生成）。"""

import json
import re
import uuid
import threading
from datetime import datetime, timedelta
from pathlib import Path

from lab_tools_registry import (
    _REGISTRY, tool, PresentedToolResult, _attach_artifact,
    present_call, present_result,
    REPO_ROOT, RESULTS_DIR, STEP_IMPROVEMENTS_FILE,
    _timers, _timers_lock, _record_lock,
    domain, llm_bridge, settings_store,
    RecordCommand, SharedRecordService,
    generate_schedule, format_schedule_brief,
    get_remaining_schedule, format_remaining_brief,
    get_step_profile, get_next_passive_window,
    plan_multi_protocols, format_multi_protocol_brief,
    plan_clock_schedule,
    PresentationDeliveryPlan, build_delivery_plan,
    extract_entities,
    current_session_id, list_records, next_segment_id, save_record,
    save_protocol_preference, get_protocol_preference,
)

# ---------------- 时间 / 计时 ----------------

@tool(
    "get_current_time",
    "获取当前日期和本地时间。用户问现在几点、今天几号、实验时间安排时调用。",
    {"type": "object", "properties": {}, "additionalProperties": False},
    kind="read", title="查看当前时间", experiment_command=True,
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


def _start_timer_immediate(duration_seconds, label=None):
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
        "recorded": False,
        "pending": False,
    }
    with _timers_lock:
        _timers[timer_id] = timer
    return timer


@tool(
    "start_timer",
    "启动一个计时器。用户说“计时X分钟/秒”“帮我定时”时调用。自动按识别到的名称和时长开始，不需要用户再确认。只负责计时，不要用本工具记录实验数据或修改方案。",
    {
        "type": "object",
        "properties": {
            "duration_seconds": {"type": "integer", "description": "计时时长（秒）"},
            "label": {"type": "string", "description": "计时器名称，如：水浴加热"},
        },
        "required": ["duration_seconds"],
        "additionalProperties": False,
    },
    kind="execute", title="启动计时器 {label}", experiment_command=True,
    present=lambda a, r: [f"计时器已启动：{r['label'] or '未命名'}，{r['duration_seconds']} 秒后结束"],
)
def _start_timer(duration_seconds, label=None):
    """Agent 工具入口：直接开始计时，不需要用户点击确认。"""
    return _start_timer_immediate(duration_seconds, label=label)


def _request_timer(duration_seconds, label=None):
    """由 Agent 工具调用：先创建待确认计时器，等用户在弹窗确认后才真正开始。"""
    if not isinstance(duration_seconds, int) or duration_seconds <= 0:
        raise ValueError("duration_seconds 必须是正整数")
    timer_id = str(uuid.uuid4())[:8]
    now = datetime.now()
    timer = {
        "timer_id": timer_id,
        "label": label or "",
        "duration_seconds": duration_seconds,
        "started_at": now.isoformat(timespec="seconds"),
        "end_at": None,
        "recorded": False,
        "pending": True,
        "created_at": now.isoformat(timespec="seconds"),
    }
    with _timers_lock:
        _timers[timer_id] = timer
    return timer


def accept_pending_timer(
    timer_id: str,
    *,
    label: str | None = None,
    duration_seconds: int | None = None,
) -> dict:
    """确认待确认计时器，真正开始倒计时；可同时修改名称/时长。"""
    with _timers_lock:
        timer = _timers.get(timer_id)
        if timer is None or not timer.get("pending"):
            raise ValueError("没有找到待确认的计时器。")
        if duration_seconds is not None:
            if not isinstance(duration_seconds, int) or duration_seconds <= 0:
                raise ValueError("duration_seconds 必须是正整数")
            timer["duration_seconds"] = duration_seconds
        if label is not None:
            timer["label"] = (label or "").strip()
        timer["pending"] = False
        timer["end_at"] = (
            datetime.now() + timedelta(seconds=timer["duration_seconds"])
        ).isoformat(timespec="seconds")
        return dict(timer)


@tool(
    "check_timer",
    "查询计时器剩余时间。用户问“还有多久”“时间到了吗”时调用。只读，不修改计时器；不要用于记录实验数据。",
    {
        "type": "object",
        "properties": {"timer_id": {"type": "string", "description": "start_timer 返回的 timer_id"}},
        "required": ["timer_id"],
        "additionalProperties": False,
    },
    kind="read", title="查看计时器", experiment_command=True,
    present=lambda a, r: [f"计时器 {r['label'] or r['timer_id']}：{r['remaining_seconds']} 秒剩余"],
)
def _check_timer(timer_id):
    with _timers_lock:
        timer = _timers.get(timer_id)
        if timer is None:
            return {"found": False, "message": "没有找到这个计时器，请重新启动一个。"}
        if timer.get("pending"):
            return {
                "found": True,
                "timer_id": timer_id,
                "label": timer["label"],
                "duration_seconds": timer["duration_seconds"],
                "started_at": timer.get("started_at"),
                "end_at": None,
                "remaining_seconds": timer["duration_seconds"],
                "finished": False,
                "pending": True,
            }
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
            "pending": False,
        }


def list_active_timers() -> list[dict]:
    """返回全部计时器的活动/待确认/结束快照，供 API 和前端轮询。"""
    now = datetime.now()
    with _timers_lock:
        result = []
        for timer_id, timer in list(_timers.items()):
            if timer.get("pending"):
                result.append({
                    "timer_id": timer_id,
                    "label": timer["label"],
                    "duration_seconds": timer["duration_seconds"],
                    "started_at": timer.get("started_at"),
                    "end_at": None,
                    "remaining_seconds": timer["duration_seconds"],
                    "finished": False,
                    "pending": True,
                    "created_at": timer.get("created_at"),
                })
                continue
            end_at = datetime.fromisoformat(timer["end_at"])
            remaining = max(0, int((end_at - now).total_seconds()))
            finished = remaining <= 0
            # 计时器到点后自动写一条实验记录（只写一次，内存标记防重）。
            if finished and not timer.get("recorded"):
                timer["recorded"] = True
                label = timer.get("label") or "未命名计时器"
                try:
                    save_record({
                        "transcript": f"[计时结束] {label}",
                        "entities": {
                            "timer_id": timer_id,
                            "duration_seconds": timer["duration_seconds"],
                            "label": label,
                        },
                        "evaluation": {},
                        "extraction_source": "timer",
                        "step": None,
                        "at": now.isoformat(timespec="seconds"),
                    })
                except Exception:
                    # 自动记录失败不应影响计时器展示；下轮不再重试。
                    pass
            result.append({
                "timer_id": timer_id,
                "label": timer["label"],
                "duration_seconds": timer["duration_seconds"],
                "started_at": timer["started_at"],
                "end_at": timer["end_at"],
                "remaining_seconds": remaining,
                "finished": finished,
                "pending": False,
            })
        result.sort(key=lambda item: (1 if item.get("pending") else 0, item.get("end_at") or "", item["timer_id"]))
        return result


def create_timer(duration_seconds: int, label: str | None = None) -> dict:
    """API/前端创建计时器；与 Agent 工具共用同一个内存注册表。"""
    return _start_timer_immediate(duration_seconds, label=label)


def cancel_timer(timer_id: str) -> bool:
    with _timers_lock:
        if timer_id not in _timers:
            return False
        _timers.pop(timer_id, None)
        return True


# ---------------- 时间引擎 ----------------

@tool(
    "generate_schedule",
    "根据当前实验方案生成时间规划。分析每一步是「动手操作」还是「机器等待」，"
    "计算总耗时和等待窗口，给出等待期间可以做的并行建议。"
    "用户说'帮我安排时间''怎么做最快''要多久'时调用。",
    {"type": "object", "properties": {}, "additionalProperties": False},
    kind="read", title="时间规划", experiment_command=True,
    present=lambda a, r: format_schedule_brief(r),
)
def _generate_schedule():
    """读取当前方案的步骤，生成时间规划。"""
    from harness_context import get_current_protocol_id
    protocol_id = get_current_protocol_id()
    if not protocol_id:
        return {
            "protocol_id": None,
            "protocol_title": "",
            "total_steps": 0,
            "total_seconds": 0,
            "total_label": "未知",
            "active_seconds": 0,
            "passive_seconds": 0,
            "active_label": "未知",
            "passive_label": "未知",
            "passive_ratio": 0,
            "passive_windows": [],
            "timeline": [],
        }
    return generate_schedule(protocol_id)


@tool(
    "get_remaining_schedule",
    "从当前步骤开始计算剩余时间规划。用户做到一半问'还有多久''剩下要多久'"
    "'后面还要做什么'时调用。会标注接下来的步骤和下一个等待窗口。",
    {"type": "object", "properties": {}, "additionalProperties": False},
    kind="read", title="剩余时间规划", experiment_command=True,
    present=lambda a, r: format_remaining_brief(r),
)
def _get_remaining_schedule():
    """从当前步骤开始计算剩余时间规划。"""
    from harness_context import get_current_protocol_id
    protocol_id = get_current_protocol_id()
    if not protocol_id:
        return {
            "protocol_id": None, "protocol_title": "", "from_step": 0,
            "remaining_seconds": 0, "remaining_label": "未选定方案",
            "remaining_active_seconds": 0, "remaining_passive_seconds": 0,
            "remaining_active_label": "", "remaining_passive_label": "",
            "next_passive_window": None, "timeline": [],
        }
    # 获取当前步骤号
    state = domain.session()
    from_step = 1
    if state.selection.has_protocol:
        try:
            cs = state.current_step()
            if cs:
                from_step = cs.step_number
        except Exception:
            pass
    return get_remaining_schedule(protocol_id, from_step)


@tool(
    "start_step_timer",
    "为当前步骤启动计时器。从方案时间画像自动获取该步骤的预计时长。"
    "到达被动等待步骤（离心、孵育、电泳等）时调用——不需要用户说具体时长，"
    "系统会从方案里查出。如果当前步没有时长数据则返回提示。",
    {"type": "object", "properties": {}, "additionalProperties": False},
    kind="execute", title="启动步骤计时器", experiment_command=True,
    present=lambda a, r: r.get("present_lines", [f"已启动计时器：{r.get('label','')}，{r.get('duration_seconds',0)} 秒"]),
)
def _start_step_timer():
    """为当前被动步骤自动启动计时器。"""
    from harness_context import get_current_protocol_id
    protocol_id = get_current_protocol_id()
    if not protocol_id:
        return {"ok": False, "message": "当前没有选定方案。"}

    state = domain.session()
    if not state.selection.has_protocol:
        return {"ok": False, "message": "当前没有选定方案。"}

    step = state.current_step()
    if not step:
        return {"ok": False, "message": "无法确定当前步骤。"}

    profile = get_step_profile(protocol_id, step.step_number)
    if not profile:
        return {"ok": False, "message": f"第{step.step_number}步没有时间画像数据。"}

    duration = profile.get("duration_seconds", 0)
    if not duration or duration < 10:
        return {
            "ok": False,
            "message": f"第{step.step_number}步「{step.title}」预计耗时太短（{duration}秒），不需要计时器。",
        }

    wait_type = profile.get("wait_type", "active")
    label = step.title
    timer = _start_timer_immediate(duration, label=label)
    result = dict(timer)
    result["ok"] = True
    result["wait_type"] = wait_type
    result["step_number"] = step.step_number
    result["parallel_suggestions"] = profile.get("parallel_suggestions", [])
    # 为 present 提供
    lines = [f"计时器已启动：{label}，{_duration_label(duration)}后结束"]
    sugg = profile.get("parallel_suggestions", [])
    if sugg:
        lines.append(f"等待期间可做：{'、'.join(sugg[:3])}")
    result["present_lines"] = lines
    return result


def _duration_label(seconds: int) -> str:
    """秒 → 可读时长（与 time_engine._fmt_duration 一致）。"""
    if seconds <= 0:
        return "0分钟"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    parts = []
    if hours:
        parts.append(f"{hours}小时")
    if minutes:
        parts.append(f"{minutes}分钟")
    if secs and not hours:
        parts.append(f"{secs}秒")
    return "".join(parts) if parts else "0分钟"


@tool(
    "plan_multi_protocols",
    "分析多个实验方案的时间安排，检测设备冲突，给出交错优化建议。"
    "用户说'今天要做A和B''帮我安排两个实验''怎么做最快'时调用。"
    "传入 protocol_ids 数组。",
    {
        "type": "object",
        "properties": {
            "protocol_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要规划的方案 ID 列表",
            },
        },
        "required": ["protocol_ids"],
        "additionalProperties": False,
    },
    kind="read", title="跨实验规划", experiment_command=True,
    present=lambda a, r: format_multi_protocol_brief(r),
)
def _plan_multi_protocols(protocol_ids):
    return plan_multi_protocols(protocol_ids)


@tool(
    "plan_clock_schedule",
    "按用户作息时间做时钟规划：把每个步骤投射到真实钟点，标出午饭/下班/过夜节点。"
    "用户说'我9点开始''几点能做完''来得及午饭前做吗'时调用。"
    "work_start 是开始时间（HH:MM），lunch_start/lunch_end 是午休，work_end 是下班。"
    "如果用户没说全部时间，用默认值（09:00/12:00-13:00/18:00）。",
    {
        "type": "object",
        "properties": {
            "work_start": {"type": "string", "description": "开始时间 HH:MM，如 09:00", "default": "09:00"},
            "lunch_start": {"type": "string", "description": "午休开始 HH:MM", "default": "12:00"},
            "lunch_end": {"type": "string", "description": "午休结束 HH:MM", "default": "13:00"},
            "work_end": {"type": "string", "description": "下班时间 HH:MM", "default": "18:00"},
        },
        "additionalProperties": False,
    },
    kind="read", title="时钟规划", experiment_command=True,
    present=lambda a, r: r.get("summary_lines", ["无法生成时钟规划。"]),
)
def _plan_clock_schedule(work_start="09:00", lunch_start="12:00", lunch_end="13:00", work_end="18:00"):
    from harness_context import get_current_protocol_id
    protocol_id = get_current_protocol_id()
    if not protocol_id:
        return {"summary_lines": ["当前没有选定方案。请先选定一个实验方案。"]}
    return plan_clock_schedule(
        protocol_id,
        work_start=work_start or "09:00",
        lunch_start=lunch_start or "12:00",
        lunch_end=lunch_end or "13:00",
        work_end=work_end or "18:00",
    )


@tool(
    "list_experiment_commands",
    "列出实验记录过程中当前允许小科调用的全部工具。用户问“小科你能做什么”、"
    "“有哪些工具”或“支持什么功能”时调用。清单直接来自工具注册表。",
    {"type": "object", "properties": {}, "additionalProperties": False},
    kind="read", title="查看小科当前可用工具", experiment_command=True,
    present=lambda a, r: [
        f"{item['title']}：{item['description']}" for item in r["tools"]
    ] or ["当前没有开放的实验工具。"],
)
def _list_experiment_commands():
    tools = experiment_command_catalog()
    return {"count": len(tools), "tools": tools}


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

