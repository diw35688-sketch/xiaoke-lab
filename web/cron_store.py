# -*- coding: utf-8 -*-
"""持久化 cron 任务存储：对应 OpenClaw 的 cron job store。

支持三种 schedule：
- at: 一次性
- every: 固定间隔
- cron: 简化的每日表达式（"08:00" 或标准 5 段 "0 8 * * *"）
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from database.db import get_connection, initialize_database


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _row_to_job(row) -> dict:
    job = dict(row)
    try:
        job["payload"] = json.loads(job.pop("payload_json") or "{}")
    except (json.JSONDecodeError, KeyError):
        job["payload"] = {}
    return job


def _next_from_cron_expr(expr: str, after: datetime | None = None) -> datetime | None:
    after = after or datetime.now()
    expr = (expr or "").strip()
    # "08:00" 或 "8:00"
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", expr)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            target = after.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target <= after:
                target += timedelta(days=1)
            return target
    # "0 8 * * *"
    m = re.fullmatch(r"(\d+)\s+(\d+)\s+\*\s+\*\s+\*", expr)
    if m:
        minute, hour = int(m.group(1)), int(m.group(2))
        if 0 <= minute <= 59 and 0 <= hour <= 23:
            target = after.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target <= after:
                target += timedelta(days=1)
            return target
    return None


def compute_next_run(job: dict, after: datetime | None = None) -> str:
    after = after or datetime.now()
    kind = job.get("schedule_kind")
    if kind == "at":
        try:
            at = datetime.fromisoformat(str(job.get("at") or ""))
            return at.isoformat(timespec="seconds")
        except ValueError:
            return (_now())
    if kind == "every":
        every_ms = int(job.get("every_ms") or 0)
        if every_ms <= 0:
            return (_now() + timedelta(hours=24)).isoformat(timespec="seconds")
        last = job.get("last_run_at") or ""
        try:
            base = datetime.fromisoformat(last) if last else after
        except ValueError:
            base = after
        nxt = base + timedelta(milliseconds=every_ms)
        if nxt <= after:
            nxt = after + timedelta(milliseconds=every_ms)
        return nxt.isoformat(timespec="seconds")
    if kind == "cron":
        nxt = _next_from_cron_expr(str(job.get("cron_expr") or ""), after)
        if nxt is not None:
            return nxt.isoformat(timespec="seconds")
        # 兜底：每天同一时刻
        return (after + timedelta(hours=24)).isoformat(timespec="seconds")
    return (after + timedelta(hours=24)).isoformat(timespec="seconds")


def list_jobs(include_disabled: bool = False) -> list[dict]:
    initialize_database()
    with get_connection() as connection:
        if include_disabled:
            rows = connection.execute("SELECT * FROM cron_jobs ORDER BY id").fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM cron_jobs WHERE enabled=1 ORDER BY id"
            ).fetchall()
    return [_row_to_job(row) for row in rows]


def get_job(job_id: int) -> dict | None:
    initialize_database()
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM cron_jobs WHERE id=?", (int(job_id),)
        ).fetchone()
    return _row_to_job(row) if row is not None else None


def get_job_by_declaration(declaration_key: str) -> dict | None:
    initialize_database()
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM cron_jobs WHERE declaration_key=?", (declaration_key,)
        ).fetchone()
    return _row_to_job(row) if row is not None else None


def create_job(data: dict) -> dict:
    initialize_database()
    payload = data.get("payload") or {}
    schedule = data.get("schedule") or {}
    kind = schedule.get("kind", "every")
    every_ms = int(schedule.get("everyMs", schedule.get("every_ms", 0)) or 0)
    at = str(schedule.get("at") or "")
    expr = str(schedule.get("expr", schedule.get("cron_expr", "")) or "")
    tz = str(schedule.get("tz", "local") or "local")
    row_data = {
        "declaration_key": data.get("declarationKey", ""),
        "name": data.get("name", "cron job"),
        "schedule_kind": kind,
        "at": at,
        "every_ms": every_ms,
        "cron_expr": expr,
        "cron_tz": tz,
        "enabled": 1 if data.get("enabled", True) else 0,
        "payload_kind": payload.get("kind", data.get("payload_kind", "systemEvent")),
        "payload_json": json.dumps(payload, ensure_ascii=False),
        "last_run_at": "",
        "next_run_at": "",
    }
    job = dict(row_data)
    job["next_run_at"] = compute_next_run(job)
    with get_connection() as connection:
        cursor = connection.execute(
            """INSERT INTO cron_jobs
               (declaration_key,name,schedule_kind,at,every_ms,cron_expr,cron_tz,
                enabled,payload_kind,payload_json,last_run_at,next_run_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                job["declaration_key"], job["name"], job["schedule_kind"],
                job["at"], job["every_ms"], job["cron_expr"], job["cron_tz"],
                job["enabled"], job["payload_kind"], job["payload_json"],
                job["last_run_at"], job["next_run_at"],
            ),
        )
        job_id = cursor.lastrowid
    return get_job(job_id)


def update_job(job_id: int, data: dict) -> dict | None:
    initialize_database()
    existing = get_job(job_id)
    if existing is None:
        return None
    schedule = data.get("schedule") or {}
    if schedule.get("kind"):
        existing["schedule_kind"] = schedule["kind"]
    if "at" in schedule:
        existing["at"] = str(schedule["at"] or "")
    if "everyMs" in schedule or "every_ms" in schedule:
        existing["every_ms"] = int(schedule.get("everyMs", schedule.get("every_ms", 0)) or 0)
    if "expr" in schedule or "cron_expr" in schedule:
        existing["cron_expr"] = str(schedule.get("expr", schedule.get("cron_expr", "")) or "")
    if "tz" in schedule:
        existing["cron_tz"] = str(schedule.get("tz") or "local")
    if data.get("name") is not None:
        existing["name"] = str(data["name"])
    if data.get("enabled") is not None:
        existing["enabled"] = 1 if data["enabled"] else 0
    if data.get("payload") is not None:
        existing["payload"] = data["payload"]
        existing["payload_kind"] = data["payload"].get("kind", existing.get("payload_kind", "systemEvent"))
    existing["next_run_at"] = compute_next_run(existing)
    with get_connection() as connection:
        connection.execute(
            """UPDATE cron_jobs SET
               name=?, schedule_kind=?, at=?, every_ms=?, cron_expr=?, cron_tz=?,
               enabled=?, payload_kind=?, payload_json=?, next_run_at=?, updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (
                existing["name"], existing["schedule_kind"], existing["at"],
                existing["every_ms"], existing["cron_expr"], existing["cron_tz"],
                existing["enabled"], existing["payload_kind"],
                json.dumps(existing.get("payload") or {}, ensure_ascii=False),
                existing["next_run_at"], int(job_id),
            ),
        )
    return get_job(job_id)


def delete_job(job_id: int) -> bool:
    initialize_database()
    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM cron_jobs WHERE id=?", (int(job_id),))
        return bool(cursor.rowcount)


def mark_run(job_id: int, last_run_at: str):
    initialize_database()
    job = get_job(job_id)
    if job is None:
        return
    job["last_run_at"] = last_run_at
    job["next_run_at"] = compute_next_run(job)
    with get_connection() as connection:
        connection.execute(
            "UPDATE cron_jobs SET last_run_at=?, next_run_at=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (last_run_at, job["next_run_at"], int(job_id)),
        )
