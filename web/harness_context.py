# -*- coding: utf-8 -*-
"""统一 Harness 上下文：让 Agent 每次调用都能感知当前实验状态。

这个模块只做“采集和格式化”，不调用大模型。采集内容包括：
- 当前交互模式 / 实验上下文
- 当前实验会话的状态（方案、当前步、已记录值、步骤完成情况）
- 当前选中的实验方案与当前步骤
- 当前试剂配置流程
- 最近几条会话消息
- 当前会话的基础信息
"""
from __future__ import annotations

import json
from typing import Mapping, Optional

import domain
from database.crud import get_recent_messages
from database.db import get_connection
from database.turn_store import TurnStore
from src.core.protocol_completion_policy import ProtocolStepFactState
from src.core.protocol_execution_state import (
    ProtocolExecutionState,
    ProtocolStepProgressStatus,
)
from src.core.session_context import SessionContext

_turn_store = TurnStore()


def get_current_protocol_id() -> str | None:
    """获取当前选中方案的 ID（全局 domain session）。"""
    try:
        state = domain.session()
        if state.selection.has_protocol:
            return state.selection.protocol.protocol_id
    except Exception:
        pass
    return None


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
        # 不输出“现场必测”，全局没有必填字段。
        return "\n".join(lines)
    except Exception:  # noqa: BLE001 - 采集上下文不应让会话失败
        return "当前方案状态读取失败（不影响继续对话）。"


def _format_experiment_state(
    conversation_id: Optional[str], lab_session_id: Optional[str]
) -> str:
    if not conversation_id or not lab_session_id:
        return "当前没有实验会话上下文。"
    try:
        stored = _turn_store.load_experiment_state(
            conversation_id, lab_session_id
        )
        lines: list[str] = []

        # 1. 会话上下文（最近已分析的事件）
        session_context = SessionContext.from_snapshot(
            dict(stored["session_context"])
        )
        prompt_context = session_context.as_prompt_context()
        if prompt_context:
            lines.append("【本实验会话最近记录】")
            lines.extend(f"- {item}" for item in prompt_context[-6:])

        # 2. 方案执行状态：优先使用本实验会话的快照，而不是全局 domain 状态。
        facts = dict(stored.get("protocol_step_facts") or {})
        if not facts:
            # 兼容旧版 lab_session 错位：如果当前 lab_session 没有方案，
            # 找同一 conversation 下任意一份非空协议快照。
            try:
                with get_connection() as connection:
                    rows = connection.execute(
                        """SELECT protocol_step_facts_json
                           FROM experiment_session_state
                           WHERE conversation_id=? AND protocol_step_facts_json != '{}'
                           ORDER BY updated_at DESC""",
                        (conversation_id,),
                    ).fetchall()
                for row in rows:
                    candidate = json.loads(row["protocol_step_facts_json"])
                    if candidate:
                        facts = dict(candidate)
                        break
            except Exception:
                pass
        protocol_id = facts.get("protocol_id")
        protocol_version = facts.get("protocol_version")
        if protocol_id and protocol_version:
            protocol = domain.protocols().get_by_id(str(protocol_id))
            if protocol is not None:
                protocol_execution = ProtocolExecutionState.from_snapshot(
                    facts,
                    protocol_id=str(protocol_id),
                    protocol_version=str(protocol_version),
                    default_step_number=1,
                )
                current_step_number = protocol_execution.current_step_number
                current_step = next(
                    (
                        step for step in protocol.steps
                        if step.step_number == current_step_number
                    ),
                    None,
                )
                if current_step is not None:
                    lines.append("【当前实验方案状态】")
                    lines.append(f"方案：{protocol.title}")
                    lines.append(
                        f"当前第 {current_step.step_number} 步：{current_step.title}"
                    )
                    if getattr(current_step, "instruction", None):
                        lines.append(
                            f"步骤说明：{str(current_step.instruction)[:200]}"
                        )
                    if getattr(current_step, "protocol_values", None):
                        values = "、".join(
                            f"{key}={value}"
                            for key, value in current_step.protocol_values.items()
                        )
                        lines.append(f"方案已定：{values}")
                    # 不输出“现场必测”，全局没有必填字段。

                    current_state = protocol_execution.step_state(
                        current_step_number
                    )
                    recorded = current_state.values
                    if recorded:
                        lines.append(
                            "当前步已记录："
                            + "、".join(
                                f"{name}={value.value}"
                                for name, value in recorded.items()
                            )
                        )
                    else:
                        lines.append("当前步尚未记录实测值。")

                    statuses = protocol_execution.statuses
                    if statuses:
                        status_text = "、".join(
                            f"第{step_number}步:{status.value}"
                            for step_number, status in sorted(statuses.items())
                        )
                        lines.append(f"步骤完成状态：{status_text}")

                    # 所有步骤中已记录的字段，方便跨步引用
                    all_recorded: list[str] = []
                    for step_number, fact_state in protocol_execution.steps.items():
                        for field_name, observed in fact_state.values.items():
                            all_recorded.append(
                                f"第{step_number}步 {field_name}={observed.value}"
                            )
                    if all_recorded:
                        lines.append(
                            "本实验已记录数据：" + "；".join(all_recorded[:10])
                        )
                else:
                    lines.append("当前实验方案状态读取失败：找不到当前步骤。")
            else:
                lines.append("当前实验方案状态读取失败：方案库中找不到该方案。")
        else:
            lines.append("当前实验会话：自由记录模式（未绑定方案）。")
            if prompt_context:
                lines.append("已记录上下文见上。")

        if stored.get("experiment_step_count"):
            lines.append(
                f"本实验会话已累计 {stored['experiment_step_count']} 条记录。"
            )
        return "\n".join(lines)
    except Exception as error:  # noqa: BLE001
        return (
            "当前实验会话状态读取失败（不影响继续对话）："
            f"{type(error).__name__}: {error}"
        )


def _format_reagent_flow(
    conversation_id: Optional[str] = None,
    lab_session_id: Optional[str] = None,
) -> str:
    """试剂配制流程：优先按 lab_session_id 查，其次用 conversation_id。

    增加陈旧检测：超过 4 小时未更新的流程视为过期，不注入上下文。
    """
    from datetime import datetime, timedelta

    try:
        with get_connection() as connection:
            # 优先用 lab_session_id 查，回退到旧的 "lab-session" 键
            keys_to_try = []
            if lab_session_id:
                keys_to_try.append(lab_session_id)
            if conversation_id:
                keys_to_try.append(conversation_id)
            keys_to_try.append("lab-session")  # 兼容旧数据

            row = None
            for key in keys_to_try:
                row = connection.execute(
                    "SELECT * FROM reagent_prep_flows WHERE conversation_id=?",
                    (key,),
                ).fetchone()
                if row is not None:
                    break

        if row is None:
            return "没有进行中的试剂配置流程。"

        # 陈旧检测：updated_at 超过 4 小时的流程不注入
        updated_raw = str(row["updated_at"] or "")
        try:
            # 数据库存储格式：YYYY-MM-DD HH:MM:SS 或 ISO 格式
            updated = datetime.fromisoformat(
                updated_raw.replace(" ", "T").replace("Z", "")
            )
            age = datetime.utcnow() - updated
            if age > timedelta(hours=4):
                # 过期流程自动标记为 stale，不再误导模型
                with get_connection() as conn:
                    conn.execute(
                        "UPDATE reagent_prep_flows SET status='stale' WHERE conversation_id=?",
                        (row["conversation_id"],),
                    )
                return "没有进行中的试剂配置流程。"
        except (ValueError, TypeError):
            pass  # 时间解析失败时不阻断，保守返回

        status = row["status"]
        if status not in ("running", "active"):
            return "没有进行中的试剂配置流程。"

        return (
            f"当前试剂配置流程：reagent_prep_id={row['prep_id']}，"
            f"第 {row['current_index'] + 1} 步，状态：{status}"
        )
    except Exception:  # noqa: BLE001
        return "当前试剂配置流程读取失败。"


def _format_active_experiments(
    conversation_id: Optional[str] = None,
    current_lab_session_id: Optional[str] = None,
) -> str:
    """列出同一会话下的活跃实验，标出哪个是当前焦点。

    从 experiment_session_state 表读出同一 conversation_id 下所有有方案的状态，
    按最后更新时间排序。超过 24 小时未更新的标记为陈旧。
    """
    if not conversation_id:
        return ""
    from datetime import datetime, timedelta

    try:
        with get_connection() as connection:
            rows = connection.execute(
                """SELECT lab_session_id, protocol_step_facts_json, updated_at
                   FROM experiment_session_state
                   WHERE conversation_id=? AND protocol_step_facts_json != '{}'
                   ORDER BY updated_at DESC
                   LIMIT 5""",
                (conversation_id,),
            ).fetchall()
        if not rows:
            return ""

        lines = []
        now = datetime.utcnow()
        active_count = 0
        for row in rows:
            facts = json.loads(row["protocol_step_facts_json"] or "{}")
            protocol_id = facts.get("protocol_id")
            step_num = facts.get("current_step_number")
            if not protocol_id:
                continue
            lab_sid = row["lab_session_id"]
            updated_raw = str(row["updated_at"] or "")
            try:
                updated = datetime.fromisoformat(
                    updated_raw.replace(" ", "T").replace("Z", "")
                )
                age = now - updated
            except (ValueError, TypeError):
                age = timedelta(0)

            # 超过 24 小时不显示
            if age > timedelta(hours=24):
                continue

            # 查方案标题
            try:
                title = facts.get("protocol_title") or protocol_id
            except Exception:
                title = protocol_id

            is_current = (
                current_lab_session_id
                and lab_sid == current_lab_session_id
            )
            marker = " ← 当前" if is_current else ""
            lines.append(
                f"  • {title}（第{step_num}步）{marker}"
            )
            active_count += 1

        if not lines:
            return ""
        header = f"【活跃实验（{active_count}个）】"
        return header + "\n" + "\n".join(lines)
    except Exception:  # noqa: BLE001
        return ""


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

    # 有 lab_session_id 时，per-session store 是真相源；
    # 全局 domain 可能因恢复失败而不同步，不要用它的状态误导模型。
    if lab_session_id:
        parts.append(_format_experiment_state(conversation_id, lab_session_id))
    else:
        # 没有 lab_session_id（旧客户端/聊天模式），退化为全局 domain 状态。
        parts.append(_format_protocol_state())
    parts.append(_format_reagent_flow(conversation_id, lab_session_id))
    parts.append(_format_active_experiments(conversation_id, lab_session_id))

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
