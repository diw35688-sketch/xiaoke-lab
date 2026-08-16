from database.crud import create_experiment, list_experiments
from planner.conflicts import find_conflicts

# 基础版使用进程内的待确认记录；服务重启后会自动失效，不会误创建实验。
PENDING_EXPERIMENTS: dict[str, dict] = {}


def list_current_experiments():
    return list_experiments()


def check_experiment_conflicts(start_at, end_at, equipment):
    conflicts = find_conflicts(start_at, end_at, equipment)
    return {"has_conflict": bool(conflicts), "conflicts": conflicts}


def propose_experiment(conversation_id, name, goal, start_at, end_at, equipment, notes):
    experiment = {"name": name, "goal": goal, "start_at": start_at, "end_at": end_at, "equipment": equipment, "notes": notes}
    conflicts = find_conflicts(start_at, end_at, equipment)
    if conflicts:
        return {"ready": False, "reason": "存在时间或仪器冲突，尚未创建。", "conflicts": conflicts}
    PENDING_EXPERIMENTS[conversation_id] = experiment
    return {"ready": True, "confirmation_required": True, "experiment": experiment}


def confirm_pending_experiment(conversation_id):
    experiment = PENDING_EXPERIMENTS.get(conversation_id)
    if not experiment:
        return {"created": False, "reason": "没有待确认的实验。请先提供实验信息。"}
    conflicts = find_conflicts(experiment["start_at"], experiment["end_at"], experiment["equipment"])
    if conflicts:
        PENDING_EXPERIMENTS.pop(conversation_id, None)
        return {"created": False, "reason": "确认时检测到新的冲突，未创建。", "conflicts": conflicts}
    created = create_experiment(**experiment)
    PENDING_EXPERIMENTS.pop(conversation_id, None)
    return {"created": True, "experiment": created}
