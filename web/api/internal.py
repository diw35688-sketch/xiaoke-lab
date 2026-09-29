# -*- coding: utf-8 -*-
"""本机内部任务接口。

QwenAudio 自定义后台 Adapter（Node 侧）通过该接口把语音里需要
“实验助手干活”的请求转回本项目：
  instruction（自然语言任务）
      → 走原有 Chat/Turn 生产链路
      → 返回最终文字结果
供 QwenAudio 实时语音前台自然播报。

安全边界：只允许本机回环访问，防止公网隧道把内部任务口暴露出去。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/internal", tags=["内部"])


class InternalLabTaskRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=10000)
    conversation_id: str | None = Field(default=None, max_length=64)
    lab_session_id: str | None = Field(default=None, max_length=128)


class InternalConversationRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=64)
    lab_session_id: str | None = Field(default=None, max_length=128)


class VoiceClientLogPayload(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class VoiceTranscriptPayload(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=64)
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=10000)
    turn_id: str | None = Field(default=None, max_length=128)
    lab_session_id: str | None = Field(default=None, max_length=128)


class VoiceToolCallPayload(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=64)
    tool_name: str = Field(min_length=1, max_length=256)
    arguments: dict | None = None
    status: str = Field(default="pending", pattern="^(pending|done|error)$")
    result_text: str | None = Field(default=None, max_length=2000)


def _allowed(request: Request) -> bool:
    host = request.client.host if request.client else ""
    return host in ("127.0.0.1", "::1", "localhost")


def _read_lab_context() -> tuple[str, str]:
    """Read the QwenAudio current conversation/lab-session files if present."""
    conversation_id = ""
    lab_session_id = ""
    try:
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent.parent / "realtime"
        conversation_id = (root / "current-conversation-id.txt").read_text(
            encoding="utf-8"
        ).strip()
        lab_session_id = (root / "current-lab-session-id.txt").read_text(
            encoding="utf-8"
        ).strip()
    except Exception:
        pass
    return conversation_id, lab_session_id


def _write_qwen_conversation(conversation_id: str, lab_session_id: str | None = None) -> None:
    """Persist the current QwenAudio conversation/lab-session files."""
    try:
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent.parent / "realtime"
        root.mkdir(parents=True, exist_ok=True)
        if conversation_id:
            (root / "current-conversation-id.txt").write_text(
                str(conversation_id).strip(), encoding="utf-8"
            )
        if lab_session_id:
            (root / "current-lab-session-id.txt").write_text(
                str(lab_session_id).strip(), encoding="utf-8"
            )
    except OSError:
        pass


def _sync_global_from_lab_state(
    lab_session_id: str,
    conversation_id: str | None = None,
) -> None:
    """Mirror the latest per-conversation experiment state onto the global domain.

    The left “实验进行中/步骤卡” reads /protocols/session/steps, which is backed by
    domain.session().  Voice writes go through the per-conversation TurnStore, so until
    this mirror runs the UI can look stale.
    """
    if not lab_session_id:
        return
    try:
        import domain as domain_module
        from database.lab_record_store import set_current_session
        from database.turn_store import TurnStore

        # 让记录层与当前语音会话对齐（否则记录会写到旧 session、缺 conversation_id）
        set_current_session(lab_session_id, conversation_id)

        store = TurnStore()
        state = None
        if conversation_id:
            state = store.load_experiment_state(conversation_id, lab_session_id)
            if not (state.get("protocol_step_facts") or {}):
                state = store.load_latest_experiment_state_for_lab(lab_session_id)
        else:
            state = store.load_latest_experiment_state_for_lab(lab_session_id)
        if not state:
            return
        facts = state.get("protocol_step_facts") or {}
        if not facts.get("protocol_id"):
            return
        current = int(facts.get("current_step_number") or 1)
        domain_module.move("jump", current)
        for step_number, step_fact in (facts.get("steps") or {}).items():
            values = {}
            for field_name, observed in (step_fact.get("values") or {}).items():
                value = observed.get("value") if isinstance(observed, dict) else observed
                if value:
                    values[field_name] = value
            if values:
                domain_module.record_step_fields(int(step_number), values, False)
    except Exception:
        # 镜像只提升显示一致性；失败不应影响语音流程或会话文件。
        pass


def _run_unified_experiment_turn(
    instruction: str,
    conversation_id: str,
    lab_session_id: str,
) -> str:
    """Run one real experiment-mode Turn through the same processor as the UI.

    This is NOT the legacy free-chat path.  It uses TurnInput with
    InteractionMode.EXPERIMENT, so records are actually written and step
    navigation is actually persisted.
    """
    from api.chat import _assistant_text
    from api.turn import turn_application_service
    from database.turn_store import TurnStore
    from src.core.conversation_turn import ExperimentContext, InputSource, InteractionMode
    from src.core.turn_input import TurnInput

    request_id = f"voice-exp-{uuid.uuid4().hex}"
    turn_id = f"turn-{request_id}"
    store = TurnStore()
    stored = store.load_experiment_state(conversation_id, lab_session_id)
    facts = stored.get("protocol_step_facts") or {}
    # 新聊天会话可能还没有同 lab_session 的状态行；继承同一个实验最近的状态，
    # 避免语音在“新会话”里变成自由模式而无法记到当前实验。
    if not facts:
        fallback = store.load_latest_experiment_state_for_lab(lab_session_id)
        if fallback and (fallback.get("protocol_step_facts") or {}):
            stored = fallback
            facts = stored.get("protocol_step_facts") or {}
    context = (
        ExperimentContext.PROTOCOL
        if facts.get("protocol_id")
        else ExperimentContext.FREE
    )
    turn = TurnInput(
        conversation_id,
        request_id,
        turn_id,
        lab_session_id,
        InteractionMode.EXPERIMENT,
        context,
        1,
        InputSource.TEXT,
        instruction.strip(),
        None,
    )
    completed = turn_application_service.submit(turn).future.result()
    answer = _assistant_text(completed.result)
    if not answer:
        raise RuntimeError("实验模式没有返回可播报文字。")

    # 把“按会话保存”的实验状态同步回全局 domain（左侧实验进行中/步骤卡读取的源），
    # 否则语音里已经翻页，左侧还停留在第一步。
    try:
        import domain as domain_module
        updated_facts = (store.load_experiment_state(
            conversation_id, lab_session_id
        ).get("protocol_step_facts") or {})
        old_current = int(facts.get("current_step_number") or 1)
        new_current = int(updated_facts.get("current_step_number") or old_current)
        if new_current != old_current:
            domain_module.move("jump", new_current)
        for step_number, step_fact in (updated_facts.get("steps") or {}).items():
            raw_values = step_fact.get("values") or {}
            values = {}
            for field_name, observed in raw_values.items():
                value = observed.get("value") if isinstance(observed, dict) else observed
                if value:
                    values[field_name] = value
            if values:
                domain_module.record_step_fields(int(step_number), values, False)
    except Exception:
        # 全局镜像只影响左侧显示，不影响语音记录本身已成功落库。
        pass
    return answer


@router.post("/lab-voice-task")
def lab_voice_task(payload: InternalLabTaskRequest, request: Request):
    if not _allowed(request):
        raise HTTPException(status_code=403, detail="仅允许本机内部调用。")

    from api.chat import ChatRequest, _assistant_text, _submit_legacy_chat
    from database import user_store
    from database.crud import conversation_exists, create_conversation

    instruction = payload.instruction.strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="instruction 不能为空。")

    users = user_store.list_users()
    if not users:
        raise HTTPException(status_code=400, detail="还没有账号，请先初始化系统。")
    user_id = users[0]["id"]

    # 语音里的实验指令必须绑定当前实验会话；优先用 Node Adapter 显式传入，
    # 否则回退到 realtime 里的 current-conversation/lab-session 文件。
    file_conversation_id, file_lab_session_id = _read_lab_context()
    conversation_id = payload.conversation_id or file_conversation_id
    if not conversation_id or not conversation_exists(conversation_id, user_id):
        conversation_id = create_conversation(
            user_id,
            title="实时语音对话",
            conversation_id=conversation_id or None,
        )
    lab_session_id = (
        (payload.lab_session_id or "").strip()
        or file_lab_session_id
    )

    try:
        import domain as domain_module

        # 关键：切换实验/选择方案这类指令必须走真正的实验工具通道，
        # 不能走自由聊天通道（自由聊天不会执行 select_protocol）。
        switch_keywords = ("切换", "切换到", "选择方案", "开始实验", "开始走", "开始做", "做这个实验", "做这个方案", "转到", "打开这个实验")
        is_switch_request = any(k in instruction for k in switch_keywords) or (
            "开始" in instruction and ("实验" in instruction or "方案" in instruction)
        )
        if lab_session_id and is_switch_request:
            # 确定性优先：能匹配到本地方案就立刻切换，不交给模型猜。
            try:
                import difflib

                protocols = domain_module.protocols().list_all()
                query = str(instruction)
                for prefix in ("切换实验到", "切换到", "切换实验", "切换到实验", "选择方案", "选择", "开始实验", "开始", "做这个实验", "做这个方案"):
                    query = query.replace(prefix, "", 1)
                query = query.strip(" ，。!！?？:：、")
                if query:
                    def similarity(p):
                        title = str(getattr(p, "title", "") or "")
                        return difflib.SequenceMatcher(None, query, title).ratio()
                    best = max(protocols, key=similarity) if protocols else None
                    if best is not None:
                        ratio = similarity(best)
                        if ratio >= 0.25:
                            from agent.core import _select_protocol_for_session
                            selected_view = _select_protocol_for_session(
                                conversation_id, lab_session_id, best.protocol_id
                            )
                            if selected_view.get("mode") == "protocol":
                                protocol = selected_view["protocol"]
                                step = selected_view.get("step") or {}
                                answer = (
                                    f"已切换到实验方案：{protocol['title']}，"
                                    f"当前第 {step.get('number')} 步：{step.get('title')}。"
                                )
                                return {
                                    "answer": answer,
                                    "conversation_id": conversation_id,
                                    "ok": True,
                                }
            except Exception:  # noqa: BLE001
                pass
            try:
                from agent.core import run_agent
                answer = run_agent(
                    [{"role": "user", "content": instruction}],
                    conversation_id,
                )
                if answer:
                    return {
                        "answer": answer,
                        "conversation_id": conversation_id,
                        "ok": True,
                    }
            except Exception as error:  # noqa: BLE001
                # 实验工具失败时继续降级到后台，不让指令直接挂掉。
                import time
                time.sleep(0.2)

        # 非“切换方案”的语音指令：只要知道 lab_session，就走实验模式，
        # 让它真正写记录/推进步骤；绝不再走自由聊天假装干活。
        if lab_session_id:
            try:
                answer = _run_unified_experiment_turn(
                    instruction, conversation_id, lab_session_id
                )
                return {
                    "answer": answer,
                    "conversation_id": conversation_id,
                    "ok": True,
                }
            except Exception as error:  # noqa: BLE001
                return {
                    "answer": (
                        "后台实验处理没有完成，我先不假装已经记录或翻页。"
                        "你可以稍后重试，或直接到实验本查看。"
                    ),
                    "conversation_id": conversation_id or "",
                    "ok": False,
                    "detail": str(error),
                }

        # 完全没有 lab_session 时才退回旧自由聊天（例如未开始任何实验的闲聊）。
        def submit_assistant(text: str):
            completed, cid = _submit_legacy_chat(
                ChatRequest(message=text, conversation_id=conversation_id)
            )
            return _assistant_text(completed.result), cid

        from agent_orchestrator import create_default_orchestrator
        planner, executor, reflector = create_default_orchestrator(
            domain=domain_module, submit_assistant=submit_assistant
        )
        plan = planner.plan(instruction)
        if plan.kind == "direct":
            result = reflector.run(plan, instruction, executor)
            if result.ok:
                return {
                    "answer": result.answer,
                    "conversation_id": conversation_id,
                    "ok": True,
                }
            plan = planner.plan("")

        completed = None
        last_error = None
        for attempt in range(2):
            try:
                completed, conversation_id = _submit_legacy_chat(
                    ChatRequest(message=instruction, conversation_id=conversation_id)
                )
                answer = _assistant_text(completed.result)
                return {
                    "answer": answer,
                    "conversation_id": conversation_id,
                    "ok": True,
                }
            except Exception as error:  # noqa: BLE001
                last_error = error
                if attempt == 0:
                    import time
                    time.sleep(0.5)
        return {
            "answer": "后台处理暂时不可用，我先把这句话记下；你可以稍后让我重试，或直接到实验本查看。",
            "conversation_id": conversation_id or "",
            "ok": False,
            "detail": str(last_error) if last_error else "",
        }
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"实验助手后台处理失败：{error}") from error


@router.get("/mcp/protocols")
def mcp_protocols(request: Request):
    if not _allowed(request):
        raise HTTPException(status_code=403, detail="仅允许本机内部调用。")
    import domain
    items = []
    for protocol in domain.protocols().list_all():
        items.append({
            "id": protocol.protocol_id,
            "title": protocol.title,
            "source": protocol.source,
            "version": protocol.version,
            "total_steps": len(protocol.steps),
        })
    return {"items": items}


@router.get("/mcp/current-experiment")
def mcp_current_experiment(request: Request):
    if not _allowed(request):
        raise HTTPException(status_code=403, detail="仅允许本机内部调用。")
    import domain
    selected = domain.session()
    data = domain.all_steps_view(selected)
    # 语音助手拿到的当前实验只用于“告诉用户现在在哪、下一步是什么”；
    # 绝不把任何字段标成“必测/还缺”，避免它追问用户补录。
    if data.get("mode") == "protocol" and data.get("step"):
        data["step"]["must_record"] = []
        data["step"]["missing"] = []
        data["step"]["card_type"] = "confirm"
    for item in data.get("all_steps") or []:
        item["must_record"] = []
        item["missing"] = []
        item["card_type"] = "confirm"
    return data


class ToolExecuteRequest(BaseModel):
    tool_name: str = Field(min_length=1, max_length=256)
    arguments: dict | None = None
    conversation_id: str | None = Field(default=None, max_length=64)
    lab_session_id: str | None = Field(default=None, max_length=128)


@router.get("/tool-definitions")
def tool_definitions(request: Request):
    """导出全部工具定义，供千问 MCP 启动时自动注册。

    返回 MCP 兼容格式：每个工具含 name / description / parameters。
    千问和 DeepSeek 看到完全相同的工具列表，行为一致。
    """
    if not _allowed(request):
        raise HTTPException(status_code=403, detail="仅允许本机内部调用。")
    from agent.core import TOOLS
    from tool_router import _EXCLUDED
    tools = []
    for entry in TOOLS:
        fn = entry.get("function", {})
        name = fn.get("name", "")
        # 过滤开发者工具和内部机制工具
        if name in _EXCLUDED or name == "activate_skill":
            continue
        tools.append({
            "name": name,
            "description": fn.get("description", ""),
            "parameters": fn.get("parameters", {"type": "object", "properties": {}}),
        })
    return {"tools": tools}


@router.post("/tool-execute")
def tool_execute(payload: ToolExecuteRequest, request: Request):
    """通用工具执行端点：千问 MCP 通过此端点执行任意已注册工具。

    与 stream_agent 走完全相同的执行路径（run_tool），保证行为一致。
    """
    if not _allowed(request):
        raise HTTPException(status_code=403, detail="仅允许本机内部调用。")
    from agent.core import run_tool
    from database import user_store
    from database.crud import conversation_exists, create_conversation

    users = user_store.list_users()
    if not users:
        raise HTTPException(status_code=400, detail="还没有账号。")
    user_id = users[0]["id"]

    conversation_id = payload.conversation_id or ""
    if not conversation_id or not conversation_exists(conversation_id, user_id):
        conversation_id = create_conversation(
            user_id, title="实时语音对话", conversation_id=conversation_id or None,
        )

    # 同步 lab_session 到 domain，确保工具看到正确的实验上下文
    lab_session_id = (payload.lab_session_id or "").strip()
    if lab_session_id:
        _sync_global_from_lab_state(lab_session_id, conversation_id)

    arguments = payload.arguments or {}
    try:
        result = run_tool(payload.tool_name, arguments, conversation_id)
        return {"ok": True, "result": result, "conversation_id": conversation_id}
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"{type(error).__name__}: {error}",
            "conversation_id": conversation_id,
        }


@router.post("/voice-client-log")
def voice_client_log(payload: VoiceClientLogPayload, request: Request):
    """浏览器端实时语音诊断日志（仅本机）。"""
    if not _allowed(request):
        raise HTTPException(status_code=403, detail="仅允许本机内部调用。")
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent.parent / "logs" / "voice_client.log"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.utcnow().isoformat()}] {payload.message}\n")
    except OSError as error:
        raise HTTPException(status_code=500, detail=f"写日志失败：{error}") from error
    return {"ok": True}


@router.post("/voice-transcript")
def voice_transcript(payload: VoiceTranscriptPayload, request: Request):
    """把实时语音的最终文本写入聊天会话（去重，避免与后台任务重复）。"""
    if not _allowed(request):
        raise HTTPException(status_code=403, detail="仅允许本机内部调用。")

    from database import user_store
    from database.crud import (
        add_message,
        conversation_exists,
        create_conversation,
        get_messages,
    )

    users = user_store.list_users()
    if not users:
        raise HTTPException(status_code=400, detail="还没有账号。")
    user_id = users[0]["id"]

    conversation_id = payload.conversation_id
    if not conversation_id or not conversation_exists(conversation_id, user_id):
        conversation_id = create_conversation(
            user_id,
            title="实时语音对话",
            conversation_id=conversation_id or None,
        )

    # 只要语音里出现了任何一条消息，就把“当前语音会话”立刻指向这个会话，
    # 避免 MCP 工具继续写到旧的 current-conversation-id.txt。
    _write_qwen_conversation(conversation_id, getattr(payload, "lab_session_id", None))
    _sync_global_from_lab_state(
        getattr(payload, "lab_session_id", None) or "",
        conversation_id,
    )

    content = payload.content.strip()
    if not content:
        return {"ok": True, "conversation_id": conversation_id}

    # 简单去重：最近几条若已有同role同内容，则视为后台已经写过了。
    try:
        recent = get_messages(conversation_id, limit=6)
        for item in recent:
            if item.get("role") == payload.role and str(item.get("content") or "").strip() == content:
                return {"ok": True, "conversation_id": conversation_id, "deduplicated": True}
    except Exception:
        pass

    add_message(conversation_id, payload.role, content)
    # 同时落一条轻量 Turn，让 /turn/history 能展示实时语音消息，
    # 避免右侧聊天一段时间后不再刷新。
    try:
        from database.turn_store import TurnStore
        TurnStore().append_voice_transcript(
            conversation_id=conversation_id,
            role=payload.role,
            content=content,
            lab_session_id=getattr(payload, "lab_session_id", None),
            turn_id=payload.turn_id or None,
        )
    except Exception:
        # 不影响文本消息落库；Turn 历史补写失败时下轮仍可重试。
        pass
    return {"ok": True, "conversation_id": conversation_id}


@router.post("/voice-tool-call")
def voice_tool_call(payload: VoiceToolCallPayload, request: Request):
    """把实时语音的工具调用记录成右侧聊天里的 tool_card。"""
    if not _allowed(request):
        raise HTTPException(status_code=403, detail="仅允许本机内部调用。")
    try:
        from database.turn_store import TurnStore
        result = TurnStore().append_voice_tool_call(
            conversation_id=payload.conversation_id,
            tool_name=payload.tool_name,
            arguments=payload.arguments,
            status=payload.status,
            result_text=payload.result_text or "",
        )
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"记录工具调用失败：{error}") from error
    return result


@router.post("/qwen-conversation")
def set_qwen_conversation(payload: InternalConversationRequest, request: Request):
    """记录实时语音应该进入哪个聊天会话（当前前端 localStorage 里的会话号）。"""
    if not _allowed(request):
        raise HTTPException(status_code=403, detail="仅允许本机内部调用。")

    from pathlib import Path

    root = Path(__file__).resolve().parent.parent.parent / "realtime"
    path = root / "current-conversation-id.txt"
    try:
        root.mkdir(parents=True, exist_ok=True)
        path.write_text(str(payload.conversation_id).strip(), encoding="utf-8")
        if payload.lab_session_id:
            (root / "current-lab-session-id.txt").write_text(
                str(payload.lab_session_id).strip(), encoding="utf-8"
            )
    except OSError as error:
        raise HTTPException(status_code=500, detail=f"写入会话号失败：{error}") from error
    _sync_global_from_lab_state(payload.lab_session_id or "", payload.conversation_id)
    return {"ok": True, "conversation_id": payload.conversation_id}

