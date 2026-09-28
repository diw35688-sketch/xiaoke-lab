"""Business processors used behind the unified Web Turn boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

import json

import domain
import settings_store
from agent.core import (
    run_storage_agent,
    run_template_agent,
    stream_agent,
    EXPERIMENT_RECORD_POLICY,
)
from database.crud import get_recent_messages
from database.turn_store import TurnStore
from src.core.conversation_turn import (
    BlockType,
    ConversationBlock,
    ConversationTurn,
    ExperimentContext,
)
from src.core.answer_fallback import decide_natural_short_answer
from src.core.clarification_acceptance import (
    ClarificationAction,
    ClarificationActionType,
    ClarificationMutationPermission,
)
from src.core.experiment_acceptance import ExperimentAcceptanceKind
from src.core.experiment_tool_command import ExperimentToolCommandParser
from src.core.protocol_completion_policy import (
    ProtocolStepFactState,
    resolve_protocol_completion,
)
from src.core.protocol_execution_state import (
    ProtocolExecutionState,
    ProtocolStepProgressStatus,
)
from src.core.protocol_navigation import decide_protocol_move
from src.core.presentation_delivery import VoiceDeliveryItem
from src.core.presentation_intent import MessageKind, MessagePriority
from src.core.reply_coordinator import FIELD_LABELS, ReplyCoordinator
from src.core.rule_entity_extraction import extract_entities
from src.core.session_context import SessionContext
from src.core.turn_input import TurnInput
from src.core.turn_timing import TurnTimingRecorder


@dataclass(frozen=True)
class PreparedTurn:
    turn: ConversationTurn
    business: Mapping[str, object]
    messages: tuple[Mapping[str, object], ...] = ()
    lab_record: Mapping[str, object] | None = None
    experiment_events: tuple[Mapping[str, object], ...] = ()
    session_state: Mapping[str, object] | None = None
    voice_items: tuple[VoiceDeliveryItem, ...] = ()


class TurnProcessor(Protocol):
    def prepare(
        self, turn: TurnInput, timing: TurnTimingRecorder
    ) -> PreparedTurn: ...


def _text_block(turn: TurnInput, suffix: str, text: str, *, assistant: bool):
    return ConversationBlock(
        block_id=f"{turn.turn_id}:{suffix}",
        type=BlockType.ASSISTANT_TEXT if assistant else BlockType.USER_TEXT,
        payload={"text": text},
    )


def _voice_item(turn: TurnInput, text: str, source_block_id: str, kind: MessageKind):
    priority = (
        MessagePriority.SUMMARY
        if kind == MessageKind.SESSION_CLOSING_SUMMARY
        else MessagePriority.ACTIVE_QUESTION
    )
    return VoiceDeliveryItem(
        intent_id=f"{turn.turn_id}:voice",
        kind=kind,
        priority=priority,
        voice_text=text,
        source_block_id=source_block_id,
        max_chars=max(80, len(text)),
        speech_rate=settings_store.current().tts_speed,
    )


def _tool_card_first_lines(tool_cards: Mapping[str, dict]) -> str | None:
    """统一输出规则：只读/搜索工具时，正文取卡片第一行，避免模型长篇复述。

    不是按功能路由；只要本轮全是只读/搜索工具就生效。
    如果包含执行/写入工具，返回 None，保留模型自然回复。
    """
    if not tool_cards:
        return None
    kinds = {str(card.get("kind") or "") for card in tool_cards.values()}
    if not kinds <= {"read", "search"}:
        return None
    parts = []
    for card in tool_cards.values():
        lines = card.get("lines") or []
        first = ""
        for line in lines:
            if str(line or "").strip():
                first = str(line).strip().rstrip("。")
                break
        if first:
            if len(first) > 120:
                first = first[:120] + "…"
            parts.append(first)
    if not parts:
        titles = [str(c.get("title") or "") for c in tool_cards.values()]
        parts = [t for t in titles if t]
    if not parts:
        return None
    return "；".join(parts) + "。完整内容见工具卡片。"


class TemplateProcessor:
    """制作模板：按模板规范对话，可调用文档解析/保存工具生成规范模板。"""

    def __init__(self, *, generate=run_template_agent, history=get_recent_messages) -> None:
        self._generate = generate
        self._history = history

    def prepare(self, turn: TurnInput, timing: TurnTimingRecorder) -> PreparedTurn:
        history = list(self._history(turn.conversation_id))
        history.append({"role": "user", "content": turn.raw_text})
        timing.mark("understanding_started")
        timing.mark("llm_started")
        answer = self._generate(history, turn.conversation_id)
        timing.mark("llm_completed")
        timing.mark("understanding_completed")
        user = _text_block(turn, "user", turn.raw_text, assistant=False)
        assistant = _text_block(turn, "spoken", answer or "没有生成模板内容，请补充模板名称/用途/步骤后重试。", assistant=True)
        voice = ConversationBlock(
            block_id=f"{turn.turn_id}:voice",
            type=BlockType.VOICE,
            payload={},
            source_block_id=assistant.block_id,
            intent_id=f"{turn.turn_id}:voice",
            priority=MessagePriority.REVIEW,
        )
        conversation_turn = ConversationTurn(
            turn.conversation_id, turn.request_id, turn.turn_id,
            turn.interaction_mode, turn.experiment_context, turn.mode_version,
            turn.input_source, (user, assistant, voice),
        )
        return PreparedTurn(
            turn=conversation_turn,
            business={"kind": "template"},
            messages=(
                {"role": "user", "content": turn.raw_text, "block_id": user.block_id},
                {"role": "assistant", "content": answer, "block_id": assistant.block_id},
            ),
            voice_items=(),
        )


class StorageProcessor:
    """制作储存库：识别位置/物品并调用储存库工具登记。"""

    def __init__(self, *, generate=run_storage_agent, history=get_recent_messages) -> None:
        self._generate = generate
        self._history = history

    def prepare(self, turn: TurnInput, timing: TurnTimingRecorder) -> PreparedTurn:
        history = list(self._history(turn.conversation_id))
        history.append({"role": "user", "content": turn.raw_text})
        timing.mark("understanding_started")
        timing.mark("llm_started")
        answer = self._generate(history, turn.conversation_id)
        timing.mark("llm_completed")
        timing.mark("understanding_completed")
        user = _text_block(turn, "user", turn.raw_text, assistant=False)
        assistant = _text_block(turn, "spoken", answer or "没有生成储存库结果，请补充位置/物品/数量后重试。", assistant=True)
        voice = ConversationBlock(
            block_id=f"{turn.turn_id}:voice",
            type=BlockType.VOICE,
            payload={},
            source_block_id=assistant.block_id,
            intent_id=f"{turn.turn_id}:voice",
            priority=MessagePriority.REVIEW,
        )
        conversation_turn = ConversationTurn(
            turn.conversation_id, turn.request_id, turn.turn_id,
            turn.interaction_mode, turn.experiment_context, turn.mode_version,
            turn.input_source, (user, assistant, voice),
        )
        return PreparedTurn(
            turn=conversation_turn,
            business={"kind": "storage"},
            messages=(
                {"role": "user", "content": turn.raw_text, "block_id": user.block_id},
                {"role": "assistant", "content": answer, "block_id": assistant.block_id},
            ),
            voice_items=(),
        )


def _restore_domain_from_store(
    store: TurnStore, conversation_id: str, lab_session_id: str
) -> None:
    """把存储里的实验状态恢复到 domain 全局单例。

    domain.session() 是进程全局单例，切到另一个 lab_session_id 时，
    必须先把对应实验的步骤游标和已记录值同步回去，否则模型看到的
    Harness 上下文和工具执行的 domain 状态会对不上。

    如果当前 lab_session_id 没有任何存储状态（全新实验），切到自由模式，
    防止模型看到上一个实验的上下文。
    """
    state = store.load_experiment_state(conversation_id, lab_session_id)
    facts = state.get("protocol_step_facts") or {}
    if not facts:
        # 这个 lab_session 没有方案状态 → 尝试继承同一 lab 的最近状态
        state2 = store.load_latest_experiment_state_for_lab(lab_session_id)
        if state2:
            facts = state2.get("protocol_step_facts") or {}
            if facts:
                state = state2
    protocol_id = facts.get("protocol_id")
    try:
        if not protocol_id:
            # 全新实验会话：切到自由模式，避免看到上一个实验的上下文
            current_session = domain.session()
            current_view = domain.step_view(current_session)
            if isinstance(current_view, Mapping) and current_view.get("mode") == "protocol":
                domain.start_session(None)
            return
        # 确保 domain 选中的方案是对的
        current_session = domain.session()
        current_view = domain.step_view(current_session)
        current_protocol_id = (
            str(current_view["protocol"]["id"])
            if isinstance(current_view, Mapping)
            and current_view.get("mode") == "protocol"
            and current_view.get("protocol")
            else None
        )
        if current_protocol_id != protocol_id:
            domain.start_session(protocol_id)
        # 恢复步骤游标
        current_step = int(facts.get("current_step_number") or 1)
        domain.move("jump", current_step)
        # 恢复已记录的步骤值
        for step_number, step_fact in (facts.get("steps") or {}).items():
            values = {}
            for field_name, observed in (step_fact.get("values") or {}).items():
                value = observed.get("value") if isinstance(observed, dict) else observed
                if value:
                    values[field_name] = value
            if values:
                domain.record_step_fields(int(step_number), values, False)
    except Exception:  # noqa: BLE001
        pass


class ExperimentProcessor:
    """统一路径：所有实验 Turn 都走 stream_agent，模型自己决定调什么工具。

    不再用统一理解引擎做意图分类——模型的工具选择本身就是意图理解。
    record_observation / move_step 等工具内部处理实体提取和步骤推进，
    完成后读回 domain 状态同步到 store。
    """

    def __init__(self, store: TurnStore) -> None:
        self._store = store

    def prepare(self, turn: TurnInput, timing: TurnTimingRecorder) -> PreparedTurn:
        if turn.lab_session_id is None:
            raise ValueError("实验 Turn 缺少 lab_session_id。")
        raw = (turn.raw_text or "").strip()

        # 纯标点/空内容不调大模型
        if raw and not any(ch.isalnum() for ch in raw):
            answer = "我在。需要我做什么？"
            user = _text_block(turn, "user", turn.raw_text, assistant=False)
            assistant = _text_block(turn, "spoken", answer, assistant=True)
            conversation_turn = ConversationTurn(
                turn.conversation_id, turn.request_id, turn.turn_id,
                turn.interaction_mode, turn.experiment_context, turn.mode_version,
                turn.input_source, (user, assistant),
            )
            return PreparedTurn(
                turn=conversation_turn,
                business={"kind": "experiment_chat"},
                messages=(
                    {"role": "user", "content": turn.raw_text, "block_id": user.block_id},
                    {"role": "assistant", "content": answer, "block_id": assistant.block_id},
                ),
            )

        # 加载存储状态，用于回写
        stored = self._store.load_experiment_state(
            turn.conversation_id, turn.lab_session_id
        )
        segment_id = int(stored["next_segment_id"])

        # 恢复 domain 全局单例到当前 lab_session_id 的状态。
        # 不恢复的话，切换实验时 domain 还停留在上一个实验的步骤上。
        try:
            _restore_domain_from_store(self._store, turn.conversation_id, turn.lab_session_id)
        except Exception as _e:
            print(f"[WARN] _restore_domain_from_store failed: {_e}")

        # 记录 domain 工具执行前的状态
        pre_step_number = None
        pre_protocol_id = None
        try:
            pre_view = domain.step_view(domain.session())
            if isinstance(pre_view, Mapping) and pre_view.get("mode") == "protocol":
                pre_step_number = int(pre_view["step"]["number"])
                pre_protocol_id = str(pre_view["protocol"]["id"])
        except Exception:  # noqa: BLE001
            pass

        # 所有 Turn 统一走 stream_agent —— 模型自己决定调工具还是直接回复
        timing.mark("understanding_started")
        timing.mark("llm_started")
        # 多取一些历史：超长会话由 compaction.compact_history 压成
        # 「较早对话摘要 + 最近原文」，而不是像以前那样直接把 20 条以外的丢掉。
        history = list(get_recent_messages(turn.conversation_id, limit=60))
        history.append({"role": "user", "content": turn.raw_text})
        text_parts: list[str] = []
        tool_cards: dict[str, dict] = {}
        for chunk in stream_agent(
            history,
            turn.conversation_id,
            turn.interaction_mode,
            turn.lab_session_id,
            policy_override=EXPERIMENT_RECORD_POLICY,
            allow_tools=True,
        ):
            if isinstance(chunk, str) and chunk.startswith("[[LABTHINK]]"):
                continue
            if isinstance(chunk, str) and chunk.startswith("[[LABCARD]]"):
                try:
                    card = json.loads(chunk[len("[[LABCARD]]"):])
                except json.JSONDecodeError:
                    continue
                key = card.get("tool_call_id") or "anon:" + str(len(tool_cards))
                tool_cards[key] = card
            elif isinstance(chunk, str):
                text_parts.append(chunk)
        timing.mark("llm_completed")
        timing.mark("understanding_completed")

        answer = "".join(text_parts).strip()
        if not answer and tool_cards:
            short = _tool_card_first_lines(tool_cards)
            if short:
                answer = short
        if not answer:
            answer = "我在，直接告诉我。"

        # 读回 domain 状态（工具执行后）
        post_step_number = None
        post_view = None
        post_protocol_id = None
        try:
            post_view = domain.step_view(domain.session())
            if isinstance(post_view, Mapping) and post_view.get("mode") == "protocol":
                post_step_number = int(post_view["step"]["number"])
                post_protocol_id = str(post_view["protocol"]["id"])
        except Exception:  # noqa: BLE001
            pass
        step_changed = (
            pre_step_number is not None
            and post_step_number is not None
            and pre_step_number != post_step_number
        )
        protocol_changed = pre_protocol_id != post_protocol_id

        # 构建 UI blocks
        user = _text_block(turn, "user", turn.raw_text, assistant=False)
        blocks: list[ConversationBlock] = [user]

        # 工具卡片
        for card in tool_cards.values():
            block_id = (
                card.get("tool_call_id")
                or f"{turn.turn_id}:tool:{card.get('title') or len(blocks)}"
            )
            blocks.append(ConversationBlock(
                block_id=block_id,
                type=BlockType.TOOL_CARD,
                payload=dict(card),
            ))

        # 步骤切换时展示方案/步骤/安全卡片
        if step_changed and isinstance(post_view, Mapping) and post_view.get("mode") == "protocol":
            protocol_info = post_view["protocol"]
            current_step = post_view["step"]
            blocks.append(ConversationBlock(
                block_id=f"{turn.turn_id}:protocol",
                type=BlockType.PROTOCOL_CARD,
                payload={
                    "title": protocol_info["title"],
                    "summary": f"共 {protocol_info['total_steps']} 步",
                    "status": "protocol",
                },
            ))
            blocks.append(ConversationBlock(
                block_id=f"{turn.turn_id}:step:{current_step['number']}",
                type=BlockType.STEP_CARD,
                payload={
                    "number": current_step["number"],
                    "title": current_step["title"],
                    "instruction": current_step["instruction"],
                    "lines": [
                        sub["text"] for sub in current_step.get("substeps", [])
                    ],
                    "meta": [
                        f"方案已知 {len(current_step.get('protocol_values', {}))} 项",
                        f"现场必测 {len(current_step.get('must_record', []))} 项",
                    ],
                },
            ))
            for index, item in enumerate(post_view.get("safety", [])):
                blocks.append(ConversationBlock(
                    block_id=f"{turn.turn_id}:safety:{item.get('cas') or item.get('name') or index}",
                    type=BlockType.SAFETY_ALERT,
                    payload={**item, "note": post_view.get("safety_note")},
                ))

        assistant = _text_block(turn, "assistant", answer, assistant=True)
        blocks.append(assistant)

        # 语音
        voice_block = ConversationBlock(
            block_id=f"{turn.turn_id}:voice",
            type=BlockType.VOICE,
            payload={},
            source_block_id=assistant.block_id,
            intent_id=f"{turn.turn_id}:voice",
            priority=MessagePriority.ACTIVE_QUESTION,
        )
        blocks.append(voice_block)
        voice_items = (
            _voice_item(turn, answer, assistant.block_id, MessageKind.ASSISTANT_REPLY),
        )

        # 同步 domain 状态到 store
        # 注意：stored 是本轮开始时加载的，不包含工具执行期间 _select_protocol_for_session
        # 写入的 protocol_version 和完整快照。所以必须从 post-tool domain 状态补齐，
        # 否则 facts 缺 protocol_version → _format_experiment_state 误判为自由记录模式。
        protocol_step_facts = dict(stored.get("protocol_step_facts") or {})
        # 优先使用工具执行后的 protocol_id（模型可能在本次调用 select_protocol 切换了方案）
        effective_protocol_id = post_protocol_id or pre_protocol_id or protocol_step_facts.get("protocol_id")
        if effective_protocol_id:
            protocol_step_facts["protocol_id"] = effective_protocol_id
        if post_step_number is not None:
            protocol_step_facts["current_step_number"] = post_step_number
        # 从 post-tool domain 状态补齐 protocol_version
        if isinstance(post_view, Mapping) and post_view.get("mode") == "protocol":
            proto_info = post_view.get("protocol")
            if proto_info and proto_info.get("version"):
                protocol_step_facts["protocol_version"] = str(proto_info["version"])

        # 把 domain 里已记录的步骤值序列化进 protocol_step_facts。
        # 不做这一步的话，下一轮恢复时上下文里看不到已记录的实测值，
        # 模型会反复问"实际称了多少克"。
        # 格式必须匹配 ProtocolStepFactState.from_snapshot 的要求：
        # 每个 step 条目需要 protocol_id、protocol_version、step_number；
        # 每个 value 条目需要 value、request_id、segment_id。
        try:
            all_values = domain.recorded_step_values()
            eff_pid = protocol_step_facts.get("protocol_id", "")
            eff_pv = protocol_step_facts.get("protocol_version", "")
            if all_values and eff_pid and eff_pv:
                steps_dict = protocol_step_facts.setdefault("steps", {})
                for sn, vals in all_values.items():
                    step_key = str(sn)
                    step_entry = steps_dict.setdefault(step_key, {})
                    step_entry["protocol_id"] = eff_pid
                    step_entry["protocol_version"] = eff_pv
                    step_entry["step_number"] = sn
                    step_entry["values"] = {
                        name: {"value": str(val), "request_id": "domain-sync", "segment_id": 1}
                        for name, val in vals.items()
                    }
        except Exception:  # noqa: BLE001
            pass

        state_changed = step_changed or protocol_changed or bool(tool_cards)
        session_state = None
        if state_changed:
            session_state = {
                "revision": int(stored.get("revision") or 0) + 1,
                "reply_coordinator": dict(stored.get("reply_coordinator") or {}),
                "session_context": dict(stored.get("session_context") or {}),
                "protocol_step_facts": protocol_step_facts,
            }

        conversation_turn = ConversationTurn(
            turn.conversation_id, turn.request_id, turn.turn_id,
            turn.interaction_mode, turn.experiment_context, turn.mode_version,
            turn.input_source, tuple(blocks),
        )
        return PreparedTurn(
            turn=conversation_turn,
            business={"kind": "experiment", "segment_id": segment_id},
            messages=(
                {"role": "user", "content": turn.raw_text, "block_id": user.block_id},
                {"role": "assistant", "content": answer, "block_id": assistant.block_id},
            ),
            session_state=session_state,
            voice_items=voice_items,
        )
