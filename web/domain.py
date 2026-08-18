# -*- coding: utf-8 -*-
"""网页层到领域层的桥：复用 src/ 里已验证的方案与安全逻辑。

web/ 以自身为工作目录启动，src/ 在仓库根目录，因此这里显式把根目录
加入模块搜索路径。除此之外不做任何业务判断，只负责装配与转译。
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.protocol_segment_evaluation import evaluate_segment  # noqa: E402
from src.core.protocol_selection import select_protocol  # noqa: E402
from src.core.protocol_session import ProtocolSessionState  # noqa: E402
from src.core.reagent_prep import ReagentPrep, ReagentPrepError  # noqa: E402
from src.llm.schemas import ExperimentEntities  # noqa: E402
from src.storage.hazmat_store import HazmatStore  # noqa: E402
from src.storage.protocol_store import ProtocolStore  # noqa: E402
from src.storage.reagent_prep_store import (  # noqa: E402
    REAGENT_PREP_FILE,
    ReagentPrepStore,
)

PROTOCOL_FILE = REPO_ROOT / "data" / "protocols" / "undergraduate_basic_protocols.json"
PREP_REQUIREMENTS_FILE = (
    REPO_ROOT / "data" / "protocols" / "prep_requirements.json"
)

_lock = threading.RLock()
_protocol_store = None
_hazmat_store = None
_reagent_prep_store = None
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


def reagent_preps() -> ReagentPrepStore:
    global _reagent_prep_store
    with _lock:
        if _reagent_prep_store is None:
            _reagent_prep_store = ReagentPrepStore(REAGENT_PREP_FILE)
        return _reagent_prep_store


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


def _bump_version(version: str) -> str:
    try:
        major, minor = str(version).split(".")
        return f"{major}.{int(minor) + 1}"
    except Exception:
        return str(version) + ".1"


def protocol_detail(protocol_id: str) -> dict:
    """一份方案的完整详情：步骤、准备材料、危险提示。"""

    protocol = protocols().get_by_id(protocol_id)
    if protocol is None:
        raise ValueError(f"找不到方案 {protocol_id}")
    return {
        "protocol": {
            "id": protocol.protocol_id,
            "title": protocol.title,
            "source": protocol.source,
            "version": protocol.version,
            "total_steps": len(protocol.steps),
        },
        "steps": [
            {
                "number": s.step_number,
                "title": s.title,
                "instruction": s.instruction,
                "protocol_values": dict(s.protocol_values),
                "must_record": list(s.must_record),
                "terms": list(s.terms),
                "hazard_note": s.hazard_note,
                "field_prompts": dict(s.field_prompts),
                "substeps": [
                    {"order": x.order, "text": x.text, "note": x.note}
                    for x in s.substeps
                ],
                "safety": safety_for(s),
            }
            for s in protocol.steps
        ],
        "prep_requirements": protocol_prep_requirements(protocol_id)["items"],
    }


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

    _sync_prep_requirements_for_protocol(raw_protocol)
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
    target_protocol["version"] = _bump_version(target_protocol.get("version", "1.0"))
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


def reagent_prep_view(prep: ReagentPrep) -> dict:
    """把一条试剂配置方案转成前端可渲染结构，并附带危险提示。"""

    store = hazmat()
    safety = []
    for name in prep.hazard_reagents:
        found = store.find(name)
        if found is not None:
            safety.append({
                "name": found.name_zh,
                "cas": found.cas,
                "critical": found.is_critical,
                "codes": list(found.critical_codes),
                "statements": [s.text for s in found.critical_statements()],
                "source_url": found.source_url,
            })
    return {
        "reagent_prep_id": prep.reagent_prep_id,
        "name_zh": prep.name_zh,
        "purpose": prep.purpose,
        "target_concentration": prep.target_concentration,
        "target_volume": prep.target_volume,
        "solvent": prep.solvent,
        "steps": list(prep.steps),
        "storage_condition": prep.storage_condition,
        "expiry": prep.expiry,
        "hazard_reagents": list(prep.hazard_reagents),
        "source": prep.source,
        "source_url": prep.source_url,
        "review_status": prep.review_status,
        "safety": safety,
        "safety_note": hazmat().authority_note,
    }


def add_reagent_prep(raw_prep: dict) -> dict:
    """校验并新增一条试剂配置；不通过绝不落盘。"""

    prep = ReagentPrep.from_dict(raw_prep)
    store = reagent_preps()
    store.add(prep)
    return reagent_prep_view(prep)


def add_reagent_preps(raw_preps: list) -> dict:
    """批量校验并新增；全部通过才写库。"""

    preps = [ReagentPrep.from_dict(item) for item in raw_preps]
    store = reagent_preps()
    store.add_many(preps)
    return {
        "added": len(preps),
        "ids": [p.reagent_prep_id for p in preps],
    }


def analyze_reagents(texts: list) -> dict:
    """识别文字中出现的危化品与试剂配置库条目。

    试剂名采用最长名优先，避免“硫酸铜”命中后“五水硫酸铜”重复。
    """

    store = hazmat()
    found = store.find_in_text(*texts)
    prep_store = reagent_preps()
    preps = [
        prep
        for prep in prep_store.list_all()
        if any(prep.name_zh in text for text in texts if isinstance(text, str))
    ]
    return {
        "hazmat": [
            {
                "name": r.name_zh,
                "cas": r.cas,
                "critical": r.is_critical,
                "codes": list(r.critical_codes),
                "statements": [s.text for s in r.critical_statements()],
            }
            for r in found
        ],
        "reagent_preps": [
            {
                "reagent_prep_id": p.reagent_prep_id,
                "name_zh": p.name_zh,
                "purpose": p.purpose,
            }
            for p in preps
        ],
    }


def protocol_prep_requirements(protocol_id: str | None) -> dict:
    """读取方案需要的试剂配置列表；找不到方案返回空。"""

    if protocol_id is None:
        return {"protocol_id": None, "items": []}
    raw = json.loads(PREP_REQUIREMENTS_FILE.read_text(encoding="utf-8"))
    ids = raw.get("requirements", {}).get(protocol_id, [])
    store = reagent_preps()
    items = []
    for prep_id in ids:
        prep = store.get_by_id(prep_id)
        if prep is not None:
            items.append(reagent_prep_view(prep))
    return {"protocol_id": protocol_id, "items": items}


def _protocol_texts(raw_protocol: dict) -> list:
    """提取一份方案中可用于试剂识别的文本。"""

    texts = [raw_protocol.get("title", "")]
    for step in raw_protocol.get("steps", []):
        texts.append(step.get("instruction", ""))
        texts.append(step.get("title", ""))
        texts.extend(step.get("terms", []) or [])
    return [str(t) for t in texts if str(t).strip()]


def _sync_prep_requirements_for_protocol(raw_protocol: dict) -> None:
    """把方案中命中的试剂配置自动写入 prep_requirements 映射。"""

    protocol_id = raw_protocol.get("protocol_id", "")
    if not protocol_id:
        return
    texts = _protocol_texts(raw_protocol)
    analysis = analyze_reagents(texts)
    prep_ids = [item["reagent_prep_id"] for item in analysis["reagent_preps"]]

    raw = json.loads(PREP_REQUIREMENTS_FILE.read_text(encoding="utf-8"))
    requirements = raw.setdefault("requirements", {})
    requirements[protocol_id] = prep_ids
    PREP_REQUIREMENTS_FILE.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def add_protocol_step(payload: dict) -> dict:
    """在方案中追加/插入一个大步骤，严格校验后落盘。"""

    from src.core.protocol import ProtocolStep, ProtocolSubStep

    protocol_id = payload["protocol_id"]
    after = payload.get("after_step_number")
    raw = json.loads(PROTOCOL_FILE.read_text(encoding="utf-8"))
    target_protocol = None
    for item in raw["protocols"]:
        if item["protocol_id"] == protocol_id:
            target_protocol = item
            break
    if target_protocol is None:
        raise ValueError(f"找不到方案 {protocol_id}")

    step_data = {
        "step_number": 0,
        "title": payload.get("title", ""),
        "instruction": payload.get("instruction", ""),
        "protocol_values": payload.get("protocol_values") or {},
        "must_record": list(payload.get("must_record") or ()),
        "terms": list(payload.get("terms") or ()),
        "hazard_note": payload.get("hazard_note") or None,
        "field_prompts": payload.get("field_prompts") or {},
        "substeps": [
            {"order": i, "text": x.get("text", ""), "note": x.get("note") or None}
            for i, x in enumerate(payload.get("substeps") or [], start=1)
            if str(x.get("text", "")).strip()
        ],
    }

    ProtocolStep(
        step_number=1,
        title=step_data["title"],
        instruction=step_data["instruction"],
        protocol_values=step_data["protocol_values"],
        must_record=tuple(step_data["must_record"]),
        terms=tuple(step_data["terms"]),
        hazard_note=step_data["hazard_note"],
        field_prompts=step_data["field_prompts"],
        substeps=tuple(
            ProtocolSubStep(order=x["order"], text=x["text"], note=x.get("note"))
            for x in step_data["substeps"]
        ),
    )

    steps = target_protocol["steps"]
    if after is None:
        insert_at = len(steps)
    else:
        after = int(after)
        insert_at = after
        if insert_at < 0 or insert_at > len(steps):
            raise ValueError("after_step_number 超出范围。")
    steps.insert(insert_at, step_data)
    for index, step in enumerate(steps, start=1):
        step["step_number"] = index
    target_protocol["version"] = _bump_version(target_protocol.get("version", "1.0"))
    PROTOCOL_FILE.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    global _protocol_store, _session
    with _lock:
        _protocol_store = None
        if _session is not None and _session.selection.protocol is not None:
            if _session.selection.protocol.protocol_id == protocol_id:
                current = _session.step_number
                _session = ProtocolSessionState.start(
                    select_protocol(protocols(), protocol_id)
                )
                if current:
                    _session = _session.jump_to(current)
    return step_view(session())


def delete_protocol_step(protocol_id: str, step_number: int) -> dict:
    """删除方案中的一个大步骤并重新编号，严格校验后落盘。"""

    raw = json.loads(PROTOCOL_FILE.read_text(encoding="utf-8"))
    target_protocol = None
    for item in raw["protocols"]:
        if item["protocol_id"] == protocol_id:
            target_protocol = item
            break
    if target_protocol is None:
        raise ValueError(f"找不到方案 {protocol_id}")
    if len(target_protocol["steps"]) <= 1:
        raise ValueError("方案至少保留一个步骤。")
    step_number = int(step_number)
    if step_number < 1 or step_number > len(target_protocol["steps"]):
        raise ValueError("步骤号超出范围。")
    del target_protocol["steps"][step_number - 1]
    for index, step in enumerate(target_protocol["steps"], start=1):
        step["step_number"] = index
    target_protocol["version"] = _bump_version(target_protocol.get("version", "1.0"))
    PROTOCOL_FILE.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    global _protocol_store, _session
    with _lock:
        _protocol_store = None
        if _session is not None and _session.selection.protocol is not None:
            if _session.selection.protocol.protocol_id == protocol_id:
                current = _session.step_number
                _session = ProtocolSessionState.start(
                    select_protocol(protocols(), protocol_id)
                )
                if current:
                    _session = _session.jump_to(current)
    return step_view(session())
