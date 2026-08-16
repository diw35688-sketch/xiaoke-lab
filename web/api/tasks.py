from fastapi import APIRouter, HTTPException, Query
from database.task_store import get_task, get_undelivered_results, list_tasks
from tasks.task_manager import task_manager

router = APIRouter(prefix="/tasks", tags=["后台任务"])


@router.get("")
def get_tasks(conversation_id: str = Query(min_length=1, max_length=64)):
    return list_tasks(conversation_id)


@router.get("/updates")
def get_task_updates(conversation_id: str = Query(min_length=1, max_length=64)):
    return get_undelivered_results(conversation_id)


@router.post("/{task_id}/cancel")
def cancel_background_task(task_id: str):
    task = task_manager.cancel(task_id)
    if not task:
        raise HTTPException(404, "未找到该后台任务。")
    return task


@router.get("/{task_id}")
def get_one_task(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "未找到该后台任务。")
    return task
