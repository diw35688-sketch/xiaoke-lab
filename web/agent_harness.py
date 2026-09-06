# -*- coding: utf-8 -*-
"""Agent Harness：基于 agent_loop 的多工具心跳/反思循环。

参考 OpenClaw：
- context engine 组装记忆/任务/工具上下文
- embedded agent runner 多轮工具循环
- multi-agent router 选择心跳/反思子智能体
- heartbeat_respond / reflection_respond 作为终端工具，notify=false 静默
"""

from __future__ import annotations

from datetime import datetime

from agent_loop import EmbeddedAgentRunner, MultiAgentRouter
from database import crud


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _context_lines() -> str:
    lines = []
    try:
        experiments = crud.list_experiments(include_completed=False)
        today = _today()
        today_experiments = [
            e for e in experiments if not (e.get("start_at") or "") or str(e.get("start_at") or "")[:10] == today
        ]
        if today_experiments:
            lines.append("【今日实验计划】")
            lines.extend(f"- {e.get('name')}" + (f"（{e.get('equipment')}）" if e.get("equipment") else "") for e in today_experiments)
        else:
            lines.append("【今日实验计划】今天没有安排实验。")
    except Exception:
        pass
    try:
        today_summary = crud.work_summary(0)
        yesterday_summary = crud.work_summary(1)
        lines.append("【今日工作】")
        lines.append(f"- 实验记录 {today_summary['records']} 条，新增储存 {today_summary['storage_added']} 项，用户消息 {today_summary['user_messages']} 条")
        lines.append("【昨日工作】")
        lines.append(f"- 实验记录 {yesterday_summary['records']} 条，新增储存 {yesterday_summary['storage_added']} 项")
    except Exception:
        pass
    try:
        storage = crud.storage_stats()
        lines.append("【库存】")
        lines.append(f"- 即将过期 {storage.get('expiring', 0)} 项，已过期 {storage.get('expired', 0)} 项")
    except Exception:
        pass
    from settings_store import current as current_settings
    profile = current_settings().owner_profile or {}
    if profile.get("field"):
        lines.append(f"【主人画像】领域：{profile.get('field')}")
    return "\n".join(lines)


def _build_tools(task_kind: str) -> dict[str, dict]:
    context = _context_lines()
    if task_kind == "heartbeat":
        terminal_name = "heartbeat_respond"
        terminal_schema = {
            "name": "heartbeat_respond",
            "description": "接受心跳结果。notify=false 时不打扰用户；notify=true 时必须提供 notificationText。",
            "parameters": {
                "type": "object",
                "properties": {
                    "notify": {"type": "boolean"},
                    "notificationText": {"type": "string", "description": "需要打扰用户时的简短提醒"},
                },
                "required": ["notify"],
                "additionalProperties": False,
            },
        }
    else:
        terminal_name = "reflection_respond"
        terminal_schema = {
            "name": "reflection_respond",
            "description": "接受反思结果。notify=false 时静默跳过；notify=true 时必须提供 reflectionText。",
            "parameters": {
                "type": "object",
                "properties": {
                    "notify": {"type": "boolean"},
                    "reflectionText": {"type": "string", "description": "今天的简短反思和明日建议"},
                },
                "required": ["notify"],
                "additionalProperties": False,
            },
        }

    def terminal_execute(args):
        key = "notificationText" if task_kind == "heartbeat" else "reflectionText"
        return {
            "notify": bool(args.get("notify", False)),
            "text": str(args.get(key) or "").strip(),
        }

    tools = {
        "lookup_today_context": {
            "schema": {
                "name": "lookup_today_context",
                "description": "查看今天的实验计划、工作摘要、库存和主人画像。",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            "execute": lambda _args: context,
        },
        "lookup_storage": {
            "schema": {
                "name": "lookup_storage",
                "description": "查看储存库过期/即将过期情况。",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            "execute": lambda _args: crud.storage_stats(),
        },
        terminal_name: {
            "schema": terminal_schema,
            "execute": terminal_execute,
        },
    }
    return tools


def _run_loop(task_kind: str) -> dict:
    router = MultiAgentRouter.route(task_kind)
    tools = _build_tools(task_kind)
    runner = EmbeddedAgentRunner(max_steps=6)
    result = runner.run(
        system_prompt=router["system_prompt"],
        user_text=f"请检查当前实验工作状态，并按规则决定是否通知。今天是 {_today()}。",
        tools=tools,
        task_kind=task_kind,
        terminal_tools={ "heartbeat_respond" if task_kind == "heartbeat" else "reflection_respond" },
    )
    terminal = result.get("result")
    if not isinstance(terminal, dict) or not terminal.get("notify") or not terminal.get("text"):
        return {"notified": False, "notification": None}
    text = terminal["text"]
    period = "morning" if task_kind == "heartbeat" else "evening"
    title = f"每日心跳 · {_today()}" if task_kind == "heartbeat" else f"今晚反思 · {_today()}"
    notification = crud.create_daily_notification(period, _today(), title, text)
    return {"notified": True, "notification": notification, "text": text}


def run_heartbeat_loop() -> dict:
    try:
        return _run_loop("heartbeat")
    except Exception:
        # 模型不可用/超时不能拖垮心跳：静默跳过。
        return {"notified": False, "notification": None, "error": "model_unavailable"}


def run_reflection_loop() -> dict:
    try:
        return _run_loop("reflection")
    except Exception:
        return {"notified": False, "notification": None, "error": "model_unavailable"}
