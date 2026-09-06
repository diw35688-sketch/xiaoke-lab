# -*- coding: utf-8 -*-
"""持久化 cron 服务：对应 OpenClaw 的 Gateway scheduler。

系统心跳/反思以 cron_jobs 形式持久化，重启不丢；到点自动执行。
"""

from __future__ import annotations

import threading
from datetime import datetime

import cron_store
from agent_harness import run_heartbeat_loop, run_reflection_loop
from database.crud import run_daily_experiment_check
from settings_store import current as current_settings

_started = False
_lock = threading.Lock()
_stop = threading.Event()

HEARTBEAT_DECLARATION = "system:heartbeat"
REFLECTION_DECLARATION = "system:reflection"


def _heartbeat_time() -> str:
    return (current_settings().heartbeat_time or "08:00").strip() or "08:00"


def reconcile_system_jobs() -> None:
    heartbeat = cron_store.get_job_by_declaration(HEARTBEAT_DECLARATION)
    heartbeat_payload = {"kind": "heartbeat"}
    if heartbeat is None:
        cron_store.create_job({
            "declarationKey": HEARTBEAT_DECLARATION,
            "name": "每日心跳",
            "enabled": current_settings().heartbeat_enabled,
            "schedule": {"kind": "cron", "expr": _heartbeat_time(), "tz": "local"},
            "payload": heartbeat_payload,
        })
    else:
        cron_store.update_job(heartbeat["id"], {
            "name": "每日心跳",
            "enabled": current_settings().heartbeat_enabled,
            "schedule": {"kind": "cron", "expr": _heartbeat_time(), "tz": "local"},
            "payload": heartbeat_payload,
        })

    reflection = cron_store.get_job_by_declaration(REFLECTION_DECLARATION)
    reflection_payload = {"kind": "reflection"}
    if reflection is None:
        cron_store.create_job({
            "declarationKey": REFLECTION_DECLARATION,
            "name": "每晚反思",
            "enabled": True,
            "schedule": {"kind": "cron", "expr": "21:00", "tz": "local"},
            "payload": reflection_payload,
        })
    else:
        cron_store.update_job(reflection["id"], {
            "name": "每晚反思",
            "enabled": True,
            "schedule": {"kind": "cron", "expr": "21:00", "tz": "local"},
            "payload": reflection_payload,
        })


def run_job(job: dict) -> dict:
    payload_kind = job.get("payload_kind") or (job.get("payload") or {}).get("kind") or "systemEvent"
    if payload_kind == "heartbeat":
        return run_heartbeat_loop()
    if payload_kind == "reflection":
        return run_reflection_loop()
    if payload_kind in ("experiment_check", "daily_check"):
        run_daily_experiment_check()
        return {"ok": True, "payload_kind": payload_kind}
    return {"ok": True, "skipped": True, "payload_kind": payload_kind}


def _due_jobs(now: datetime):
    jobs = cron_store.list_jobs(include_disabled=True)
    for job in jobs:
        if not job.get("enabled"):
            continue
        next_run = str(job.get("next_run_at") or "")
        if not next_run:
            continue
        try:
            due_at = datetime.fromisoformat(next_run)
        except ValueError:
            continue
        if due_at <= now:
            yield job


def _loop() -> None:
    while not _stop.is_set():
        now = datetime.now()
        try:
            for job in _due_jobs(now):
                try:
                    run_job(job)
                except Exception:
                    # 单个任务失败不拖垮调度器
                    pass
                try:
                    cron_store.mark_run(job["id"], now.isoformat(timespec="seconds"))
                except Exception:
                    pass
        except Exception:
            pass
        _stop.wait(5)


def start_cron_service() -> None:
    global _started
    with _lock:
        if _started:
            return
        _started = True
        try:
            reconcile_system_jobs()
        except Exception:
            pass
        threading.Thread(target=_loop, name="cron-service", daemon=True).start()


def stop_cron_service() -> None:
    _stop.set()
