# -*- coding: utf-8 -*-
"""超长会话压缩（Transcript Compaction）。

对应 OpenClaw 的 compaction：
- 超过阈值的历史对话先交给模型生成摘要
- 旧摘要 + 最近 N 条原文继续作为上下文
- 摘要按会话持久化，避免每次重复压缩
"""

from __future__ import annotations

import json
from datetime import datetime

import httpx
import settings_store
from database.db import get_connection, initialize_database
from openai import OpenAI

DEFAULT_MAX_TAIL = 30
DEFAULT_TRIGGER = 48


def _client() -> OpenAI:
    s = settings_store.current()
    if not s.api_key:
        raise ValueError("尚未配置模型密钥。")
    return OpenAI(
        api_key=s.api_key,
        base_url=s.base_url,
        timeout=httpx.Timeout(60, connect=10),
        max_retries=3,
        http_client=httpx.Client(trust_env=False),
    )


def _extra_body() -> dict:
    if settings_store.current().voice_disable_thinking:
        return {"thinking": {"type": "disabled"}}
    return {}


def _text_of(messages: list[dict]) -> str:
    lines = []
    for item in messages:
        role = item.get("role", "user")
        content = str(item.get("content") or "")
        if role == "system":
            lines.append(f"[系统] {content}")
        elif role == "user":
            lines.append(f"[用户] {content}")
        elif role == "assistant":
            lines.append(f"[助手] {content}")
        elif role == "tool":
            lines.append(f"[工具] {content}")
    return "\n".join(lines)


def summarize_messages(messages: list[dict]) -> str:
    """把一段历史消息压缩成摘要。失败时抛出异常，由调用方降级。"""
    client = _client()
    response = client.chat.completions.create(
        model=settings_store.current().model_name,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是会话压缩器。把下面的实验助手历史对话压缩成一段简洁的中文摘要，"
                    "保留：用户目标、进行中的实验方案、当前步骤、关键操作、已记录数据、"
                    "尚未解决的问题、重要安全信息。不要编造不存在的内容。"
                ),
            },
            {"role": "user", "content": _text_of(messages)},
        ],
        extra_body=_extra_body(),
    )
    return (response.choices[0].message.content or "").strip()


def get_compaction_summary(conversation_id: str) -> dict | None:
    if not conversation_id:
        return None
    initialize_database()
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM conversation_compactions WHERE conversation_id=?",
            (conversation_id,),
        ).fetchone()
    return dict(row) if row is not None else None


def save_compaction_summary(conversation_id: str, summary: str, summarized_until_id: int = 0) -> dict:
    initialize_database()
    now = datetime.now().isoformat(timespec="seconds")
    with get_connection() as connection:
        connection.execute(
            """INSERT INTO conversation_compactions
               (conversation_id, summary, summarized_until_id, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(conversation_id) DO UPDATE SET
                 summary=excluded.summary,
                 summarized_until_id=excluded.summarized_until_id,
                 updated_at=excluded.updated_at""",
            (conversation_id, summary, int(summarized_until_id or 0), now),
        )
        row = connection.execute(
            "SELECT * FROM conversation_compactions WHERE conversation_id=?",
            (conversation_id,),
        ).fetchone()
    return dict(row)


def compact_history(
    history: list[dict],
    conversation_id: str | None = None,
    max_tail: int = DEFAULT_MAX_TAIL,
    trigger: int = DEFAULT_TRIGGER,
) -> list[dict]:
    """把超过阈值的 history 压缩为 摘要 + 最近 max_tail 条。

    - 历史总条数 <= trigger 时不压缩。
    - 已有持久化摘要且没有更多旧消息时直接复用。
    - 摘要失败时降级为只保留最近 max_tail 条，不让对话中断。
    """
    history = list(history or [])
    if len(history) <= trigger:
        return history

    head = history[:-max_tail]
    tail = history[-max_tail:]

    if conversation_id:
        stored = get_compaction_summary(conversation_id)
        if stored and stored.get("summary"):
            return [
                {"role": "system", "content": f"以下是较早对话的压缩摘要：\n{stored['summary']}"},
                *tail,
            ]

    try:
        summary = summarize_messages(head)
    except Exception:
        # 压缩失败也不能把整段上下文丢掉太多：至少保留最近内容。
        return tail

    if conversation_id:
        try:
            save_compaction_summary(conversation_id, summary)
        except Exception:
            pass

    return [
        {"role": "system", "content": f"以下是较早对话的压缩摘要：\n{summary}"},
        *tail,
    ]
