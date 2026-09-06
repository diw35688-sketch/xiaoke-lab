# -*- coding: utf-8 -*-
"""任务会话持久化：当前方案 / 当前步 / 各步记录进度写入 SQLite。

内存里的 domain._session / domain._progress 是"工作台"，这里把关键状态落盘：
页面刷新、横竖屏切换、甚至服务器重启，进度都不丢。
三张表：
- session_snapshot        单行：当前方案 id + 当前步号
- step_progress_rows      各步已记录到的字段名（一步多行）
- step_deviation_flags    出现偏差的步号

注意：每个函数用完必须 conn.close()——sqlite 的 with conn 只提交事务、不关闭
连接，句柄不关会导致文件被占用（测试里表现为删不掉临时库）。
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

# 与 config.DATABASE_PATH 指向同一文件；测试可整体替换该路径。
if getattr(sys, "frozen", False):
    DB_PATH = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)) / "web" / "lab_agent.db"
else:
    DB_PATH = Path(__file__).resolve().parent.parent / "lab_agent.db"

_DDL = [
    """CREATE TABLE IF NOT EXISTS session_snapshot (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        protocol_id TEXT,
        step_number INTEGER,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS step_progress_rows (
        step_number INTEGER NOT NULL,
        field_name TEXT NOT NULL,
        PRIMARY KEY (step_number, field_name))""",
    """CREATE TABLE IF NOT EXISTS step_deviation_flags (
        step_number INTEGER PRIMARY KEY,
        flagged_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS step_confirmation_flags (
        step_number INTEGER PRIMARY KEY,
        confirmed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
]


def _open() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    for ddl in _DDL:
        conn.execute(ddl)
    return conn


def save_session_snapshot(protocol_id, step_number) -> None:
    """保存当前会话快照；自由模式 protocol_id/step_number 均为 None。"""
    conn = _open()
    try:
        conn.execute(
            """INSERT INTO session_snapshot (id, protocol_id, step_number)
               VALUES (1, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 protocol_id = excluded.protocol_id,
                 step_number = excluded.step_number,
                 updated_at = CURRENT_TIMESTAMP""",
            (protocol_id, step_number),
        )
        conn.commit()
    finally:
        conn.close()


def load_session_snapshot():
    """读取会话快照；从没保存过时返回 None。"""
    conn = _open()
    try:
        row = conn.execute(
            "SELECT protocol_id, step_number FROM session_snapshot WHERE id = 1"
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {"protocol_id": row["protocol_id"], "step_number": row["step_number"]}


def save_step_progress(step_number, field_names, has_deviation) -> None:
    """增量保存一步的进度：字段名去重入库；偏差标记入库。"""
    if step_number is None:
        return
    conn = _open()
    try:
        for name in field_names or ():
            conn.execute(
                "INSERT OR IGNORE INTO step_progress_rows (step_number, field_name) VALUES (?, ?)",
                (step_number, name),
            )
        if has_deviation:
            conn.execute(
                "INSERT OR IGNORE INTO step_deviation_flags (step_number) VALUES (?)",
                (step_number,),
            )
        conn.commit()
    finally:
        conn.close()


def load_step_progress() -> dict:
    """读出全部步骤进度：{step_number: {"recorded": [...], "deviation": bool}}。"""
    result: dict = {}
    conn = _open()
    try:
        for row in conn.execute(
            "SELECT step_number, field_name FROM step_progress_rows ORDER BY field_name"
        ):
            result.setdefault(row["step_number"], {"recorded": [], "deviation": False})
            result[row["step_number"]]["recorded"].append(row["field_name"])
        for row in conn.execute("SELECT step_number FROM step_deviation_flags"):
            result.setdefault(row["step_number"], {"recorded": [], "deviation": False})
            result[row["step_number"]]["deviation"] = True
    finally:
        conn.close()
    return result


def save_step_confirmation(step_number) -> None:
    """记录一次用户手动确认完成（人类责任确认）。"""
    if step_number is None:
        return
    conn = _open()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO step_confirmation_flags (step_number) VALUES (?)",
            (step_number,),
        )
        conn.commit()
    finally:
        conn.close()


def load_step_confirmations() -> list:
    """读出全部手动确认的步号列表。"""
    conn = _open()
    try:
        rows = conn.execute("SELECT step_number FROM step_confirmation_flags").fetchall()
    finally:
        conn.close()
    return [row["step_number"] for row in rows]


def clear_progress_rows() -> None:
    """清空各步进度（换方案/重置会话时调用）。"""
    conn = _open()
    try:
        conn.execute("DELETE FROM step_progress_rows")
        conn.execute("DELETE FROM step_deviation_flags")
        conn.execute("DELETE FROM step_confirmation_flags")
        conn.commit()
    finally:
        conn.close()
