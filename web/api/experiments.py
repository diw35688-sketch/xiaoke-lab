from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from database.crud import clear_history, create_experiment, delete_history_item, list_experiments, list_history, set_experiment_status
from planner.conflicts import find_conflicts

router = APIRouter(prefix="/experiments", tags=["实验"])


class ExperimentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    goal: str = ""
    start_at: str | None = None
    end_at: str | None = None
    equipment: str = ""
    notes: str = ""


class StatusUpdate(BaseModel):
    status: str = Field(pattern="^(pending|completed)$")


@router.get("")
def get_experiments():
    """只返回当前清单：已完成实验转入历史清单。"""
    return list_experiments()


@router.get("/history")
def get_history():
    return list_history()


@router.post("")
def add_experiment(experiment: ExperimentCreate):
    data = experiment.model_dump()
    conflicts = find_conflicts(data["start_at"], data["end_at"], data["equipment"])
    if conflicts:
        raise HTTPException(409, {"message": "检测到冲突，未创建实验。", "conflicts": conflicts})
    return create_experiment(**data)


@router.patch("/{experiment_id}/status")
def update_status(experiment_id: int, update: StatusUpdate):
    item = set_experiment_status(experiment_id, update.status)
    if item is None:
        raise HTTPException(404, "未找到该实验。")
    return item


@router.delete("/history")
def remove_all_history():
    return {"deleted": clear_history()}


@router.delete("/history/{experiment_id}")
def remove_history_item(experiment_id: int):
    if not delete_history_item(experiment_id):
        raise HTTPException(404, "未找到该历史记录。")
    return {"deleted": True}
