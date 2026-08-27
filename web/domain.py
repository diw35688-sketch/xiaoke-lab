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
from src.core.protocol_deviations import detect_protocol_deviations  # noqa: E402
from src.core.protocol_selection import select_protocol  # noqa: E402
from src.core.protocol_session import ProtocolSessionState  # noqa: E402
from src.llm.schemas import ExperimentEntities  # noqa: E402
from src.storage.hazmat_store import HazmatStore  # noqa: E402
from src.storage.protocol_store import ProtocolStore  # noqa: E402

PROTOCOL_FILE = REPO_ROOT / "data" / "protocols" / "undergraduate_basic_protocols.json"

_lock = threading.RLock()
_protocol_store = None
_hazmat_store = None
_session: ProtocolSessionState | None = None


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
    """当前会话状态；未选择方案时为自由记录模式。"""
    global _session
    with _lock:
        if _session is None:
            _session = ProtocolSessionState.start(select_protocol(protocols(), None))
        return _session


def start_session(selection) -> ProtocolSessionState:
    """selection 为 None 表示自由记录模式。"""
    global _session
    with _lock:
        _session = ProtocolSessionState.start(select_protocol(protocols(), selection))
        return _session


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
            "value_aliases": {
                name: list(values) for name, values in step.value_aliases.items()
            },
            "must_record": list(step.must_record),
            "hazard_note": step.hazard_note,
            "terms": list(step.terms),
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
    return evaluate_for_state(session(), entities_dict)


def evaluate_for_state(state: ProtocolSessionState, entities_dict: dict) -> dict:
    """按调用方捕获的同一方案状态快照评价，避免步骤在处理中漂移。"""
    known = {f: entities_dict.get(f) for f in ExperimentEntities.__dataclass_fields__}
    entities = ExperimentEntities(**known)
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


def project_record_evaluation(record: dict) -> dict:
    """Re-evaluate ledger display with the exact current protocol id/version/step."""

    step_snapshot = record.get("step") or {}
    protocol_snapshot = step_snapshot.get("protocol") or {}
    recorded_step = step_snapshot.get("step") or {}
    protocol_id = protocol_snapshot.get("id")
    protocol_version = protocol_snapshot.get("version")
    step_number = recorded_step.get("number")
    if not protocol_id or not protocol_version or not step_number:
        return record
    protocol = protocols().get(str(protocol_id))
    if protocol is None or protocol.version != str(protocol_version):
        return record
    step_index = int(step_number) - 1
    if step_index < 0 or step_index >= len(protocol.steps):
        return record
    entities_dict = record.get("entities") or {}
    known = {
        name: entities_dict.get(name)
        for name in ExperimentEntities.__dataclass_fields__
    }
    deviations = detect_protocol_deviations(
        protocol.steps[step_index], ExperimentEntities(**known)
    )
    projected = dict(record)
    stored_evaluation = dict(record.get("evaluation") or {})
    evaluation = dict(stored_evaluation)
    evaluation["stored_deviations"] = stored_evaluation.get("deviations") or []
    evaluation["deviations"] = [{
        "field": item.field_name,
        "protocol_value": item.protocol_value,
        "actual_value": item.actual_value,
    } for item in deviations]
    evaluation["deviation_rule_version"] = 2
    projected["evaluation"] = evaluation
    return projected

def all_steps_view(state) -> dict:
    """当前方案的全部步骤概要，供状态机卡片栏渲染。"""
    view = step_view(state)
    protocol = state.selection.protocol
    if protocol is None:
        view["all_steps"] = []
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
        }
        for s in protocol.steps
    ]
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
    if payload.get("value_aliases") is not None:
        updated["value_aliases"] = payload["value_aliases"]
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
        value_aliases={
            key: tuple(values)
            for key, values in (updated.get("value_aliases") or {}).items()
        },
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
                if current:
                    _session = _session.jump_to(current)
    return step_view(session())
