# -*- coding: utf-8 -*-
"""主动智能体接口：手动触发心跳/反思、查看每日时间线。"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

import agent_harness
from database import crud
from database.lab_record_store import list_records_by_date

router = APIRouter(prefix="/agent", tags=["主动智能体"])


@router.post("/heartbeat/run")
def run_heartbeat():
    try:
        result = agent_harness.run_heartbeat_loop()
        return {"ok": True, "notified": result.get("notified", False), "notification": result.get("notification")}
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@router.post("/reflect")
def run_reflection():
    try:
        result = agent_harness.run_reflection_loop()
        return {"ok": True, "notified": result.get("notified", False), "notification": result.get("notification")}
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@router.get("/timeline")
def timeline(date: str = Query(default="")):
    """某一天的实验时间线：实验记录 + 实验计划 + 通知。"""
    target = date or datetime.now().strftime("%Y-%m-%d")
    try:
        datetime.strptime(target, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="日期格式应为 YYYY-MM-DD。")
    records = list_records_by_date(target)
    experiments = []
    for item in crud.list_experiments(include_completed=True):
        start = str(item.get("start_at") or "")
        if start[:10] == target:
            experiments.append(item)
    notifications = crud.list_notifications(limit=100)
    notifications = [n for n in notifications if str(n.get("period_date") or "") == target]
    return {
        "date": target,
        "records": records,
        "experiments": experiments,
        "notifications": notifications,
        "summary": {
            "record_count": len(records),
            "experiment_count": len(experiments),
            "notification_count": len(notifications),
        },
    }
