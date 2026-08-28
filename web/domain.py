# -*- coding: utf-8 -*-
"""网页层到领域层的桥：复用 src/ 里已验证的方案与安全逻辑。

web/ 以自身为工作目录启动，src/ 在仓库根目录，因此这里显式把根目录
加入模块搜索路径。除此之外不做任何业务判断，只负责装配与转译。
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.protocol_segment_evaluation import evaluate_segment  # noqa: E402
from src.core.protocol_selection import select_protocol  # noqa: E402
from src.core.protocol_session import ProtocolSessionState  # noqa: E402
from src.llm.schemas import ExperimentEntities  # noqa: E402
from src.storage.hazmat_store import HazmatStore  # noqa: E402
from src.storage.protocol_store import ProtocolStore  # noqa: E402

from step_progress import StepProgress, card_type_for  # noqa: E402
from database.session_store import (  # noqa: E402
    clear_progress_rows,
    load_session_snapshot,
    load_step_confirmations,
    load_step_progress,
    save_session_snapshot,
    save_step_confirmation,
    save_step_progress,
)

PROTOCOL_FILE = REPO_ROOT / "data" / "protocols" / "undergraduate_basic_protocols.json"

_lock = threading.RLock()
_protocol_store = None
_hazmat_store = None
_session: ProtocolSessionState | None = None
_progress = StepProgress()


def protocols() -> ProtocolStore:
    global _protocol_store
    with _lock:
        if _protocol_store is None:
            _protocol_store = ProtocolStore(PROTOCOL_FILE)
        return _protocol_store


def hazmat() -> HazmatStore:
    global _hazmat_store
    with _lock:
        if _hazmat_store is None:
            _hazmat_store = HazmatStore()
        return _hazmat_store


def session() -> ProtocolSessionState:
    """当前会话状态；首次访问时尝试从持久层恢复（刷新/重启不丢进度）。"""
    global _session
    with _lock:
        if _session is None:
            _session = _restore_session()
        return _session


def _restore_session() -> ProtocolSessionState:
    """从 SQLite 恢复：方案选择 + 当前步 + 各步记录进度。"""
    snapshot = load_session_snapshot()
    protocol_id = snapshot.get("protocol_id") if snapshot else None
    state = ProtocolSessionState.start(select_protocol(protocols(), protocol_id))
    _progress.reset()
    saved_step = snapshot.get("step_number") if snapshot else None
    if saved_step and state.selection.has_protocol:
        try:
            state = state.jump_to(int(saved_step))
        except Exception:
            pass  # 持久数据与方案不匹配时回退到第 1 步，不崩溃
    for step_number, info in load_step_progress().items():
        _progress.restore(step_number, info["recorded"], info["deviation"])
    for step_number in load_step_confirmations():
        _progress.confirm(step_number)
    return state


def _persist_snapshot() -> None:
    """把当前方案与步骤号写进 SQLite 快照。"""
    protocol_id = None
    step_number = None
    if _session is not None and _session.selection.has_protocol:
        protocol_id = _session.selection.protocol.protocol_id
        step_number = _session.step_number
    save_session_snapshot(protocol_id, step_number)


def start_session(selection) -> ProtocolSessionState:
    """selection 为 None 表示自由记录模式。换方案时进度清零并持久化。"""
    global _session
    with _lock:
        _session = ProtocolSessionState.start(select_protocol(protocols(), selection))
        _progress.reset()
        _persist_snapshot()
        clear_progress_rows()
        return _session


def reset_session() -> ProtocolSessionState:
    """开始全新的实验会话：退出旧方案并清空全部步骤进度。"""
    return start_session(None)


def record_step_fields(step_number: int, fields: dict, has_deviation: bool) -> None:
    """把一段口述的实体字段与偏差登记进当前步骤并落盘。"""
    with _lock:
        _progress.record(step_number, fields, has_deviation)
        if step_number is not None:
            save_step_progress(
                step_number,
                {k for k, v in (fields or {}).items() if v},
                bool(has_deviation),
            )


def step_status(step) -> str:
    """当前步骤的确定性状态：completed / error / waiting_user。"""
    with _lock:
        return _progress.status_for(step)


def _step_recorded_missing(step):
    """某一步的已记录字段与还缺字段（同一把锁内读取，保证一致性）。"""
    with _lock:
        return (
            _progress.recorded_fields(step.step_number),
            _progress.missing_fields(step),
        )


def step_progress_view(state) -> dict:
    """当前步骤的进度事实：状态 + 已记录字段 + 还缺的必测字段。

    供大模型在用户说"完成了"时核对真相用——模型只读事实，不自己猜。
    """
    step = state.current_step()
    if step is None:
        return {"status": "waiting_user", "recorded": [], "missing": []}
    with _lock:
        return {
            "status": _progress.status_for(step),
            "recorded": _progress.recorded_fields(step.step_number),
            "missing": _progress.missing_fields(step),
        }


def complete_step(step_number: int, manual: bool) -> dict:
    """完成当前步。

    - manual=True：用户手动确认（点"完成本步"按钮）→ 直接打勾并落盘，
      视为人类责任确认，不要求补齐口述数据；
    - manual=False：严格校验（必测字段记齐且无偏差才通过，否则拒绝）。
    两种路径都只能完成"当前步"，且状态变更都发生在后端状态机。
    """
    with _lock:
        state = session()
        if not state.selection.has_protocol:
            raise ValueError("尚未选择实验方案")
        if state.step_number != step_number:
            raise ValueError(f"只能完成当前步（第 {state.step_number} 步）")
        if manual:
            _progress.confirm(step_number)
            save_step_confirmation(step_number)
            return step_progress_view(state)
        progress = step_progress_view(state)
        if progress["status"] == "error":
            raise ValueError("本步存在偏差，需要先处理")
        if progress["status"] != "completed":
            raise ValueError("本步还没记齐，还缺：" + "、".join(progress["missing"]))
        return progress


def move(action: str, step_number: int | None = None) -> ProtocolSessionState:
    global _session
    with _lock:
        state = session()
        if action == "next":
            _session = state.next()
        elif action == "prev":
            _session = state.prev()
        elif action == "jump":
            _session = state.jump_to(int(step_number))
        else:
            raise ValueError("不支持的步骤操作：" + str(action))
        _persist_snapshot()
        return _session


def safety_for(step) -> list:
    """返回本步骤涉及试剂的安全信息；只突出高危项，避免警告过载。"""
    if step is None:
        return []
    store = hazmat()
    found = store.find_in_text(step.instruction, *step.terms)
    result = []
    for reagent in found:
        result.append({
            "name": reagent.name_zh,
            "cas": reagent.cas,
            "critical": reagent.is_critical,
            "codes": list(reagent.critical_codes),
            "statements": [s.text for s in reagent.critical_statements()],
            "source_url": reagent.source_url,
        })
    return result


def step_view(state: ProtocolSessionState) -> dict:
    """把会话状态转成前端可直接渲染的结构。"""
    step = state.current_step()
    protocol = state.selection.protocol
    if step is None or protocol is None:
        return {
            "mode": "free",
            "protocol": None,
            "step": None,
            "safety": [],
            "safety_note": hazmat().authority_note,
        }
    recorded, missing = _step_recorded_missing(step)
    return {
        "mode": "protocol",
        "protocol": {
            "id": protocol.protocol_id,
            "title": protocol.title,
            "source": protocol.source,
            "version": protocol.version,
            "total_steps": len(protocol.steps),
        },
        "step": {
            "number": step.step_number,
            "title": step.title,
            "instruction": step.instruction,
            "protocol_values": dict(step.protocol_values),
            "must_record": list(step.must_record),
            "hazard_note": step.hazard_note,
            "terms": list(step.terms),
            "status": step_status(step),
            "card_type": card_type_for(step_status(step), step.must_record),
            "recorded": recorded,
            "missing": missing,
            "substeps": [
                {"order": x.order, "text": x.text, "note": x.note}
                for x in step.substeps
            ],
        },
        "safety": safety_for(step),
        "safety_note": hazmat().authority_note,
    }


def evaluate(entities_dict: dict) -> dict:
    """按当前步骤做确定性判断：缺什么、有没有偏差。"""
    known = {f: entities_dict.get(f) for f in ExperimentEntities.__dataclass_fields__}
    entities = ExperimentEntities(**known)
    state = session()
    result = evaluate_segment(state, entities)
    return {
        "missing_fields": list(result.missing_fields),
        "follow_up_question": result.follow_up_question,
        "follow_up_required": result.follow_up_required,
        "deviations": [
            {
                "field": d.field_name,
                "protocol_value": d.protocol_value,
                "actual_value": d.actual_value,
            }
            for d in result.deviations
        ],
        "sourced_values": {
            name: {"value": v.value, "source": v.source.value}
            for name, v in result.sourced_values.items()
        },
    }


def evaluate_and_record(entities_dict: dict) -> dict:
    """原子地评估本段、累计步骤字段，再按累计进度生成追问。"""
    with _lock:
        result = evaluate(entities_dict)
        step = session().current_step()
        if step is None:
            return result
        record_step_fields(
            step.step_number, entities_dict, bool(result.get("deviations"))
        )
        missing = _progress.missing_fields(step)
        prompts = [
            step.field_prompts.get(name, f"请补充现场记录：{name}。")
            for name in missing
        ]
        result["missing_fields"] = missing
        result["follow_up_question"] = " ".join(prompts) if prompts else None
        result["follow_up_required"] = bool(missing)
        return result

def all_steps_view(state) -> dict:
    """当前方案的全部步骤概要，供状态机卡片栏渲染。"""
    view = step_view(state)
    protocol = state.selection.protocol
    if protocol is None:
        view["all_steps"] = []
        view["all_completed"] = False
        return view
    view["all_steps"] = [
        {
            "number": s.step_number,
            "title": s.title,
            "instruction": s.instruction,
            "protocol_values": dict(s.protocol_values),
            "must_record": list(s.must_record),
            "has_hazard": bool(s.hazard_note) or bool(safety_for(s)),
            "substep_count": len(s.substeps),
            "status": step_status(s),
            "card_type": card_type_for(step_status(s), s.must_record),
            "recorded": _step_recorded_missing(s)[0],
            "missing": _step_recorded_missing(s)[1],
        }
        for s in protocol.steps
    ]
    # "全部完成"由后端判定（前端只渲染）：所有步骤均为 completed。
    view["all_completed"] = bool(view["all_steps"]) and all(
        s["status"] == "completed" for s in view["all_steps"]
    )
    return view

def entity_field_names() -> list:
    """实体字段白名单，供编辑界面做下拉选择。"""
    from dataclasses import fields as dc_fields
    return [f.name for f in dc_fields(ExperimentEntities)]


def add_protocol(raw_protocol: dict) -> dict:
    """把一份新的实验方案写入方案库；先严格校验，再整份重写。"""
    import json

    from src.storage.protocol_store import ProtocolStore, ProtocolStoreError

    raw_library = json.loads(PROTOCOL_FILE.read_text(encoding="utf-8"))
    existing_ids = {item.get("protocol_id") for item in raw_library.get("protocols", [])}
    new_id = raw_protocol.get("protocol_id", "")
    if not new_id or new_id in existing_ids:
        raise ValueError("protocol_id 为空或已存在：" + str(new_id))

    # 用契约解析器先验证这份草稿；不通过绝不写入。
    try:
        ProtocolStore._parse_protocol(raw_protocol, index=len(raw_library["protocols"]) + 1)
    except ProtocolStoreError as error:
        raise ValueError(f"方案草稿不符合契约：{error}") from error

    raw_library["protocols"].append(raw_protocol)
    PROTOCOL_FILE.write_text(
        json.dumps(raw_library, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    global _protocol_store, _session
    with _lock:
        _protocol_store = None
        if _session is not None and _session.selection.protocol is None:
            pass
    return raw_protocol



def update_step(payload: dict) -> dict:
    """编辑一个大步骤并写回方案库。

    先在内存里构造新的 ProtocolStep，让契约校验拦下非法输入；
    通过后才整份重写 JSON，避免写出半成品文件。
    """
    import json
    from src.core.protocol import ProtocolStep, ProtocolSubStep

    protocol_id = payload["protocol_id"]
    step_number = int(payload["step_number"])

    raw = json.loads(PROTOCOL_FILE.read_text(encoding="utf-8"))
    target_protocol = None
    target_step = None
    for item in raw["protocols"]:
        if item["protocol_id"] == protocol_id:
            target_protocol = item
            for step in item["steps"]:
                if step["step_number"] == step_number:
                    target_step = step
            break
    if target_protocol is None or target_step is None:
        raise ValueError(f"找不到方案 {protocol_id} 的第 {step_number} 步")

    updated = dict(target_step)
    for key in ("title", "instruction", "hazard_note"):
        if payload.get(key) is not None:
            updated[key] = payload[key]
    if payload.get("protocol_values") is not None:
        updated["protocol_values"] = payload["protocol_values"]
    if payload.get("must_record") is not None:
        updated["must_record"] = list(payload["must_record"])
    if payload.get("field_prompts") is not None:
        updated["field_prompts"] = payload["field_prompts"]
    if payload.get("substeps") is not None:
        updated["substeps"] = [
            {"order": i, "text": x.get("text", ""), "note": x.get("note") or None}
            for i, x in enumerate(payload["substeps"], start=1)
            if str(x.get("text", "")).strip()
        ]

    # 先让契约校验；不通过直接抛，不落盘
    ProtocolStep(
        step_number=updated["step_number"],
        title=updated["title"],
        instruction=updated["instruction"],
        protocol_values=updated.get("protocol_values") or {},
        must_record=tuple(updated.get("must_record") or ()),
        terms=tuple(updated.get("terms") or ()),
        hazard_note=updated.get("hazard_note") or None,
        field_prompts=updated.get("field_prompts") or {},
        substeps=tuple(
            ProtocolSubStep(order=x["order"], text=x["text"], note=x.get("note"))
            for x in (updated.get("substeps") or [])
        ),
    )

    for index, step in enumerate(target_protocol["steps"]):
        if step["step_number"] == step_number:
            target_protocol["steps"][index] = updated
            break
    PROTOCOL_FILE.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    global _protocol_store, _session
    with _lock:
        _protocol_store = None       # 下次访问重新加载
        if _session is not None and _session.selection.protocol is not None:
            if _session.selection.protocol.protocol_id == protocol_id:
                current = _session.step_number
                _session = ProtocolSessionState.start(
                    select_protocol(protocols(), protocol_id)
                )
                _progress.reset()     # 方案步骤被编辑，进度按新方案重新计
                clear_progress_rows() # 落盘进度同步清零
                if current:
                    _session = _session.jump_to(current)
    return step_view(session())
