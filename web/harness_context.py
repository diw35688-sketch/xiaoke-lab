# -*- coding: utf-8 -*-
"""统一 Harness 上下文：让 Agent 每次调用都能感知当前实验状态。

这个模块只做“采集和格式化”，不调用大模型。采集内容包括：
- 当前交互模式 / 实验上下文
- 当前选中的实验方案与当前步骤
- 当前试剂配置流程
- 最近几条会话消息
- 当前会话的基础信息
"""
from __future__ import annotations

from typing import Optional

import domain
from database.crud import get_recent_messages
from database.db import get_connection


def _format_protocol_state() -> str:
    try:
        state = domain.session()
        if not state.selection.has_protocol:
            return "当前没有选择实验方案（自由记录模式）。"
        protocol = state.selection.protocol
        step = state.current_step()
        lines = [
            f"当前方案：{protocol.title}",
            f"当前第 {step.step_number} 步：{step.title}",
        ]
        if getattr(step, "instruction", None):
            lines.append(f"步骤说明：{str(step.instruction)[:200]}")
        if getattr(step, "protocol_values", None):
            values = "、".join(
                f"{key}={value}" for key, value in step.protocol_values.items()
            )
            lines.append(f"方案已定：{values}")
        if getattr(step, "must_record", None):
            lines.append("现场必测：" + "、".join(step.must_record))
        return "\n".join(lines)
    except Exception:  # noqa: BLE001 - 采集上下文不应让会话失败
        return "当前方案状态读取失败（不影响继续对话）。"


def _format_reagent_flow(conversation_id: Optional[str]) -> str:
    if not conversation_id:
        return "没有进行中的试剂配置流程。"
    try:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM reagent_prep_flows WHERE conversation_id=?",
                (conversation_id,),
            ).fetchone()
        if row is None:
            return "没有进行中的试剂配置流程。"
        return (
            f"当前试剂配置流程：reagent_prep_id={row['prep_id']}，"
            f"第 {row['current_index'] + 1} 步，状态：{row['status']}"
        )
    except Exception:  # noqa: BLE001
        return "当前试剂配置流程读取失败。"


def build_harness_context(
    conversation_id: Optional[str] = None,
    lab_session_id: Optional[str] = None,
    interaction_mode: Optional[str] = None,
) -> str:
    """构建一段适合放入 system prompt 的上下文。"""
    parts: list[str] = []
    parts.append("【当前系统 Harness 状态】")
    parts.append(f"交互模式：{interaction_mode or '未指定'}")
    if lab_session_id:
        parts.append(f"实验会话 ID：{lab_session_id}")
    if conversation_id:
        parts.append(f"会话 ID：{conversation_id}")

    parts.append(_format_protocol_state())
    parts.append(_format_reagent_flow(conversation_id))

    if conversation_id:
        try:
            recent = get_recent_messages(conversation_id, limit=6)
            if recent:
                parts.append("【最近会话消息】")
                for item in recent[-4:]:
                    role = "用户" if item["role"] == "user" else "助手"
                    text = str(item["content"] or "").replace("\n", " ")[:120]
                    parts.append(f"{role}：{text}")
        except Exception:  # noqa: BLE001
            parts.append("最近会话消息读取失败。")

    return "\n".join(parts)
