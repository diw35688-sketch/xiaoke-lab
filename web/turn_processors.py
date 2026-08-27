"""Business processors used behind the unified Web Turn boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Mapping, Protocol

import domain
import llm_bridge
import settings_store
from agent.core import refine_chat_answer, run_agent
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
from src.core.presentation_delivery import VoiceDeliveryItem
from src.core.presentation_intent import MessageKind, MessagePriority
from src.core.reply_coordinator import ReplyCoordinator
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


class ChatProcessor:
    """Prepare Chat messages and Blocks without writing the conversation ledger."""

    def __init__(self, *, generate=run_agent, history=get_recent_messages) -> None:
        self._generate = generate
        self._history = history

    def prepare(self, turn: TurnInput, timing: TurnTimingRecorder) -> PreparedTurn:
        history = list(self._history(turn.conversation_id))
        history.append({"role": "user", "content": turn.raw_text})
        timing.mark("understanding_started")
        timing.mark("llm_started")
        answer = self._generate(history, turn.conversation_id, turn.interaction_mode)
        answer, voice_item = _prepare_chat_spoken_delivery(turn, answer)
        timing.mark("first_chunk")
        timing.mark("llm_completed")
        timing.mark("understanding_completed")
        user = _text_block(turn, "user", turn.raw_text, assistant=False)
        assistant = _text_block(turn, "spoken", answer, assistant=True)
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
            business={"kind": "chat"},
            messages=(
                {"role": "user", "content": turn.raw_text, "block_id": user.block_id},
                {"role": "assistant", "content": answer, "block_id": assistant.block_id},
            ),
            voice_items=(voice_item,),
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
    ) -> None:
        self._store = store
        self._observer_factory = observer_factory

    def _observer(self) -> UnifiedObserver:
        if self._observer_factory is not None:
            return self._observer_factory()
        return UnifiedObserver(UnifiedAcceptanceBypass(
            UnifiedUnderstandingRouter(llm_bridge.processor())
        ))

    def prepare(self, turn: TurnInput, timing: TurnTimingRecorder) -> PreparedTurn:
        if turn.lab_session_id is None:
            raise ValueError("实验 Turn 缺少 lab_session_id。")
        stored = self._store.load_experiment_state(
            turn.conversation_id, turn.lab_session_id
        )
        coordinator = ReplyCoordinator.from_snapshot(
            dict(stored["reply_coordinator"])
        )
        context = SessionContext.from_snapshot(dict(stored["session_context"]))
        segment_id = int(stored["next_segment_id"])
        if turn.experiment_context == ExperimentContext.PROTOCOL:
            step = domain.step_view(domain.session())
            if not isinstance(step, Mapping) or step.get("mode") != "protocol":
                raise ValueError("方案实验模式需要先选择一个有效实验方案。")
        else:
            step = {"mode": "free", "protocol": None, "step": None}

        timing.mark("understanding_started")
        observation = self._observer().observe(
            request_id=turn.request_id,
            session_id=turn.lab_session_id,
            segment_id=segment_id,
            asr_result=turn.asr_result,
            raw_text=turn.raw_text,
            reply_coordinator=coordinator,
            recent_context=context.as_prompt_context(),
        )
        timing.mark("understanding_completed")
        if observation.status != UnifiedObservationStatus.OBSERVED:
            raise RuntimeError(f"统一理解失败：{observation.error_type}")

        execution = None
        if observation.pending_action is not None:
            execution = ClarificationExecutor(
                coordinator, entity_extractor=_RuleAnswerExtractor()
            ).execute(observation.pending_action)

        events: tuple[Mapping[str, object], ...] = ()
        lab_record = None
        analysis = None
        if observation.accepted_analysis is not None:
            analysis = observation.accepted_analysis.materialize_analysis()
            events = tuple(event.to_dict() for event in analysis.events)
            context.add_analysis(analysis)
            entities: dict[str, str] = {}
            for event in analysis.events:
                for name, value in vars(event.entities).items():
                    if value and name not in entities:
                        entities[name] = value
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
                "evaluation": {
                    "missing_fields": list(observation.missing_fields),
                    "follow_up_required": bool(observation.follow_up_required),
                    "follow_up_question": analysis.follow_up_question,
                    "deviations": [],
                },
                "step": step,
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }

        reply_text, kind = self._reply_text(
            observation,
            execution,
            coordinator,
            analysis,
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
            and analysis is not None
            and analysis.follow_up_question
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
                    "question": analysis.follow_up_question,
                    "status": "待回答",
                },
            )
        blocks = [user]
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
                voice_text = analysis.follow_up_question
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
            analysis is not None or (execution is not None and execution.state_changed)
        )
        session_state = None
        if state_changed:
            session_state = {
                "revision": int(stored["revision"]) + 1,
                "reply_coordinator": coordinator.to_snapshot(),
                "session_context": context.to_snapshot(),
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
                "clarification_action": observation.clarification_action,
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

    @staticmethod
    def _reply_text(
        observation,
        execution,
        coordinator,
        analysis,
        *,
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
                    lines.append(
                        f"问题 {item.display_number}（{status}）：{item.question}"
                    )
            return "\n".join(lines), MessageKind.SESSION_CLOSING_SUMMARY
        if observation.end_confirmation_requested:
            return "要结束本次实验记录吗？请明确回答确认或继续。", MessageKind.CLARIFICATION
        if observation.clarification_action == "review":
            active = coordinator.active_clarifications()
            if not active:
                return "当前没有待确认问题。", MessageKind.CLARIFICATION_REVIEW
            text = "待确认问题：" + "；".join(
                f"{item.display_number}. {item.question}" for item in active
            )
            return text, MessageKind.CLARIFICATION_REVIEW
        if execution is not None and execution.state_changed:
            if (
                execution.action_type == ClarificationActionType.CREATE
                and analysis is not None
                and analysis.follow_up_question
                and execution.affected_display_number is not None
            ):
                return (
                    f"问题 {execution.affected_display_number}："
                    f"{analysis.follow_up_question}",
                    MessageKind.CLARIFICATION,
                )
            return execution.reason, MessageKind.CONFIRMATION_ACK
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
