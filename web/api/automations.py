# -*- coding: utf-8 -*-
"""自动化任务接口：对应 OpenClaw 的 cron tool / automations。

支持创建、列出、修改、删除、立即运行持久化 cron 任务。
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import cron_service
import cron_store

router = APIRouter(prefix="/automations", tags=["自动化任务"])


class AutomationCreatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    schedule: dict = Field(description="支持 {kind:'at',at} / {kind:'every',everyMs} / {kind:'cron',expr}")
    payload: dict = Field(default_factory=dict)
    enabled: bool = True
    declarationKey: str = ""


class AutomationUpdatePayload(BaseModel):
    name: str | None = None
    schedule: dict | None = None
    payload: dict | None = None
    enabled: bool | None = None


@router.get("")
def list_automations(include_disabled: bool = True):
    return {"items": cron_store.list_jobs(include_disabled=include_disabled)}


@router.post("")
def create_automation(payload: AutomationCreatePayload):
    try:
        job = cron_store.create_job({
            "declarationKey": payload.declarationKey,
            "name": payload.name,
            "enabled": payload.enabled,
            "schedule": payload.schedule,
            "payload": payload.payload,
        })
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))
    return {"ok": True, "job": job}


@router.patch("/{job_id}")
def update_automation(job_id: int, payload: AutomationUpdatePayload):
    data = payload.model_dump(exclude_none=True)
    job = cron_store.update_job(job_id, data)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在。")
    return {"ok": True, "job": job}


@router.delete("/{job_id}")
def delete_automation(job_id: int):
    if not cron_store.delete_job(job_id):
        raise HTTPException(status_code=404, detail="任务不存在。")
    return {"ok": True}


@router.post("/{job_id}/run")
def run_automation(job_id: int):
    job = cron_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在。")
    try:
        result = cron_service.run_job(job)
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))
    try:
        from datetime import datetime
        cron_store.mark_run(job_id, datetime.now().isoformat(timespec="seconds"))
    except Exception:
        pass
    return {"ok": True, "result": result}
