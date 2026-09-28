# -*- coding: utf-8 -*-
"""超长会话压缩（Transcript Compaction）。

对应 OpenClaw 的 compaction：
- 历史超过阈值时，把「较早的部分」交给模型压成摘要，最近的部分保留原文
- 摘要按会话持久化，下一次只把「上次摘要之后新淘汰的消息」喂给摘要器（滚动摘要）
- 摘要失败时**显式标注**并保留最近原文，绝不静默丢内容

为什么按字符而不是按条数触发：
    48 条短消息和 48 条长消息的 token 差 10 倍，按条数触发完全不可控。
    这里用字符数做 token 的近似（中文约 1 字 ≈ 1 token），不引入 tokenizer 依赖。

⚠️ 历史遗留的两个 bug（本文件已修）：
    1. 旧实现触发条件是 `len(history) > 48`，但调用方 `get_recent_messages()`
       默认只取 20 条 → history 最多 21 条 → **压缩从未触发（死代码）**。
    2. 旧实现 `if stored.get("summary"): return [摘要, *tail]` 里
       `summarized_until_id` 存了却从来不读 → 摘要永远不更新，
       而 head 却一直在长 → **中间那段对话被静默丢弃**。
"""

from __future__ import annotations

import json
from datetime import datetime

import httpx
import settings_store
from database.db import get_connection, initialize_database
from openai import OpenAI

#: 历史总字符数超过它才压缩（≈3000 token）。低于这个规模原样送，行为与压缩前一致。
DEFAULT_TRIGGER_CHARS = 6000
#: 压缩后保留的最近原文规模（字符）。
DEFAULT_TAIL_CHARS = 3000
#: 兜底：无论字符多少，最多保留的原文条数，防止极短消息堆太多条。
DEFAULT_MAX_TAIL = 16

#: 摘要失败时的显式标记 —— 宁可写明「省略了」，也不静默丢消息。
_DROP_NOTICE = {
    "role": "system",
    "content": "（较早的对话因摘要生成失败已省略，如需追溯请查看会话历史）",
}


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


def summarize_messages(messages: list[dict], previous_summary: str | None = None) -> str:
    """把一段历史压缩成摘要（滚动式）。

    previous_summary 非空时，让模型在旧摘要的基础上并入新增对话，
    这样每次只需要付费「旧摘要 + 本次新淘汰的消息」，不必重新读全部历史。
    失败时抛出异常，由调用方降级。
    """
    parts = []
    if previous_summary:
        parts.append(f"【已有摘要】（覆盖更早的对话）\n{previous_summary}")
    parts.append(f"【本次新增对话】\n{_text_of(messages)}")
    client = _client()
    response = client.chat.completions.create(
        model=settings_store.current().model_name,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是会话压缩器。把下面的实验助手历史对话压缩成一段简洁的中文摘要，"
                    "保留：用户目标、进行中的实验方案、当前步骤、关键操作、已记录数据、"
                    "尚未解决的问题、重要安全信息。"
                    "如果给了【已有摘要】，把它和【本次新增对话】合并成一份摘要，"
                    "不要丢失已有摘要里的信息，也不要重复。不要编造不存在的内容。"
                    "只输出摘要正文：不要写标题、不要写「【已有摘要】」这类分节标记、"
                    "不要解释你在做什么。"
                ),
            },
            {"role": "user", "content": "\n\n".join(parts)},
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


def save_compaction_summary(conversation_id: str, summary: str,
                            summarized_until_id: int = 0) -> dict:
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


# ---------- 内部工具：规模度量、切尾、清洗 ----------

def _msg_id(item: dict):
    """取消息的数据库 id；没有（合成 history）时返回 None。"""
    try:
        value = item.get("id")
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _char_size(items: list[dict]) -> int:
    """历史规模（字符）。用字符数近似 token，避免引入 tokenizer 依赖。"""
    return sum(len(str(item.get("content") or "")) for item in items)


def _clean(items: list[dict]) -> list[dict]:
    """只保留 role / content。

    调用方可能带 id（压缩需要用它做增量判断），但 id 不能进模型请求体，
    所以对外返回前一律洗掉。
    """
    return [
        {"role": str(item.get("role") or "user"), "content": item.get("content") or ""}
        for item in items
    ]


def _tail_slice(items: list[dict], max_tail: int, tail_chars: int) -> list[dict]:
    """从末尾往前取原文，直到超过字符或条数上限（至少留 1 条）。"""
    tail: list[dict] = []
    used = 0
    for item in reversed(items):
        size = len(str(item.get("content") or ""))
        if tail and (used + size > tail_chars or len(tail) >= max_tail):
            break
        tail.append(item)
        used += size
    tail.reverse()
    return tail


def _summary_message(text: str) -> dict:
    return {"role": "system", "content": f"以下是较早对话的压缩摘要：\n{text}"}


def compact_history(
    history: list[dict],
    conversation_id: str | None = None,
    max_tail: int = DEFAULT_MAX_TAIL,
    trigger_chars: int = DEFAULT_TRIGGER_CHARS,
    tail_chars: int = DEFAULT_TAIL_CHARS,
) -> list[dict]:
    """把过长的 history 压成「较早对话的摘要 + 最近原文」。

    - 规模未超阈值：原样返回（只洗掉非标准字段），不做任何额外模型调用。
    - 已压缩过且没有新淘汰的消息：直接复用持久化摘要，不重复付费。
    - 摘要失败：保留最近原文 + 显式省略标记，不静默丢内容。

    返回的消息一律只含 role / content。
    """
    items = list(history or [])
    if not items:
        return []

    if _char_size(items) <= trigger_chars:
        return _clean(items)

    tail = _tail_slice(items, max_tail, tail_chars)
    head = items[: len(items) - len(tail)]
    if not head:
        return _clean(items)

    stored = get_compaction_summary(conversation_id) if conversation_id else None
    previous = str((stored or {}).get("summary") or "")
    try:
        through = int((stored or {}).get("summarized_until_id") or 0)
    except (TypeError, ValueError):
        through = 0

    # 增量：只把「上次摘要之后新进入 head 的消息」交给摘要器。
    # 没有 id 的（合成 history）一律当作待压缩，保证不漏。
    pending = [m for m in head if (_msg_id(m) is None or _msg_id(m) > through)]

    if not pending and previous:
        return [_summary_message(previous), *_clean(tail)]

    try:
        summary = summarize_messages(pending, previous or None)
    except Exception:
        # 摘要失败：保留最近原文并写明省略，绝不静默丢弃。
        return [_DROP_NOTICE, *_clean(tail)]

    if not summary:
        return [_DROP_NOTICE, *_clean(tail)]

    ids = [i for i in (_msg_id(m) for m in head) if i is not None]
    new_through = max([through, *ids]) if ids else through
    if conversation_id:
        try:
            save_compaction_summary(conversation_id, summary, new_through)
        except Exception:
            pass

    return [_summary_message(summary), *_clean(tail)]
