# -*- coding: utf-8 -*-
"""实验语音记录的 SQLite 落盘。

设计要点：
- 记录以行为单位，整段口述原文 + 抽取实体 + 确定性判断 + 当时步骤
  整体 JSON 落盘，不做列级拆散，保证以后加字段不需要迁移表结构。
- session_id 由本模块持有，server 重启后自动恢复最近一次会话，
  因此刷新页面 / 重启 uvicorn 都不会丢失“本次记录”页。
- 只负责存取，不判断缺什么、不判断有没有偏差——业务规则仍在上游。
"""

from __future__ import annotations

import json
import queue
import sqlite3
import threading
from datetime import datetime

from database.db import get_connection, initialize_database

_lock = threading.RLock()
_session_id: str | None = None
_conversation_id: str | None = None

# ---------------------------------------------------------------------------
# 进程内事件总线：save_record 写完后通知所有 SSE 订阅者，前端立刻刷新实验本。
# ---------------------------------------------------------------------------
_event_lock = threading.Lock()
_event_subscribers: list[queue.Queue] = []


def subscribe_record_events() -> queue.Queue:
    """订阅记录变更事件，返回一个 Queue；取消订阅时调用 unsubscribe。"""
    q: queue.Queue = queue.Queue(maxsize=64)
    with _event_lock:
        _event_subscribers.append(q)
    return q


def unsubscribe_record_events(q: queue.Queue) -> None:
    with _event_lock:
        if q in _event_subscribers:
            _event_subscribers.remove(q)


def _notify_record_written(record: dict) -> None:
    """记录写完后向所有订阅者推送通知；满队列直接丢弃，不阻塞写流程。"""
    with _event_lock:
        subs = list(_event_subscribers)
    event = {
        "type": "record_written",
        "conversation_id": record.get("conversation_id"),
        "session_id": record.get("session_id"),
        "segment_id": record.get("segment_id"),
        "transcript": str(record.get("transcript", ""))[:200],
        "at": record.get("at"),
    }
    for q in subs:
        try:
            q.put_nowait(event)
        except queue.Full:
            pass


def set_current_session(session_id: str, conversation_id: str | None = None) -> None:
    """外部链路（语音 MCP → /internal/tool-execute）同步实验会话到记录层。

    语音工具通过 MCP 调用时，lab_session_id 和 conversation_id 由上层传入，
    但 lab_record_store 的全局 _session_id 可能还停在旧会话上。此函数让
    记录层与当前会话对齐，确保写入正确的 session 和 conversation。
    """
    global _session_id, _conversation_id
    with _lock:
        if session_id:
            _session_id = session_id
        if conversation_id is not None:
            _conversation_id = conversation_id


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_session_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _json_dump(value, fallback=None) -> str:
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return json.dumps(fallback or {}, ensure_ascii=False)


def _json_load(text, fallback=None):
    if not text:
        return fallback if fallback is not None else {}
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return fallback if fallback is not None else {}


def _row_to_item(row: sqlite3.Row) -> dict:
    item = {
        "id": row["id"],
        "session_id": row["session_id"],
        "segment_id": row["segment_id"],
        "transcript": row["transcript"],
        "entities": _json_load(row["entities"], {}),
        "extraction": _json_load(row["extraction"], None),
        "extraction_source": row["extraction_source"],
        "evaluation": _json_load(row["evaluation"], {}),
        "step": _json_load(row["step"], None),
        "at": row["at"],
        "conversation_id": row["conversation_id"] if "conversation_id" in row.keys() else None,
        "turn_id": row["turn_id"] if "turn_id" in row.keys() else None,
        "request_id": row["request_id"] if "request_id" in row.keys() else None,
        "recorded_by_id": row["recorded_by_id"] if "recorded_by_id" in row.keys() else None,
        "recorded_by_name": row["recorded_by_name"] if "recorded_by_name" in row.keys() else None,
    }
    return item


def current_session_id() -> str:
    """当前实验记录会话；首次访问时按以下顺序恢复：
    1. app_settings 里的 current_lab_session（点过“新会话”后，空会话也能存活到重启）
    2. lab_records 里最近一次有记录的会话
    3. 新建一个会话 id
    """
    global _session_id
    with _lock:
        if _session_id is not None:
            return _session_id
        initialize_database()
        with get_connection() as connection:
            row = connection.execute(
                "SELECT value FROM app_settings WHERE key = 'current_lab_session'"
            ).fetchone()
            if row is not None and row["value"]:
                _session_id = row["value"]
                return _session_id
            row = connection.execute(
                "SELECT session_id FROM lab_records ORDER BY id DESC LIMIT 1"
            ).fetchone()
        _session_id = row["session_id"] if row is not None else _new_session_id()
        return _session_id


def start_new_session() -> str:
    """开始新会话：只切 session_id，不删除旧记录，并让空会话跨重启保留。"""
    global _session_id
    with _lock:
        initialize_database()
        _session_id = _new_session_id()
        with get_connection() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO app_settings (key, value) VALUES ('current_lab_session', ?)",
                (_session_id,),
            )
        return _session_id


def next_segment_id(session_id: str) -> int:
    """下一段口述的序号；从已落盘记录推算，服务重启后也连续。"""
    initialize_database()
    with get_connection() as connection:
        row = connection.execute(
            "SELECT COALESCE(MAX(segment_id), 0) + 1 AS next_segment FROM lab_records WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return int(row["next_segment"])


def save_record(item: dict) -> dict:
    """插入一段实验记录并返回数据库里的完整记录。

    item 必须包含 transcript / entities / evaluation / at / step 等业务字段；
    session_id 和 segment_id 缺省时由本模块补齐，便于工具链路复用。
    """
    initialize_database()
    session_id = str(item.get("session_id") or current_session_id())
    segment_id = int(item.get("segment_id") or next_segment_id(session_id))
    now = _now()
    last_error = None
    # conversation_id: 优先用 item 里传的，其次用全局 _conversation_id（语音链路设置）。
    conversation_id = item.get("conversation_id") or _conversation_id
    # 段号由 next_segment_id 从现有记录推算；并发记录同一会话时可能撞号，
    # 靠唯一约束兜底并自动顺延，而不是让用户重说一遍。
    for _ in range(3):
        try:
            with get_connection() as connection:
                cursor = connection.execute(
                    """INSERT INTO lab_records
                       (session_id, segment_id, transcript, entities, extraction,
                        extraction_source, evaluation, step, at,
                        conversation_id,
                        recorded_by_id, recorded_by_name)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        session_id,
                        segment_id,
                        str(item.get("transcript", "")),
                        _json_dump(item.get("entities") or {}, {}),
                        _json_dump(item.get("extraction"), None),
                        str(item.get("extraction_source") or "none"),
                        _json_dump(item.get("evaluation") or {}, {}),
                        _json_dump(item.get("step"), None),
                        str(item.get("at") or now),
                        conversation_id,
                        *_signature(conversation_id),
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM lab_records WHERE id = ?", (cursor.lastrowid,)
                ).fetchone()
            saved = _row_to_item(row)
            global _session_id
            with _lock:
                _session_id = saved["session_id"]
            _notify_record_written(saved)
            return saved
        except sqlite3.IntegrityError as error:
            last_error = error
            segment_id = next_segment_id(session_id)
    if last_error:
        raise last_error
    raise RuntimeError("实验记录落盘失败")





def list_records(session_id: str | None = None, limit: int | None = None) -> list[dict]:
    """按会话返回记录，旧段在前。不传 session_id 时返回当前会话。"""
    initialize_database()
    target = session_id or current_session_id()
    query = "SELECT * FROM lab_records WHERE session_id = ? ORDER BY segment_id, id"
    params: list = [target]
    if limit is not None:
        query += " LIMIT ?"
        params.append(int(limit))
    with get_connection() as connection:
        rows = connection.execute(query, params).fetchall()
    return [_row_to_item(row) for row in rows]


def list_sessions(limit: int = 20) -> list[dict]:
    """列出最近的实验记录会话，供后续“会话总结 / 报告导出”使用。"""
    initialize_database()
    with get_connection() as connection:
        rows = connection.execute(
            """SELECT session_id,
                      COUNT(*) AS record_count,
                      MAX(at) AS last_record_at,
                      MIN(at) AS first_record_at
               FROM lab_records
               GROUP BY session_id
               ORDER BY MAX(id) DESC
               LIMIT ?""",
            (int(limit),),
        ).fetchall()
    return [dict(row) for row in rows]


def list_records_by_date(date_text: str, limit: int = 500) -> list[dict]:
    """按本地日期返回实验记录（供每日时间线/反思使用）。"""
    initialize_database()
    with get_connection() as connection:
        rows = connection.execute(
            """SELECT * FROM lab_records
               WHERE date(at) = date(?, 'localtime')
               ORDER BY id DESC
               LIMIT ?""",
            (date_text, int(limit)),
        ).fetchall()
    return [_row_to_item(row) for row in rows]


def delete_records(session_id: str | None = None) -> int:
    """删除一条会话的全部记录；不传则删除当前会话。"""
    initialize_database()
    target = session_id or current_session_id()
    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM lab_records WHERE session_id = ?", (target,)
        )
        return cursor.rowcount


def _signature(conversation_id):
    """记录落库时补上署名；查不到就留空，绝不编造。"""
    from attribution import signature_for_conversation

    return signature_for_conversation(conversation_id)
