# -*- coding: utf-8 -*-
"""主动智能体的每日心跳与反思。

心跳：早上按用户设置的时间生成“今日计划 + 昨日工作”通知。
反思：晚上生成当天实验记录总结与明日建议。
"""

from __future__ import annotations

from datetime import datetime

from database import crud
from settings_store import current as current_settings


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _experiment_lines() -> list[str]:
    try:
        items = crud.list_experiments(include_completed=False)
    except Exception:
        return []
    lines = []
    for item in items:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        start_at = str(item.get("start_at") or "")
        if start_at and start_at[:10] != _today():
            continue
        equipment = str(item.get("equipment") or "").strip()
        lines.append(f"- {name}" + (f"（{equipment}）" if equipment else ""))
    return lines


def _has_actionable_today(today_summary, yesterday_summary, experiments, storage) -> bool:
    """OpenClaw heartbeat 的 notify 决策：没有值得打扰用户的内容就不生成通知。"""
    if experiments:
        return True
    if today_summary.get("records") or today_summary.get("storage_added") or today_summary.get("user_messages"):
        return True
    if yesterday_summary.get("records") or yesterday_summary.get("storage_added"):
        return True
    if storage.get("expiring") or storage.get("expired"):
        return True
    return False


def run_daily_heartbeat() -> dict:
    today = _today()
    experiments = _experiment_lines()
    today_summary = crud.work_summary(0)
    yesterday_summary = crud.work_summary(1)
    try:
        storage = crud.storage_stats()
    except Exception:
        storage = {}
    if not _has_actionable_today(today_summary, yesterday_summary, experiments, storage):
        # 没有需要用户注意的事：按 OpenClaw 的约定静默跳过，不制造空通知。
        return {"notified": False, "notification": None}

    profile = current_settings().owner_profile or {}
    field = str(profile.get("field") or "").strip()
    greeting = "早上好" if field else "早上好"
    body_parts = [f"{greeting}，这是今天的实验计划。"]
    if field:
        body_parts.append(f"领域：{field}")
    if experiments:
        body_parts.append("")
        body_parts.append("【今日计划】")
        body_parts.extend(experiments)
    else:
        body_parts.append("")
        body_parts.append("【今日计划】今天还没有安排实验，可以点菜加入，或开始一个新方案。")
    body_parts += [
        "",
        "【今日工作】",
        f"实验记录：{today_summary['records']} 条",
        f"新增储存：{today_summary['storage_added']} 项",
        f"用户消息：{today_summary['user_messages']} 条",
        "",
        "【昨日工作】",
        f"实验记录：{yesterday_summary['records']} 条",
        f"新增储存：{yesterday_summary['storage_added']} 项",
        f"用户消息：{yesterday_summary['user_messages']} 条",
    ]
    if storage.get("expiring") or storage.get("expired"):
        body_parts.append("")
        body_parts.append(
            "【库存提醒】"
            f"即将过期 {storage.get('expiring', 0)} 项，已过期 {storage.get('expired', 0)} 项。"
        )
    notification = crud.create_daily_notification(
        "morning", today, f"每日心跳 · {today}", "\n".join(body_parts)
    )
    return {"notified": True, "notification": notification}


def run_daily_reflection() -> dict:
    today = _today()
    today_summary = crud.work_summary(0)
    experiments = _experiment_lines()
    if not today_summary.get("records") and not experiments:
        return {"notified": False, "notification": None}
    body = [
        "今晚实验反思已生成。",
        "",
        "【今天做了什么】",
        f"实验记录：{today_summary['records']} 条",
        f"新增储存：{today_summary['storage_added']} 项",
        f"用户消息：{today_summary['user_messages']} 条",
    ]
    if experiments:
        body += ["", "【今天未完成/待办】", *experiments]
    body += [
        "",
        "【明日建议】",
        "- 查看未完成实验，补齐试剂/耗材库存",
        "- 复盘今天的记录，看看有没有偏差或可优化步骤",
        "- 需要的话提前生成明天的准备清单",
    ]
    notification = crud.create_daily_notification(
        "evening", today, f"今晚反思 · {today}", "\n".join(body)
    )
    return {"notified": True, "notification": notification}
