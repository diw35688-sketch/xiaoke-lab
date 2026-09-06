# -*- coding: utf-8 -*-
"""实验室时间引擎：从方案步骤生成优化时间线，标注等待窗口和并行建议。

核心流程：
  1. 解析每步 duration 文本 → 秒
  2. 分类步骤：active（手在动）/ passive（机器在跑）/ flexible（随时能做）
  3. 生成时间线：串联关键路径，passive 窗口里插入并行建议
  4. 输出可读的时间规划

步骤画像通过 LLM 提取（首次），持久化到 step_time_profiles 表。
"""

from __future__ import annotations

import json
import re

import domain


# ── 时间解析 ──

_UNIT_SECONDS = {
    "秒": 1, "sec": 1, "s": 1,
    "分钟": 60, "min": 60, "m": 60,
    "小时": 3600, "hour": 3600, "h": 3600, "hr": 3600,
    "过夜": 8 * 3600, "overnight": 8 * 3600,
    "天": 86400, "day": 86400,
}

_RANGE_SEPARATORS = r"[\-–—~～到或]"


def parse_duration(text: str) -> int | None:
    """把方案里的 duration 文本解析成秒数。

    "5 min" → 300
    "1 h" → 3600
    "10-15秒" → 750（取中间值）
    "10–15秒" → 750
    "" → None
    """
    if not text:
        return None
    text = str(text).strip()
    if not text:
        return None
    lower = text.lower()

    # 过夜单独处理
    if "过夜" in text or "overnight" in lower:
        return 8 * 3600

    # 先尝试范围模式：数字 + 分隔符 + 数字 + 单位
    range_pattern = (
        r"(\d+(?:\.\d+)?)\s*" + _RANGE_SEPARATORS +
        r"\s*(\d+(?:\.\d+)?)\s*(秒|sec|s|分钟|min|m|小时|hour|h|hr|天|day)"
    )
    m = re.search(range_pattern, lower)
    if m:
        v1 = float(m.group(1))
        v2 = float(m.group(2))
        unit = m.group(3)
        avg = (v1 + v2) / 2
        return int(avg * _UNIT_SECONDS.get(unit, 1))

    # 单值模式：数字 + 单位
    pattern = r"(\d+(?:\.\d+)?)\s*(秒|sec|s|分钟|min|m|小时|hour|h|hr|天|day)"
    m = re.search(pattern, lower)
    if m:
        value = float(m.group(1))
        unit = m.group(2)
        return int(value * _UNIT_SECONDS.get(unit, 1))

    return None


def parse_duration_from_instruction(text: str) -> int | None:
    """从步骤正文里提取时间（当 protocol_values.duration 为空时）。"""
    if not text:
        return None
    # 匹配 "10 min", "5分钟", "1小时", "过夜" 等出现在正文里的时间
    pattern = r"(\d+(?:\.\d+)?)\s*(秒|sec|s|分钟|min|m|小时|hour|h|hr)"
    matches = []
    for m in re.finditer(pattern, text):
        value = float(m.group(1))
        unit = m.group(2)
        seconds = int(value * _UNIT_SECONDS.get(unit, 1))
        matches.append(seconds)
    if matches:
        return max(matches)  # 取最大的，通常是主要操作时间
    if "过夜" in text:
        return 8 * 3600
    return None


# ── 步骤分类 ──

# passive = 机器运行/等待，用户只需等
_PASSIVE_KEYWORDS = [
    "离心", "孵育", "电泳", "转膜", "煮沸", "加热", "封闭",
    "染色", "脱色", "固定", "水解", "反应", "静置", "过夜",
    "烘", "烤", "冷却", "沉淀", "平衡", "消化", "摇床",
    "振荡孵育", "洗膜", "漂洗", "透析",
]

# active = 手在动
_ACTIVE_KEYWORDS = [
    "移液", "加", "混匀", "吸", "倒", "弃", "收集", "剪",
    "装配", "安装", "上样", "涂", "压", "称", "刮",
]


def classify_step(step: dict, duration_seconds: int | None) -> str:
    """根据步骤文本和时长推断类型。"""
    instruction = str(step.get("instruction", "") or "")
    title = str(step.get("title", "") or "")
    text = (instruction + " " + title).lower()

    # 有时长 + 含 passive 关键词 → passive
    if duration_seconds and duration_seconds >= 60:
        for kw in _PASSIVE_KEYWORDS:
            if kw in text:
                return "passive"
        # 有长时间但没有 active 关键词，也算 passive（纯等待）
        has_active = any(kw in text for kw in _ACTIVE_KEYWORDS)
        if not has_active:
            return "passive"

    return "active"


# ── LLM 提取步骤时间画像 ──

def _build_step_text(detail: dict) -> str:
    lines = []
    for step in detail.get("steps", []):
        vals = step.get("protocol_values") or {}
        duration_raw = vals.get("duration", "") or ""
        temp = vals.get("temperature", "") or ""
        parts = [
            f"第{step.get('number', '?')}步：{step.get('title', '')}",
            f"  操作：{step.get('instruction', '')}",
        ]
        if duration_raw:
            parts.append(f"  预计时长：{duration_raw}")
        if temp:
            parts.append(f"  温度：{temp}")
        terms = step.get("terms") or []
        if terms:
            parts.append(f"  术语：{', '.join(terms)}")
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


def _llm_extract_time_profiles(detail: dict) -> list[dict] | None:
    """用 LLM 提取每步的时间画像。失败返回 None。"""
    step_text = _build_step_text(detail)
    if not step_text.strip():
        return None

    try:
        from llm_bridge import WebSettingsLLMClient
    except Exception:
        return None

    system_prompt = (
        "你是实验室时间规划助手。用户给你一份实验方案的所有步骤，"
        "请为每一步提取时间画像，只输出 JSON 数组，不要 Markdown，不要解释。\n\n"
        "每步包含：\n"
        '- step_number：步骤编号（整数）\n'
        '- wait_type：步骤类型，三选一：\n'
        '    "passive"——机器在跑、你只需等（如离心、孵育、电泳、煮沸、染色）\n'
        '    "active"——你必须亲手操作（如移液、混匀、上样、装配）\n'
        '    "flexible"——不依赖前一步、随时能做的准备（如标记管子、预热设备）\n'
        '- duration_seconds：预计耗时（秒）。范围取中间值，过夜按 8 小时，无时长则 0。\n'
        '- interruptibility：能不能中途停下、人离开，三选一：\n'
        '    "hands_on"——必须人在旁边盯着操作，不能走开（如移液、装配、上样）\n'
        '    "monitored"——机器在跑，但需要人到点回来查看/停止（如电泳要看溴酚蓝、离心要到点取）\n'
        '    "leave_ok"——可以丢着不管走人，过夜也没事（如过夜培养、4度孵育、封闭）\n'
        '- can_overnight：此步是否适合过夜无人值守（true/false）。只有 leave_ok 且 duration > 2小时的才为 true。\n'
        '- parallel_suggestions：如果是 passive 步骤，列出等待期间可以做的准备工作（字符串数组）。'
        '只列有意义的建议，最多 3 条。active 步骤留空数组。\n\n'
        '判断要点：\n'
        '- 正文写「离心」「孵育」「电泳」等且有时长 → passive\n'
        '- 正文写「移液」「加入」「混匀」「剪取」等需要动手 → active\n'
        '- 过夜培养、4℃冰箱孵育 → leave_ok + can_overnight=true\n'
        '- 电泳需要到点停 → monitored\n'
        '- 离心需要到点取 → monitored\n'
        '- 封闭/洗涤在摇床过夜 → leave_ok\n'
        '- 只需判断和填写步骤，不要遗漏任何一步\n\n'
        '输出示例：\n'
        '[{"step_number":1,"wait_type":"active","duration_seconds":0,'
        '"interruptibility":"hands_on","can_overnight":false,'
        '"parallel_suggestions":[]},'
        '{"step_number":6,"wait_type":"passive","duration_seconds":300,'
        '"interruptibility":"monitored","can_overnight":false,'
        '"parallel_suggestions":["标记EP管","预热水浴锅"]},'
        '{"step_number":17,"wait_type":"passive","duration_seconds":28800,'
        '"interruptibility":"leave_ok","can_overnight":true,'
        '"parallel_suggestions":[]}]'
    )

    try:
        client = WebSettingsLLMClient(max_attempts=1, timeout_seconds=30.0)
        result = client.generate_json(
            system_prompt=system_prompt,
            user_prompt=f"方案：{detail['protocol']['title']}\n\n{step_text}",
        )
        data = json.loads(result.content)
        if isinstance(data, dict):
            data = data.get("steps") or data.get("profiles") or []
        profiles = []
        for item in data:
            num = int(item.get("step_number", 0))
            profiles.append({
                "step_number": num,
                "wait_type": item.get("wait_type", "active"),
                "duration_seconds": int(item.get("duration_seconds", 0)),
                "interruptibility": item.get("interruptibility", "hands_on"),
                "can_overnight": bool(item.get("can_overnight", False)),
                "parallel_suggestions": item.get("parallel_suggestions", []),
            })
        if not profiles:
            return None
        return profiles
    except Exception:
        return None


_LEAVE_OK_KEYWORDS = ["过夜", "4℃", "4 度", "4度", "冰箱", "冷藏", "摇床", "封闭", "透析"]
_MONITORED_KEYWORDS = ["离心", "电泳", "煮沸", "加热", "染色", "脱色"]


def _infer_interruptibility(wait_type: str, instruction: str, duration_seconds: int) -> tuple[str, bool]:
    """推断步骤的可中断性和能否过夜。返回 (interruptibility, can_overnight)。"""
    text = instruction or ""
    if "过夜" in text:
        return "leave_ok", True
    if any(kw in text for kw in _LEAVE_OK_KEYWORDS):
        return "leave_ok", duration_seconds >= 7200
    if wait_type == "passive":
        if any(kw in text for kw in _MONITORED_KEYWORDS):
            return "monitored", False
        return "leave_ok", duration_seconds >= 7200
    return "hands_on", False


def _keyword_fallback_profiles(detail: dict) -> list[dict]:
    """降级路径：用关键词推断步骤类型。"""
    profiles = []
    for step in detail.get("steps", []):
        vals = step.get("protocol_values") or {}
        dur_raw = vals.get("duration", "") or ""
        dur_sec = parse_duration(dur_raw)
        if dur_sec is None:
            dur_sec = parse_duration_from_instruction(step.get("instruction", ""))
        dur_sec = dur_sec or 0
        wait_type = classify_step(step, dur_sec)
        instruction = str(step.get("instruction", "") or "")
        interruptibility, can_overnight = _infer_interruptibility(wait_type, instruction, dur_sec)
        profiles.append({
            "step_number": step.get("number"),
            "wait_type": wait_type,
            "duration_seconds": dur_sec,
            "interruptibility": interruptibility,
            "can_overnight": can_overnight,
            "parallel_suggestions": [],
        })
    return profiles


# ── 持久化缓存 ──

def _load_cached_profiles(protocol_id: str, step_signature: str) -> list[dict] | None:
    try:
        from database.db import get_connection
        with get_connection() as conn:
            row = conn.execute(
                "SELECT profiles_json FROM step_time_profiles WHERE protocol_id=? AND step_signature=?",
                (protocol_id, step_signature),
            ).fetchone()
        if row:
            return json.loads(row["profiles_json"])
    except Exception:
        pass
    return None


def _save_cached_profiles(protocol_id: str, step_signature: str, data: list[dict]) -> None:
    try:
        from database.db import get_connection
        with get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO step_time_profiles (protocol_id, step_signature, profiles_json) "
                "VALUES (?, ?, ?)",
                (protocol_id, step_signature, json.dumps(data, ensure_ascii=False)),
            )
    except Exception:
        pass


def get_time_profiles(protocol_id: str) -> list[dict]:
    """获取方案的时间画像（LLM 提取，持久化缓存）。"""
    detail = domain.protocol_detail(protocol_id)
    steps = detail.get("steps", [])
    step_signature = f"{detail['protocol']['total_steps']}:{len(steps)}"

    profiles = _load_cached_profiles(protocol_id, step_signature)
    if profiles is None:
        profiles = _llm_extract_time_profiles(detail)
        if profiles is None:
            profiles = _keyword_fallback_profiles(detail)
        _save_cached_profiles(protocol_id, step_signature, profiles)
    return profiles


# ── 调度引擎 ──

def generate_schedule(protocol_id: str) -> dict:
    """从方案步骤生成时间规划。"""
    detail = domain.protocol_detail(protocol_id)
    profiles = get_time_profiles(protocol_id)
    profile_map = {p["step_number"]: p for p in profiles}

    steps = detail.get("steps", [])
    timeline: list[dict] = []
    current_seconds = 0
    total_active = 0
    total_passive = 0
    passive_windows: list[dict] = []

    for step in steps:
        num = step.get("number")
        prof = profile_map.get(num, {})
        wait_type = prof.get("wait_type", "active")
        dur = prof.get("duration_seconds", 0) or 0
        suggestions = prof.get("parallel_suggestions", [])
        interruptibility = prof.get("interruptibility", "hands_on")
        can_overnight = prof.get("can_overnight", False)

        start = current_seconds
        current_seconds += dur
        end = current_seconds

        entry = {
            "step_number": num,
            "title": step.get("title", ""),
            "wait_type": wait_type,
            "interruptibility": interruptibility,
            "can_overnight": can_overnight,
            "duration_seconds": dur,
            "start_seconds": start,
            "end_seconds": end,
            "start_label": _fmt_duration(start),
            "end_label": _fmt_duration(end),
        }

        if wait_type == "passive" and dur >= 60:
            total_passive += dur
            entry["parallel_suggestions"] = suggestions
            passive_windows.append({
                "step_number": num,
                "title": step.get("title", ""),
                "duration_seconds": dur,
                "duration_label": _fmt_duration(dur),
                "interruptibility": interruptibility,
                "can_overnight": can_overnight,
                "suggestions": suggestions,
            })
        else:
            total_active += dur

        timeline.append(entry)

    total_seconds = current_seconds
    return {
        "protocol_id": protocol_id,
        "protocol_title": detail["protocol"]["title"],
        "total_steps": len(steps),
        "total_seconds": total_seconds,
        "total_label": _fmt_duration(total_seconds),
        "active_seconds": total_active,
        "passive_seconds": total_passive,
        "active_label": _fmt_duration(total_active),
        "passive_label": _fmt_duration(total_passive),
        "passive_ratio": round(total_passive / total_seconds, 2) if total_seconds else 0,
        "passive_windows": passive_windows,
        "timeline": timeline,
    }


# ── 第三期：按用户作息时间的时钟规划 ──

def _parse_clock(time_str: str) -> int:
    """"09:30" → 570（分钟）。"""
    parts = str(time_str).strip().split(":")
    return int(parts[0]) * 60 + int(parts[1])


def _fmt_clock(minutes: int) -> str:
    """570 → "09:30"。"""
    minutes = minutes % (24 * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def plan_clock_schedule(
    protocol_id: str,
    work_start: str = "09:00",
    lunch_start: str = "12:00",
    lunch_end: str = "13:00",
    work_end: str = "18:00",
) -> dict:
    """把方案步骤投射到用户的真实作息时间上。

    核心：不替用户做决定，而是把"如果9点开始，什么时候到哪一步"摊开给他看。
    标出哪些步正好卡在午饭/下班，哪些步可以丢着过夜。
    用户自己判断怎么安排。
    """
    detail = domain.protocol_detail(protocol_id)
    profiles = get_time_profiles(protocol_id)
    profile_map = {p["step_number"]: p for p in profiles}
    steps = detail.get("steps", [])

    ws = _parse_clock(work_start)
    ls = _parse_clock(lunch_start)
    le = _parse_clock(lunch_end)
    we = _parse_clock(work_end)

    # 按天组织，clock = 当前时间（分钟），day = 第几天
    clock = ws
    day = 1
    daily_steps: list[dict] = []
    alerts: list[dict] = []
    past_end_reported = False  # 超过下班时间只报一次

    for step in steps:
        num = step.get("number")
        prof = profile_map.get(num, {})
        dur_min = (prof.get("duration_seconds", 0) or 0) // 60
        wait_type = prof.get("wait_type", "active")
        interruptibility = prof.get("interruptibility", "hands_on")
        can_overnight = prof.get("can_overnight", False)
        suggestions = prof.get("parallel_suggestions", [])

        if dur_min <= 0:
            # 无时长的操作步骤，不推进时钟
            daily_steps.append({
                "day": day,
                "step_number": num,
                "title": step.get("title", ""),
                "wait_type": wait_type,
                "interruptibility": interruptibility,
                "duration_minutes": 0,
                "start_clock": _fmt_clock(clock),
                "end_clock": _fmt_clock(clock),
                "note": "",
            })
            continue

        step_end = clock + dur_min
        note = ""

        # 检查是否跨午饭
        if clock < ls < step_end:
            if interruptibility == "leave_ok":
                note = "跨午休（可不管）"
            elif interruptibility == "monitored":
                note = "跨午休，饭后回来取"
                alerts.append({
                    "type": "lunch_cross",
                    "step_number": num,
                    "message": f"第{num}步「{step.get('title','')}」跨午饭，需要到点回来处理。",
                })
            else:
                note = "建议午饭后做"
                alerts.append({
                    "type": "lunch_cross",
                    "step_number": num,
                    "message": f"第{num}步「{step.get('title','')}」要动手，正好卡午饭时间。",
                })

        # 检查是否超过下班时间
        if step_end > we and not past_end_reported:
            if can_overnight:
                note = "可过夜，下班前启动就行"
                alerts.append({
                    "type": "overnight_setup",
                    "step_number": num,
                    "message": f"从第{num}步「{step.get('title','')}」开始可以过夜，下班前启动即可。",
                })
                past_end_reported = True
            elif interruptibility == "leave_ok":
                note = f"超过下班，但可以丢着走"
                # 找后面连续的 leave_ok 步骤
                alerts.append({
                    "type": "leave_after_work",
                    "step_number": num,
                    "message": f"第{num}步以后都不需要人盯，下班可以走。",
                })
                past_end_reported = True
            else:
                # 必须明天做
                note = "今天做不完，留到明天"
                alerts.append({
                    "type": "next_day",
                    "step_number": num,
                    "message": f"第{num}步「{step.get('title','')}」需要人在，今天来不及了。",
                })
                daily_steps.append({
                    "day": day,
                    "step_number": num,
                    "title": step.get("title", ""),
                    "wait_type": wait_type,
                    "interruptibility": interruptibility,
                    "duration_minutes": dur_min,
                    "start_clock": _fmt_clock(clock),
                    "end_clock": "明天",
                    "note": note,
                })
                day += 1
                clock = ws  # 第二天从上班时间重新开始
                past_end_reported = False
                continue

        entry = {
            "day": day,
            "step_number": num,
            "title": step.get("title", ""),
            "wait_type": wait_type,
            "interruptibility": interruptibility,
            "duration_minutes": dur_min,
            "start_clock": _fmt_clock(clock),
            "end_clock": _fmt_clock(step_end),
            "note": note,
        }
        if suggestions and wait_type == "passive" and dur_min >= 1:
            entry["parallel_suggestions"] = suggestions
        daily_steps.append(entry)
        clock = step_end

    # 汇总
    total_days = day
    finish_clock = _fmt_clock(clock)
    summary_lines = _build_clock_summary(
        detail["protocol"]["title"], daily_steps, alerts,
        ws, ls, le, we, total_days, finish_clock,
    )

    return {
        "protocol_id": protocol_id,
        "protocol_title": detail["protocol"]["title"],
        "work_start": work_start,
        "lunch_start": lunch_start,
        "lunch_end": lunch_end,
        "work_end": work_end,
        "total_days": total_days,
        "finish_clock": finish_clock,
        "steps": daily_steps,
        "alerts": alerts,
        "summary_lines": summary_lines,
    }


def _build_clock_summary(
    title: str, steps: list[dict], alerts: list[dict],
    ws: int, ls: int, le: int, we: int,
    total_days: int, finish_clock: str,
) -> list[str]:
    """生成卡片展示用的文字行。"""
    lines = [f"方案：{title}"]
    if total_days > 1:
        lines.append(f"预计跨 {total_days} 天，第 {total_days} 天 {_fmt_clock(ws)} 开始，约 {finish_clock} 完成。")
    else:
        lines.append(f"从 {_fmt_clock(ws)} 开始，约 {finish_clock} 完成。")

    # 按天分组的关键节点
    for day in range(1, total_days + 1):
        day_steps = [s for s in steps if s["day"] == day]
        if not day_steps:
            continue
        if total_days > 1:
            lines.append(f"第{day}天：")
        for s in day_steps:
            dur = s.get("duration_minutes", 0)
            if dur <= 0 and s["wait_type"] != "passive":
                continue  # 跳过无时长的操作步
            marker = ""
            wt = s.get("wait_type")
            if wt == "passive":
                inter = s.get("interruptibility", "")
                if inter == "leave_ok":
                    marker = "🟢"
                elif inter == "monitored":
                    marker = "🟡"
                else:
                    marker = "🔴"
            else:
                marker = "🔧"

            time_part = f"{s['start_clock']}-{s['end_clock']}" if s["end_clock"] != "明天" else f"{s['start_clock']}→明天"
            note = f"（{s['note']}）" if s.get("note") else ""
            lines.append(f"  {marker} {time_part} 第{s['step_number']}步 {s['title']}{note}")

    # 提醒
    if alerts:
        lines.append("提醒：")
        for a in alerts:
            lines.append(f"  ⚠️ {a['message']}")

    return lines


def _fmt_duration(seconds: int) -> str:
    """秒 → 可读时长。"300" → "5分钟", "3600" → "1小时"."""
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
    if secs and not hours:  # 秒只在不足 1 分钟时显示
        parts.append(f"{secs}秒")
    return "".join(parts) if parts else "0分钟"


def format_schedule_brief(schedule: dict) -> list[str]:
    """把调度结果格式化成聊天可读的行（工具卡片用）。"""
    lines = [
        f"方案：{schedule['protocol_title']}",
        f"总计 {schedule['total_label']}（操作 {schedule['active_label']} + 等待 {schedule['passive_label']}）",
    ]
    windows = schedule.get("passive_windows") or []
    if windows:
        lines.append("等待窗口：")
        for w in windows:
            sugg = w.get("suggestions") or []
            if sugg:
                lines.append(f"  第{w['step_number']}步 {w['title']}（{w['duration_label']}）→ 可做：{'、'.join(sugg)}")
            else:
                lines.append(f"  第{w['step_number']}步 {w['title']}（{w['duration_label']}）→ 自由时间")
    return lines


# ── 第二期：从当前步开始的剩余规划 ──

def get_step_profile(protocol_id: str, step_number: int) -> dict | None:
    """查询单步的时间画像。"""
    profiles = get_time_profiles(protocol_id)
    for p in profiles:
        if p.get("step_number") == step_number:
            return p
    return None


def get_next_passive_window(protocol_id: str, from_step: int) -> dict | None:
    """从指定步开始往后找下一个 passive 窗口。"""
    profiles = get_time_profiles(protocol_id)
    detail = domain.protocol_detail(protocol_id)
    steps = {s["number"]: s for s in detail.get("steps", [])}
    for p in profiles:
        num = p.get("step_number", 0)
        if num >= from_step and p.get("wait_type") == "passive" and p.get("duration_seconds", 0) >= 60:
            step = steps.get(num, {})
            return {
                "step_number": num,
                "title": step.get("title", ""),
                "wait_type": "passive",
                "duration_seconds": p["duration_seconds"],
                "duration_label": _fmt_duration(p["duration_seconds"]),
                "interruptibility": p.get("interruptibility", "monitored"),
                "can_overnight": p.get("can_overnight", False),
                "parallel_suggestions": p.get("parallel_suggestions", []),
            }
    return None


def get_remaining_schedule(protocol_id: str, from_step: int) -> dict:
    """从指定步开始计算剩余时间规划。"""
    full = generate_schedule(protocol_id)
    timeline = full.get("timeline", [])

    remaining = [t for t in timeline if t["step_number"] >= from_step]
    if not remaining:
        return {
            "protocol_id": protocol_id,
            "protocol_title": full["protocol_title"],
            "from_step": from_step,
            "remaining_seconds": 0,
            "remaining_label": "已完成",
            "remaining_active_seconds": 0,
            "remaining_passive_seconds": 0,
            "next_passive_window": None,
            "timeline": [],
        }

    rem_active = sum(t["duration_seconds"] for t in remaining if t["wait_type"] != "passive")
    rem_passive = sum(t["duration_seconds"] for t in remaining if t["wait_type"] == "passive" and t["duration_seconds"] >= 60)
    rem_total = sum(t["duration_seconds"] for t in remaining)

    # 重新计算从 0 开始的相对时间
    rel_timeline = []
    offset = 0
    for t in remaining:
        dur = t["duration_seconds"]
        rel = dict(t)
        rel["start_seconds"] = offset
        rel["end_seconds"] = offset + dur
        rel["start_label"] = _fmt_duration(offset)
        rel["end_label"] = _fmt_duration(offset + dur)
        rel_timeline.append(rel)
        offset += dur

    # 下一个 passive 窗口
    next_window = get_next_passive_window(protocol_id, from_step)

    # 当前步信息
    current_step = timeline[0] if timeline else None
    for t in timeline:
        if t["step_number"] == from_step:
            current_step = t
            break

    return {
        "protocol_id": protocol_id,
        "protocol_title": full["protocol_title"],
        "from_step": from_step,
        "current_step": current_step,
        "remaining_seconds": rem_total,
        "remaining_label": _fmt_duration(rem_total),
        "remaining_active_seconds": rem_active,
        "remaining_passive_seconds": rem_passive,
        "remaining_active_label": _fmt_duration(rem_active),
        "remaining_passive_label": _fmt_duration(rem_passive),
        "next_passive_window": next_window,
        "timeline": rel_timeline,
    }


def format_remaining_brief(remaining: dict) -> list[str]:
    """剩余规划的卡片展示。"""
    lines = []
    rem = remaining.get("remaining_label", "")
    if rem == "已完成" or remaining.get("remaining_seconds", 0) == 0:
        lines.append(f"方案：{remaining['protocol_title']}")
        lines.append("剩余：全部步骤已完成。")
        return lines

    lines.append(f"方案：{remaining['protocol_title']}")
    lines.append(
        f"从第{remaining['from_step']}步起剩余 {rem}"
        f"（操作 {remaining.get('remaining_active_label', '')} + "
        f"等待 {remaining.get('remaining_passive_label', '')}）"
    )

    nw = remaining.get("next_passive_window")
    if nw:
        sugg = nw.get("parallel_suggestions") or []
        eq = nw.get("occupied_equipment") or []
        parts = [f"下一个等待：第{nw['step_number']}步 {nw['title']}（{nw['duration_label']}）"]
        if eq:
            parts.append(f"占用：{'、'.join(eq)}")
        lines.append(" ".join(parts))
        if sugg:
            lines.append(f"  等待期间可做：{'、'.join(sugg)}")

    # 接下来的 3 步
    upcoming = remaining.get("timeline", [])[:3]
    if upcoming:
        lines.append("接下来的步骤：")
        for t in upcoming:
            marker = "⏳等待" if t["wait_type"] == "passive" and t["duration_seconds"] >= 60 else "🔧操作"
            lines.append(f"  第{t['step_number']}步 {t['title']}（{t['end_label']}）{marker}")
    return lines


# ── 第三期：跨实验规划 ──

def plan_multi_protocols(protocol_ids: list[str]) -> dict:
    """分析多个方案，找出设备冲突和交错优化建议。

    核心：两个方案如果都占用同一设备（如离心机、摇床），不能同时跑那一步。
    但方案 A 的被动等待期间可以做方案 B 的主动操作。
    """
    if not protocol_ids:
        return {"protocols": [], "total_seconds": 0, "total_label": "0分钟",
                "conflicts": [], "schedule_plan": []}

    # 收集每个方案的信息
    proto_infos = []
    for pid in protocol_ids:
        try:
            sched = generate_schedule(pid)
            # 找最大被动窗口
            passive_windows = sched.get("passive_windows") or []
            max_window = max(passive_windows, key=lambda w: w["duration_seconds"]) if passive_windows else None
            proto_infos.append({
                "protocol_id": pid,
                "title": sched["protocol_title"],
                "total_seconds": sched["total_seconds"],
                "total_label": sched["total_label"],
                "active_seconds": sched["active_seconds"],
                "passive_seconds": sched["passive_seconds"],
                "active_label": sched["active_label"],
                "passive_label": sched["passive_label"],
                "passive_ratio": sched["passive_ratio"],
                "max_passive_window": max_window,
                "passive_windows": passive_windows,
            })
        except Exception:
            continue

    if not proto_infos:
        return {"protocols": [], "total_seconds": 0, "total_label": "0分钟",
                "schedule_plan": []}

    # 交错建议：先做被动占比高的（长等待可以先挂着，期间做别的）
    sorted_protos = sorted(proto_infos, key=lambda p: p["passive_ratio"], reverse=True)

    plan = []
    cumulative = 0
    for idx, p in enumerate(sorted_protos):
        entry = {
            "order": idx + 1,
            "protocol_id": p["protocol_id"],
            "title": p["title"],
            "total_label": p["total_label"],
            "active_label": p["active_label"],
            "start_offset": cumulative,
            "start_label": _fmt_duration(cumulative),
        }
        if idx == 0 and len(sorted_protos) > 1:
            mw = p["max_passive_window"]
            if mw and mw["duration_seconds"] >= 600:
                entry["parallel_opportunity"] = (
                    f"启动后第{mw['step_number']}步{mw['title']}（{mw['duration_label']}）期间，"
                    f"可以开始做后面的方案"
                )
        plan.append(entry)
        cumulative += p["active_seconds"]

    total_estimate = cumulative if len(proto_infos) > 1 else proto_infos[0]["total_seconds"]

    return {
        "protocols": proto_infos,
        "protocol_count": len(proto_infos),
        "total_seconds": total_estimate,
        "total_label": _fmt_duration(total_estimate),
        "sequential_total": sum(p["total_seconds"] for p in proto_infos),
        "sequential_label": _fmt_duration(sum(p["total_seconds"] for p in proto_infos)),
        "schedule_plan": plan,
    }


def format_multi_protocol_brief(result: dict) -> list[str]:
    """跨实验规划的卡片展示。"""
    lines = []
    protos = result.get("protocols") or []
    if not protos:
        return ["没有可分析的方案。"]

    names = " + ".join(p["title"] for p in protos)
    lines.append(f"方案组合：{names}（{len(protos)} 个）")

    sequential = result.get("sequential_label", "")
    optimized = result.get("total_label", "")
    if result.get("protocol_count", 0) > 1:
        lines.append(f"顺序做：{sequential} | 交错后只需亲手操作：{optimized}")

    plan = result.get("schedule_plan") or []
    if plan:
        lines.append("建议顺序：")
        for entry in plan:
            line = f"  {entry['order']}. {entry['title']}（总{entry.get('total_label','')}，动手{entry.get('active_label','')}）"
            if entry.get("parallel_opportunity"):
                line += f"\n     ← {entry['parallel_opportunity']}"
            lines.append(line)
    return lines
