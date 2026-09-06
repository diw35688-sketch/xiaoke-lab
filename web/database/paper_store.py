# -*- coding: utf-8 -*-
"""论文/Protocol 文件上传的持久化：保存原文件、OCR 文本和生成的方案草稿。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from config import BASE_DIR
from database.db import get_connection, initialize_database

PAPER_DIR = BASE_DIR / "uploads" / "papers"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def save_paper(
    *,
    title: str,
    filename: str,
    file_path: str,
    ocr_text: str,
    drafts: list,
) -> dict:
    initialize_database()
    PAPER_DIR.mkdir(parents=True, exist_ok=True)
    with get_connection() as connection:
        cursor = connection.execute(
            """INSERT INTO paper_sources
               (title, filename, file_path, ocr_text, drafts_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                title or filename or "未命名论文",
                filename,
                file_path,
                ocr_text,
                json.dumps(drafts, ensure_ascii=False),
                _now(),
            ),
        )
        row = connection.execute(
            "SELECT * FROM paper_sources WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return dict(row)


def list_papers(limit: int = 50) -> list[dict]:
    initialize_database()
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM paper_sources ORDER BY id DESC LIMIT ?", (int(limit),)
        ).fetchall()
    return [dict(row) for row in rows]


def get_paper(paper_id: int) -> dict | None:
    initialize_database()
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM paper_sources WHERE id = ?", (int(paper_id),)
        ).fetchone()
    return dict(row) if row is not None else None
