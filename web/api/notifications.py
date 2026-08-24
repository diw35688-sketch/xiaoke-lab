# -*- coding: utf-8 -*-
"""通知 / 每日工作弹窗接口，保存展示与确认溯源。"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from database import crud

router = APIRouter(prefix="/notifications", tags=["通知"])


class DailyPayload(BaseModel):
    period: str


class TodoPayload(BaseModel):
    text: str | None = None
    done: bool | None = None


class AckPayload(BaseModel):
    ack: bool = True


def _summary_text(period, dates):
    return "\n".join(f"{label}：{value}" for label, value in dates.items())


@router.get("")
def notifications(unread: bool = Query(default=False), limit: int = Query(default=50)):
    return {"items": crud.list_notifications(limit=limit, unread_only=unread)}


@router.post("/daily")
def daily(payload: DailyPayload):
    """获取当前时段每日工作弹窗；不存在则生成并返回（幂等）。"""
    period = payload.period
    if period not in crud.PERIODS:
        raise HTTPException(status_code=400, detail="period 只允许 morning/afternoon/evening。")

    today = datetime.now().strftime("%Y-%m-%d")
    existing = crud.get_notification_by_period(period, today)
    if existing:
        return existing

    today_summary = crud.work_summary(0)
    yesterday_summary = crud.work_summary(1)
    body = "\n".join([
        "【今日工作】",
        f"实验记录：{today_summary['records']} 条",
        f"新增储存：{today_summary['storage_added']} 项",
        f"用户消息：{today_summary['user_messages']} 条",
        "",
        "【昨日工作】",
        f"实验记录：{yesterday_summary['records']} 条",
        f"新增储存：{yesterday_summary['storage_added']} 项",
        f"用户消息：{yesterday_summary['user_messages']} 条",
    ])
    title = f"{period}工作摘要 · {today}"
    return crud.create_daily_notification(period, today, title, body)


@router.get("/{notification_id}")
def detail(notification_id: int):
    items = crud.list_notifications(limit=1000)
    item = next((x for x in items if x["id"] == notification_id), None)
    if item is None:
        # fallback direct fetch
        try:
            item = crud.list_notifications(limit=1000)[0]
        except Exception:
            item = None
    if item is None:
        raise HTTPException(status_code=404, detail="通知不存在。")
    item["todos"] = crud.list_notification_todos(notification_id)
    return item


@router.post("/todos")
def add_todo(payload: TodoPayload):
    raise HTTPException(status_code=400, detail="缺少 notification_id。")


@router.delete("/todos/{todo_id}")
def remove_todo(todo_id: int):
    if not crud.delete_notification_todo(todo_id):
        raise HTTPException(status_code=404, detail="待办不存在。")
    return {"ok": True}


@router.patch("/todos/{todo_id}")
def edit_todo(todo_id: int, payload: TodoPayload):
    try:
        result = crud.update_notification_todo(todo_id, text=payload.text, done=payload.done)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))
    if result is None:
        raise HTTPException(status_code=404, detail="待办不存在。")
    return result


@router.post("/{notification_id}/todos")
def add_notification_todo(notification_id: int, payload: TodoPayload):
    try:
        return crud.add_notification_todo(notification_id, payload.text or "")
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.post("/{notification_id}/shown")
def shown(notification_id: int):
    result = crud.mark_notification_shown(notification_id)
    if result is None:
        raise HTTPException(status_code=404, detail="通知不存在。")
    return result


@router.post("/{notification_id}/ack")
def ack(notification_id: int):
    result = crud.mark_notification_ack(notification_id)
    if result is None:
        raise HTTPException(status_code=404, detail="通知不存在。")
    return result
