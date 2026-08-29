"""Business processors used behind the unified Web Turn boundary."""

from __future__ import annotations

import difflib
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Callable, Mapping, Protocol

import json

import domain
import lab_tools
import llm_bridge
import settings_store
from agent.core import (
    refine_chat_answer,
    run_agent,
    run_experiment_tool_agent,
    run_storage_agent,
    run_template_agent,
    stream_agent,
)
from database.crud import get_recent_messages
from database.turn_store import TurnStore
from src.core.clarification_executor import ClarificationExecutor
from src.core.conversation_turn import (
    BlockType,
    ConversationBlock,
    ConversationTurn,
    ExperimentContext,
)
from src.core.clarification_acceptance import ClarificationActionType
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
from src.core.spoken_output import build_spoken_block_plan, select_spoken_output_policy
from src.core.unified_acceptance_bypass import UnifiedAcceptanceBypass
from src.core.unified_observer import UnifiedObservationStatus, UnifiedObserver
from src.llm.unified_router import UnifiedUnderstandingRouter


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


def _prepare_chat_spoken_delivery(
    turn: TurnInput, answer: str
) -> tuple[str, VoiceDeliveryItem]:
    """Preserve the exact visible/spoken Chat block and no-truncation rule."""

    policy = select_spoken_output_policy(
        turn.interaction_mode, turn.experiment_context
    )

    def build(text: str) -> VoiceDeliveryItem:
        plan = build_spoken_block_plan(
            turn_id=turn.turn_id,
            text=text,
            intent_id=f"{turn.turn_id}:voice",
            priority=MessagePriority.REVIEW,
            policy=policy,
        )
        return VoiceDeliveryItem(
            intent_id=plan.voice_block.intent_id or "",
            kind=MessageKind.ASSISTANT_REPLY,
            priority=plan.voice_block.priority or MessagePriority.REVIEW,
            voice_text=plan.voice_text,
            source_block_id=plan.source_block.block_id,
            max_chars=policy.estimated_max_chars or len(plan.voice_text),
            speech_rate=settings_store.current().tts_speed,
        )

    try:
        return answer, build(answer)
    except ValueError as error:
        if "超过估算上限" not in str(error):
            raise
    refined = refine_chat_answer(
        answer, max_chars=policy.estimated_max_chars or 50
    )
    return refined, build(refined)


def _wants_protocol_list(text: str) -> bool:
    lowered = (text or "").strip()
    if not lowered:
        return False
    return any(keyword in lowered for keyword in (
        "选择实验", "列出来", "列出", "哪些方案", "有哪些实验",
        "哪12", "开始实验", "实验方案", "选实验",
    ))


def _wants_reagent_list(text: str) -> bool:
    lowered = (text or "").strip()
    if not lowered:
        return False
    return any(keyword in lowered for keyword in (
        "列试剂", "列出试剂", "有哪些试剂", "有什么溶液",
        "配什么", "试剂配置库", "开始配置", "开始配液",
    ))


def _normalize_match_text(text: str) -> str:
    lowered = (text or "").lower()
    for word in ("请", "帮我", "我要", "我想", "开始", "选择", "进入",
                 "打开", "看看", "做", "用", "配置", "配", "一下", "实验"):
        lowered = lowered.replace(word, "")
    return lowered.strip()


def _best_protocol_match(text: str) -> dict | None:
    outcome = lab_tools.call("list_protocols", {})
    if not outcome.get("ok"):
        return None
    raw = _normalize_match_text(text)
    best: dict | None = None
    best_score = 0.0
    for item in outcome.get("result") or []:
        title = (item.get("title") or "").lower()
        if not title:
            continue
        if raw and title in raw:
            score = 3.0
        elif raw and raw in title:
            score = 2.5
        else:
            score = difflib.SequenceMatcher(None, raw, title).ratio()
        if score > best_score:
            best_score = score
            best = item
    return best if best_score >= 0.62 else None


def _best_reagent_match(text: str) -> dict | None:
    outcome = lab_tools.call("list_reagent_preps", {})
    if not outcome.get("ok"):
        return None
    raw = _normalize_match_text(text)
    best: dict | None = None
    best_score = 0.0
    for item in outcome.get("result", {}).get("items") or []:
        title = (item.get("name_zh") or "").lower()
        if not title:
            continue
        if raw and title in raw:
            score = 3.0
        elif raw and raw in title:
            score = 2.5
        else:
            score = difflib.SequenceMatcher(None, raw, title).ratio()
        if score > best_score:
            best_score = score
            best = item
    return best if best_score >= 0.62 else None


def _looks_like_direct_protocol(text: str) -> bool:
    lowered = (text or "").strip()
    return bool(lowered) and any(keyword in lowered for keyword in (
        "做", "开始", "选择", "进入", "用",
    ))


def _looks_like_direct_reagent(text: str) -> bool:
    lowered = (text or "").strip()
    return bool(lowered) and any(keyword in lowered for keyword in (
        "配", "配置", "做", "打开", "查看", "用",
    ))


def _is_confident_direct_match(text: str, title: str) -> bool:
    raw = _normalize_match_text(text)
    normalized_title = (title or "").lower()
    if not raw or not normalized_title:
        return False
    return (
        raw in normalized_title
        or normalized_title in raw
        or difflib.SequenceMatcher(None, raw, normalized_title).ratio() >= 0.8
    )


class ChatProcessor:
    """Prepare Chat messages and Blocks without writing the conversation ledger."""

    def __init__(self, *, generate=stream_agent, history=get_recent_messages) -> None:
        self._generate = generate
        self._history = history

    def prepare(self, turn: TurnInput, timing: TurnTimingRecorder) -> PreparedTurn:
        history = list(self._history(turn.conversation_id))
        history.append({"role": "user", "content": turn.raw_text})
        timing.mark("understanding_started")
        timing.mark("llm_started")
        # 使用流式 agent 生成：保留工具卡片与 ui_action，不再只返回一段纯文本。
        text_parts: list[str] = []
        cards: dict[str, dict] = {}
        for chunk in self._generate(history, turn.conversation_id, turn.interaction_mode):
            if isinstance(chunk, str) and chunk.startswith("[[LABTHINK]]"):
                continue
            if isinstance(chunk, str) and chunk.startswith("[[LABCARD]]"):
                try:
                    card = json.loads(chunk[len("[[LABCARD]]"):])
                except json.JSONDecodeError:
                    continue
                key = card.get("tool_call_id") or "anon:" + str(len(cards))
                cards[key] = card
            elif isinstance(chunk, str):
                text_parts.append(chunk)
        cards_list = list(cards.values())
        direct_protocol = None
        direct_reagent = None
        # 1) 用户说了具体方案名/试剂名时，直接选择或打开对应卡片页。
        #    只要名称高度匹配就命中，不一定非要带“配/做/打开”等动词。
        #    试剂类优先：缓冲液/溶液/直接发名称通常是想打开配方。
        if not any(card.get("title") == "查看试剂配方" for card in cards_list):
            reagent_match = _best_reagent_match(turn.raw_text)
            if reagent_match is not None and (
                _looks_like_direct_reagent(turn.raw_text)
                or _is_confident_direct_match(turn.raw_text, reagent_match.get("name_zh") or "")
            ):
                outcome = lab_tools.call(
                    "get_reagent_prep", {"reagent_prep_id": reagent_match["reagent_prep_id"]}
                )
                if outcome.get("ok"):
                    cards["__direct_reagent"] = lab_tools.present_result(
                        "get_reagent_prep",
                        {"reagent_prep_id": reagent_match["reagent_prep_id"]},
                        outcome,
                    )
                    cards_list = list(cards.values())
                    direct_reagent = reagent_match
        if not direct_reagent and not any(card.get("title") == "选择实验方案" or card.get("kind") == "execute"
                                          for card in cards_list):
            match = _best_protocol_match(turn.raw_text)
            if match is not None and (
                _looks_like_direct_protocol(turn.raw_text)
                or _is_confident_direct_match(turn.raw_text, match.get("title") or "")
            ):
                outcome = lab_tools.call(
                    "select_protocol", {"protocol_id": match["protocol_id"]}
                )
                if outcome.get("ok"):
                    cards["__direct_protocol"] = lab_tools.present_result(
                        "select_protocol",
                        {"protocol_id": match["protocol_id"]},
                        outcome,
                    )
                    cards_list = list(cards.values())
                    direct_protocol = match
        # 2) 没直接命中时，用户明确要“列方案/选实验/看试剂库”则强制列出概览。
        if not direct_protocol and not direct_reagent:
            if not any(card.get("title") == "查看可选实验方案" for card in cards_list) \
                    and _wants_protocol_list(turn.raw_text):
                outcome = lab_tools.call("list_protocols", {})
                if outcome.get("ok"):
                    cards["__fallback_protocols"] = lab_tools.present_result(
                        "list_protocols", {}, outcome
                    )
                    cards_list = list(cards.values())
            elif not any(card.get("title") == "查看试剂配置库" for card in cards_list) \
                    and _wants_reagent_list(turn.raw_text):
                outcome = lab_tools.call("list_reagent_preps", {})
                if outcome.get("ok"):
                    cards["__fallback_reagents"] = lab_tools.present_result(
                        "list_reagent_preps", {}, outcome
                    )
                    cards_list = list(cards.values())
        answer = "".join(text_parts).strip() or "处理完成。"
        if direct_protocol:
            answer = f"已进入「{direct_protocol['title']}」，开始实验。"
        elif direct_reagent:
            answer = f"已找到「{direct_reagent['name_zh']}」并打开试剂配置库。"
        # 方案/试剂很多时，聊天只给简短概览，真正的选择交给方案库/配置库页面。
        list_card = next((
            card for card in cards_list
            if card.get("status") == "done"
            and card.get("title") in {"查看可选实验方案", "查看试剂配置库"}
        ), None)
        if list_card and not direct_protocol and not direct_reagent:
            lines = list_card.get("lines") or []
            count_line = lines[0] if lines else ""
            if list_card.get("title") == "查看可选实验方案":
                answer = f"{count_line}。已打开实验方案库，请在卡片页选择要做的实验。"
            else:
                answer = f"{count_line}。已打开试剂配置库，请在卡片页选择要配的试剂。"
            _, voice_item = _prepare_chat_spoken_delivery(turn, answer)
        else:
            answer, voice_item = _prepare_chat_spoken_delivery(turn, answer)
        timing.mark("first_chunk")
        timing.mark("llm_completed")
        timing.mark("understanding_completed")
        user = _text_block(turn, "user", turn.raw_text, assistant=False)
        blocks = [user]
        for card in cards_list:
            block_id = card.get("tool_call_id") or f"{turn.turn_id}:tool:{card.get('title') or len(cards_list)}"
            blocks.append(ConversationBlock(
                block_id=block_id,
                type=BlockType.TOOL_CARD,
                payload=dict(card),
            ))
        assistant = _text_block(turn, "spoken", answer, assistant=True)
        blocks.append(assistant)
        voice = ConversationBlock(
            block_id=f"{turn.turn_id}:voice",
            type=BlockType.VOICE,
            payload={},
            source_block_id=assistant.block_id,
            intent_id=f"{turn.turn_id}:voice",
            priority=MessagePriority.REVIEW,
        )
        blocks.append(voice)
        conversation_turn = ConversationTurn(
            turn.conversation_id, turn.request_id, turn.turn_id,
            turn.interaction_mode, turn.experiment_context, turn.mode_version,
            turn.input_source, tuple(blocks),
        )
        return PreparedTurn(
            turn=conversation_turn,
            business={"kind": "chat"},
            messages=(
                {"role": "user", "content": turn.raw_text, "block_id": user.block_id},
                {"role": "assistant", "content": answer, "block_id": assistant.block_id},
            ),
            voice_items=(voice_item,),
        )


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
        assistant = _text_block(turn, "spoken", answer or "模板制作完成。", assistant=True)
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
        assistant = _text_block(turn, "spoken", answer or "储存库处理完成。", assistant=True)
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


class _RuleAnswerExtractor:
    def extract(self, answer_text: str) -> set[str]:
        entities = extract_entities(answer_text)
        return {
            name for name, value in vars(entities).items()
            if isinstance(value, str) and value.strip()
        }


class ExperimentProcessor:
    """Plan experiment/control/uncertain output from a SQLite-restored state copy."""

    def __init__(
        self,
        store: TurnStore,
        *,
        observer_factory: Callable[[], UnifiedObserver] | None = None,
        tool_runner=run_experiment_tool_agent,
    ) -> None:
        self._store = store
        self._observer_factory = observer_factory
        self._tool_runner = tool_runner

    def _observer(self) -> UnifiedObserver:
        if self._observer_factory is not None:
            return self._observer_factory()
        return UnifiedObserver(UnifiedAcceptanceBypass(
            UnifiedUnderstandingRouter(llm_bridge.processor())
        ))

    def prepare(self, turn: TurnInput, timing: TurnTimingRecorder) -> PreparedTurn:
        if turn.lab_session_id is None:
            raise ValueError("实验 Turn 缺少 lab_session_id。")
        tool_command = ExperimentToolCommandParser.parse(turn.raw_text)
        if tool_command.matched:
            return self._prepare_tool_turn(turn, timing, tool_command.command_text or "")
        stored = self._store.load_experiment_state(
            turn.conversation_id, turn.lab_session_id
        )
        coordinator = ReplyCoordinator.from_snapshot(
            dict(stored["reply_coordinator"])
        )
        context = SessionContext.from_snapshot(dict(stored["session_context"]))
        segment_id = int(stored["next_segment_id"])
        protocol_domain_state = None
        protocol_execution = None
        if turn.experiment_context == ExperimentContext.PROTOCOL:
            selected_domain_state = domain.session()
            selected_view = domain.step_view(selected_domain_state)
            if (
                not isinstance(selected_view, Mapping)
                or selected_view.get("mode") != "protocol"
            ):
                raise ValueError("方案实验模式需要先选择一个有效实验方案。")
            protocol_info = selected_view["protocol"]
            protocol_execution = ProtocolExecutionState.from_snapshot(
                stored.get("protocol_step_facts"),
                protocol_id=str(protocol_info["id"]),
                protocol_version=str(protocol_info["version"]),
                default_step_number=int(selected_view["step"]["number"]),
            )
            protocol_domain_state = (
                selected_domain_state.jump_to(
                    protocol_execution.current_step_number
                )
                if selected_domain_state is not None
                else None
            )
            step = domain.step_view(protocol_domain_state)
        else:
            step = {"mode": "free", "protocol": None, "step": None}

        protocol_state = None
        if turn.experiment_context == ExperimentContext.PROTOCOL:
            protocol_info = step["protocol"]
            current_step = step["step"]
            protocol_state = protocol_execution.step_state(
                int(current_step["number"])
            )

        timing.mark("understanding_started")
        timing.mark("llm_started")
        observation = self._observer().observe(
            request_id=turn.request_id,
            session_id=turn.lab_session_id,
            segment_id=segment_id,
            asr_result=turn.asr_result,
            raw_text=turn.raw_text,
            reply_coordinator=coordinator,
            recent_context=context.as_prompt_context(),
        )
        timing.mark("llm_completed")
        timing.mark("understanding_completed")
        if observation.status != UnifiedObservationStatus.OBSERVED:
            raise RuntimeError(f"统一理解失败：{observation.error_type}")

        events: tuple[Mapping[str, object], ...] = ()
        lab_record = None
        analysis = None
        entities: dict[str, str] = {}
        protocol_completion = None
        protocol_navigation = None
        final_action = observation.pending_action
        if observation.protocol_navigation_action is not None:
            if (
                turn.experiment_context == ExperimentContext.PROTOCOL
                and protocol_execution is not None
                and protocol_domain_state is not None
            ):
                protocol_navigation = decide_protocol_move(
                    state=protocol_execution,
                    action=observation.protocol_navigation_action,
                    total_steps=int(step["protocol"]["total_steps"]),
                    evaluation=domain.evaluate_for_state(
                        protocol_domain_state,
                        protocol_state.entity_values(),
                    ),
                    unresolved=coordinator.active_clarifications(),
                )
                if protocol_navigation.allowed:
                    protocol_execution = protocol_navigation.state
                    protocol_domain_state = selected_domain_state.jump_to(
                        protocol_execution.current_step_number
                    )
                    step = domain.step_view(protocol_domain_state)
        if observation.accepted_analysis is not None:
            analysis = observation.accepted_analysis.materialize_analysis()
            events = tuple(event.to_dict() for event in analysis.events)
            context.add_analysis(analysis)
            for event in analysis.events:
                for name, value in vars(event.entities).items():
                    if value and name not in entities:
                        entities[name] = value

            if (
                turn.experiment_context == ExperimentContext.PROTOCOL
                and observation.accepted_analysis.kind
                == ExperimentAcceptanceKind.STRUCTURED_EXPERIMENT
            ):
                protocol_state, conflicting_fields = protocol_state.merge(
                    entities,
                    request_id=turn.request_id,
                    segment_id=segment_id,
                )
                existing = (
                    coordinator.find_clarification(protocol_state.clarification_id)
                    if protocol_state.clarification_id is not None
                    else None
                )
                protocol_completion = resolve_protocol_completion(
                    accepted=observation.accepted_analysis,
                    state=protocol_state,
                    evaluation=domain.evaluate_for_state(
                        protocol_domain_state, protocol_state.entity_values()
                    ),
                    existing=existing,
                    conflicting_fields=conflicting_fields,
                )
                final_action = protocol_completion.action
                protocol_execution = protocol_execution.with_step(protocol_state)

        answer_target = None
        if (
            protocol_execution is not None
            and analysis is None
            and final_action is not None
            and final_action.action_type == ClarificationActionType.ANSWER
        ):
            answer_target = coordinator.find_clarification(
                final_action.target_clarification_id
            )
            if (
                answer_target is None
                or answer_target.protocol_id != protocol_execution.protocol_id
                or answer_target.protocol_version
                != protocol_execution.protocol_version
                or answer_target.protocol_step_number is None
            ):
                answer_target = None
        if answer_target is not None:
            target_step_number = answer_target.protocol_step_number
            protocol_state = protocol_execution.step_state(target_step_number)
            extracted = extract_entities(final_action.answer_text or turn.raw_text)
            answer_values = {
                name: value for name, value in vars(extracted).items()
                if isinstance(value, str) and value.strip()
            }
            supplied = tuple(final_action.supplied_entity_fields)
            if len(supplied) == 1 and supplied[0] not in answer_values:
                # The unified answer route currently carries field names, not
                # values. For one unambiguous target field, retain the answer
                # text as its traceable observed value rather than losing it.
                answer_values[supplied[0]] = final_action.answer_text or turn.raw_text
            protocol_state, _ = protocol_state.merge(
                answer_values,
                request_id=turn.request_id,
                segment_id=segment_id,
            )
            protocol_execution = protocol_execution.with_step(protocol_state)

        execution = None
        if final_action is not None:
            execution = ClarificationExecutor(
                coordinator, entity_extractor=_RuleAnswerExtractor()
            ).execute(final_action)
        if (
            protocol_state is not None
            and execution is not None
            and execution.state_changed
            and execution.action_type == ClarificationActionType.CREATE
            and execution.affected_clarification_id is not None
        ):
            protocol_state = replace(
                protocol_state,
                clarification_id=execution.affected_clarification_id,
            )
            protocol_completion = replace(protocol_completion, state=protocol_state)
            protocol_execution = protocol_execution.with_step(protocol_state)

        if protocol_execution is not None and execution is not None:
            affected = (
                coordinator.find_clarification(execution.affected_clarification_id)
                if execution.affected_clarification_id is not None
                else None
            )
            if affected is not None and affected.protocol_step_number is not None:
                affected_state = protocol_execution.step_state(
                    affected.protocol_step_number
                )
                selected_state = domain.session()
                affected_domain_state = (
                    selected_state.jump_to(affected.protocol_step_number)
                    if selected_state is not None
                    else None
                )
                affected_eval = domain.evaluate_for_state(
                    affected_domain_state, affected_state.entity_values()
                )
                if not affected_eval.get("missing_fields"):
                    affected_status = (
                        ProtocolStepProgressStatus.COMPLETED
                        if affected.protocol_step_number
                        != protocol_execution.current_step_number
                        else ProtocolStepProgressStatus.IN_PROGRESS
                    )
                elif affected.status.value == "deferred":
                    affected_status = ProtocolStepProgressStatus.LEFT_WITH_PENDING
                else:
                    affected_status = ProtocolStepProgressStatus.IN_PROGRESS
                protocol_execution = protocol_execution.with_step(
                    affected_state, status=affected_status
                )

        if analysis is not None:
            evaluation = (
                {
                    "missing_fields": list(protocol_completion.missing_fields),
                    "follow_up_required": protocol_completion.follow_up_required,
                    "follow_up_question": protocol_completion.follow_up_question,
                    "deviations": list(protocol_completion.deviations),
                    "conflicting_fields": list(
                        protocol_completion.conflicting_fields
                    ),
                }
                if protocol_completion is not None
                else {
                    "missing_fields": list(observation.missing_fields),
                    "follow_up_required": bool(observation.follow_up_required),
                    "follow_up_question": analysis.follow_up_question,
                    "deviations": [],
                }
            )
            lab_record = {
                "session_id": turn.lab_session_id,
                "segment_id": segment_id,
                "transcript": turn.raw_text,
                "entities": entities,
                "extraction": {
                    **analysis.to_dict(),
                    "input_kind": "experiment",
                    "degraded": observation.accepted_analysis.degraded,
                    "error": observation.accepted_analysis.error,
                },
                "extraction_source": (
                    "degraded" if observation.accepted_analysis.degraded else "llm"
                ),
                "evaluation": evaluation,
                "step": step,
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }

        effective_question = (
            protocol_completion.follow_up_question
            if protocol_completion is not None
            else (analysis.follow_up_question if analysis is not None else None)
        )
        reply_text, kind = self._reply_text(
            observation,
            execution,
            coordinator,
            analysis,
            effective_question=effective_question,
            protocol_completion=protocol_completion,
            protocol_navigation=protocol_navigation,
            protocol_navigation_requested=(
                observation.protocol_navigation_action is not None
            ),
            protocol_navigation_step=(
                step.get("step")
                if protocol_navigation is not None and protocol_navigation.allowed
                else None
            ),
            experiment_step_count=int(
                stored.get("experiment_step_count", max(segment_id - 1, 0))
            ),
        )
        user = _text_block(turn, "user", turn.raw_text, assistant=False)
        assistant = _text_block(turn, "assistant", reply_text, assistant=True)
        created_clarification = bool(
            execution is not None
            and execution.state_changed
            and execution.action_type == ClarificationActionType.CREATE
            and execution.affected_display_number is not None
            and effective_question
        )
        clarification_block = None
        if created_clarification:
            assistant = ConversationBlock(
                block_id=assistant.block_id,
                type=BlockType.ASSISTANT_TEXT,
                payload={"text": reply_text, "presentation": "clarification_card"},
            )
            clarification_block = ConversationBlock(
                block_id=f"{turn.turn_id}:clarification:{execution.affected_display_number}",
                type=BlockType.CONFIRMATION_CARD,
                payload={
                    "display_number": execution.affected_display_number,
                    "title": f"问题 {execution.affected_display_number}",
                    "question": effective_question,
                    "missing_fields": (
                        list(protocol_completion.missing_fields)
                        if protocol_completion is not None
                        else list(observation.missing_fields)
                    ),
                    "status": "待回答",
                    "protocol_step_number": (
                        protocol_state.step_number
                        if protocol_state is not None else None
                    ),
                },
            )
        elif (
            execution is not None
            and execution.state_changed
            and execution.action_type == ClarificationActionType.ANSWER
            and execution.affected_clarification_id is not None
        ):
            updated = coordinator.find_clarification(
                execution.affected_clarification_id
            )
            if updated is not None:
                remaining_text = "、".join(
                    FIELD_LABELS.get(name, name)
                    for name in updated.missing_fields
                )
                projected_question = (
                    f"还需要补充：{remaining_text}。"
                    if remaining_text
                    else "本问题需要的信息已补充完整。"
                )
                assistant = ConversationBlock(
                    block_id=assistant.block_id,
                    type=BlockType.ASSISTANT_TEXT,
                    payload={
                        "text": reply_text,
                        "presentation": "clarification_card",
                    },
                )
                clarification_block = ConversationBlock(
                    block_id=(
                        f"{turn.turn_id}:clarification:"
                        f"{updated.display_number}:revision:{updated.revision}"
                    ),
                    type=BlockType.CONFIRMATION_CARD,
                    payload={
                        "clarification_id": updated.clarification_id,
                        "display_number": updated.display_number,
                        "title": f"问题 {updated.display_number}",
                        "question": projected_question,
                        "original_question": updated.question,
                        "missing_fields": list(updated.missing_fields),
                        "revision": updated.revision,
                        "status": (
                            "待回答" if updated.is_unresolved else "已解决"
                        ),
                    },
                )
        blocks = [user]
        if turn.experiment_context == ExperimentContext.PROTOCOL:
            protocol_info = step["protocol"]
            current_step = step["step"]
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
            for index, item in enumerate(step.get("safety", [])):
                blocks.append(ConversationBlock(
                    block_id=f"{turn.turn_id}:safety:{item.get('cas') or item.get('name') or index}",
                    type=BlockType.SAFETY_ALERT,
                    payload={**item, "note": step.get("safety_note")},
                ))
        if lab_record is not None:
            blocks.append(ConversationBlock(
                block_id=f"{turn.turn_id}:record:{segment_id}",
                type=BlockType.RECORD_CARD,
                payload={
                    "session_id": turn.lab_session_id,
                    "segment_id": segment_id,
                    "transcript": turn.raw_text,
                    "entities": lab_record["entities"],
                },
            ))
        if clarification_block is not None:
            blocks.append(clarification_block)
        blocks.append(assistant)

        voice_items: tuple[VoiceDeliveryItem, ...] = ()
        should_speak = not (
            kind == MessageKind.RECORD_ACK
            and not settings_store.current().speak_record_ack
        )
        if should_speak:
            voice_text = reply_text
            voice_source_block_id = assistant.block_id
            if created_clarification:
                # 屏幕可以显示编号和状态，语音只读真正需要用户回答的问题。
                voice_text = effective_question
                voice_source_block_id = clarification_block.block_id
            if kind == MessageKind.SESSION_CLOSING_SUMMARY:
                unresolved_count = len(coordinator.active_clarifications())
                voice_text = (
                    f"本次实验记录已结束，仍有 {unresolved_count} 个待确认问题，"
                    "请查看屏幕汇总。"
                    if unresolved_count
                    else "本次实验记录已结束，没有待确认问题。"
                )
            voice_priority = (
                MessagePriority.SUMMARY
                if kind == MessageKind.SESSION_CLOSING_SUMMARY
                else MessagePriority.ACTIVE_QUESTION
            )
            voice_block = ConversationBlock(
                block_id=f"{turn.turn_id}:voice",
                type=BlockType.VOICE,
                payload={}, source_block_id=voice_source_block_id,
                intent_id=f"{turn.turn_id}:voice",
                priority=voice_priority,
            )
            blocks.append(voice_block)
            voice_items = (_voice_item(turn, voice_text, voice_source_block_id, kind),)

        conversation_turn = ConversationTurn(
            turn.conversation_id, turn.request_id, turn.turn_id,
            turn.interaction_mode, turn.experiment_context, turn.mode_version,
            turn.input_source, tuple(blocks),
        )
        state_changed = bool(
            analysis is not None
            or (execution is not None and execution.state_changed)
            or (protocol_navigation is not None and protocol_navigation.allowed)
        )
        session_state = None
        if state_changed:
            session_state = {
                "revision": int(stored["revision"]) + 1,
                "reply_coordinator": coordinator.to_snapshot(),
                "session_context": context.to_snapshot(),
                "protocol_step_facts": (
                    protocol_execution.to_snapshot()
                    if protocol_execution is not None
                    else stored.get("protocol_step_facts") or {}
                ),
            }
        return PreparedTurn(
            turn=conversation_turn,
            business={
                "kind": "experiment",
                "session_ended": observation.end_session_execution_requested,
                "input_kind": (
                    "experiment" if analysis is not None
                    else (observation.destination or "uncertain")
                ),
                "segment_id": segment_id if lab_record is not None else None,
                "clarification_action": (
                    final_action.action_type.value
                    if final_action is not None
                    else "no_action"
                ),
                "execution": (
                    {"state_changed": execution.state_changed, "reason": execution.reason}
                    if execution is not None else None
                ),
            },
            lab_record=lab_record,
            experiment_events=events,
            session_state=session_state,
            voice_items=voice_items,
        )

    def _prepare_tool_turn(
        self, turn: TurnInput, timing: TurnTimingRecorder, command_text: str
    ) -> PreparedTurn:
        """Execute an addressed tool command without adopting experiment facts."""

        timing.mark("understanding_started")
        timing.mark("llm_started")
        outcome = self._tool_runner(
            command_text, turn.conversation_id, turn.lab_session_id
        )
        timing.mark("first_chunk")
        timing.mark("llm_completed")
        timing.mark("understanding_completed")

        user = _text_block(turn, "user", turn.raw_text, assistant=False)
        blocks = [user]
        for index, view in enumerate(outcome.tool_views, start=1):
            blocks.append(ConversationBlock(
                block_id=f"{turn.turn_id}:tool:{index}",
                type=BlockType.TOOL_CARD,
                payload=dict(view),
            ))
        assistant = _text_block(
            turn, "spoken", outcome.answer, assistant=True
        )
        blocks.append(assistant)
        voice = ConversationBlock(
            block_id=f"{turn.turn_id}:voice",
            type=BlockType.VOICE,
            payload={},
            source_block_id=assistant.block_id,
            intent_id=f"{turn.turn_id}:voice",
            priority=MessagePriority.REVIEW,
        )
        blocks.append(voice)
        conversation_turn = ConversationTurn(
            turn.conversation_id, turn.request_id, turn.turn_id,
            turn.interaction_mode, turn.experiment_context, turn.mode_version,
            turn.input_source, tuple(blocks),
        )
        voice_item = VoiceDeliveryItem(
            intent_id=f"{turn.turn_id}:voice",
            kind=MessageKind.ASSISTANT_REPLY,
            priority=MessagePriority.REVIEW,
            voice_text=outcome.answer,
            source_block_id=assistant.block_id,
            max_chars=max(80, len(outcome.answer)),
            speech_rate=settings_store.current().tts_speed,
        )
        return PreparedTurn(
            turn=conversation_turn,
            business={
                "kind": "experiment_tool",
                "called_tools": list(outcome.called_tools),
                "segment_id": None,
            },
            voice_items=(voice_item,),
        )

    @staticmethod
    def _reply_text(
        observation,
        execution,
        coordinator,
        analysis,
        *,
        effective_question,
        protocol_completion,
        protocol_navigation,
        protocol_navigation_requested: bool,
        protocol_navigation_step,
        experiment_step_count: int,
    ):
        if observation.end_session_execution_requested:
            active = coordinator.active_clarifications()
            lines = [
                "本次实验记录已结束。",
                f"本次共记录 {experiment_step_count} 个实验步骤。",
            ]
            if not active:
                lines.append("没有待确认问题。")
            else:
                lines.append(f"仍有 {len(active)} 个待确认问题：")
                for item in active:
                    status = "已暂缓" if item.status.value == "deferred" else "待回答"
                    scope = (
                        f"，步骤 {item.protocol_step_number}"
                        if item.protocol_step_number is not None else ""
                    )
                    lines.append(
                        f"问题 {item.display_number}（{status}{scope}）：{item.question}"
                    )
            return "\n".join(lines), MessageKind.SESSION_CLOSING_SUMMARY
        if observation.end_confirmation_requested:
            return "要结束本次实验记录吗？请明确回答确认或继续。", MessageKind.CLARIFICATION
        if protocol_navigation_requested:
            if protocol_navigation is None:
                return "当前没有运行实验方案，无法进入下一步。", MessageKind.NO_ACTION_FEEDBACK
            if not protocol_navigation.allowed:
                return protocol_navigation.reason, MessageKind.NO_ACTION_FEEDBACK
            return (
                f"{protocol_navigation.reason}"
                f"当前是第 {protocol_navigation_step['number']} 步："
                f"{protocol_navigation_step['title']}。",
                MessageKind.CONFIRMATION_ACK,
            )
        if observation.clarification_action == "review":
            active = coordinator.active_clarifications()
            if not active:
                return "当前没有待确认问题。", MessageKind.CLARIFICATION_REVIEW
            text = "待确认问题：" + "；".join(
                (
                    f"{item.display_number}. "
                    + (
                        f"（步骤 {item.protocol_step_number}）"
                        if item.protocol_step_number is not None else ""
                    )
                    + item.question
                )
                for item in active
            )
            return text, MessageKind.CLARIFICATION_REVIEW
        if execution is not None and execution.state_changed:
            if (
                execution.action_type == ClarificationActionType.CREATE
                and effective_question
                and execution.affected_display_number is not None
            ):
                return (
                    f"问题 {execution.affected_display_number}："
                    f"{effective_question}",
                    MessageKind.CLARIFICATION,
                )
            if execution.action_type == ClarificationActionType.ANSWER:
                if execution.resolved:
                    return (
                        f"问题 {execution.affected_display_number} 已补充完整。",
                        MessageKind.CONFIRMATION_ACK,
                    )
                if execution.remaining_fields:
                    remaining = "、".join(
                        FIELD_LABELS.get(name, name)
                        for name in execution.remaining_fields
                    )
                    return (
                        f"已记录本次补充，还需要补充：{remaining}。",
                        MessageKind.CLARIFICATION,
                    )
            return execution.reason, MessageKind.CONFIRMATION_ACK
        if protocol_completion is not None:
            if (
                protocol_completion.follow_up_required
                and protocol_completion.follow_up_question
            ):
                return (
                    protocol_completion.follow_up_question,
                    MessageKind.CLARIFICATION,
                )
            if analysis is not None and analysis.assistant_reply:
                return analysis.assistant_reply, MessageKind.ASSISTANT_REPLY
            return "已记录。", MessageKind.RECORD_ACK
        if analysis is not None:
            if analysis.should_ask_follow_up and analysis.follow_up_question:
                return analysis.follow_up_question, MessageKind.CLARIFICATION
            if analysis.assistant_reply:
                return analysis.assistant_reply, MessageKind.ASSISTANT_REPLY
            return "已记录。", MessageKind.RECORD_ACK
        if observation.destination == "abstention":
            return (
                "这句话暂时无法确定是实验记录还是控制指令，请换一种说法。",
                MessageKind.NO_ACTION_FEEDBACK,
            )
        return (
            execution.reason if execution is not None else "未执行任何状态变更。",
            MessageKind.NO_ACTION_FEEDBACK,
        )
