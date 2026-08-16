from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from database.crud import create_experiment_plan
from planner.conflicts import find_conflicts
from planner.templates import build_plan, list_templates

router = APIRouter(prefix="/experiment-templates", tags=["实验模板"])


class PlanRequest(BaseModel):
    template_id: str = Field(min_length=1, max_length=80)
    start_at: str = Field(min_length=10, max_length=40)
    name: str = Field(default="", max_length=200)


def _preview(request: PlanRequest):
    plan = build_plan(request.template_id, request.start_at, request.name)
    conflicts = []
    for step in plan["steps"]:
        items = find_conflicts(step["start_at"], step["end_at"], step["equipment"])
        if items:
            conflicts.append({"order": step["order"], "name": step["name"], "conflicts": items})
    return plan, conflicts


@router.get("")
def get_templates():
    return list_templates()


@router.post("/preview")
def preview_plan(request: PlanRequest):
    try:
        plan, conflicts = _preview(request)
        return {**plan, "conflicts": conflicts, "ready": not conflicts}
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.post("/plans")
def create_plan(request: PlanRequest):
    try:
        plan, conflicts = _preview(request)
        if conflicts:
            raise HTTPException(409, {"message": "计划存在仪器时间冲突，未写入日历。", "conflicts": conflicts})
        return create_experiment_plan(plan["template"]["id"], plan["plan_name"], plan["start_at"], plan["steps"])
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
