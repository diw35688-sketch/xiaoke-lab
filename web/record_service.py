"""Shared application service for recording one experiment observation.

The service owns the application order from extraction through persistence and
intent projection.  It contains no FastAPI, renderer, microphone, or playback
code, so desktop and mobile adapters can share it without sharing UI details.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

import degraded_producer
from src.core.presentation_intent import PresentationIntent
from src.core.presentation_projection import messages_for_observation
from src.core.record_observation_result import (
    ExtractionSource,
    RecordObservationResult,
    RecordStructureStatus,
)


class RecordPersistenceError(RuntimeError):
    """The observation could not be saved, so no success result exists."""


@dataclass(frozen=True)
class RecordCommand:
    transcript: str
    extract: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.transcript, str) or not self.transcript.strip():
            raise ValueError("transcript 不能为空。")
        if type(self.extract) is not bool:
            raise TypeError("extract 必须是 bool。")


@dataclass(frozen=True)
class SharedRecordResult:
    saved_record: Mapping[str, object]
    observation_result: RecordObservationResult | None
    intents: tuple[PresentationIntent, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "saved_record", MappingProxyType(dict(self.saved_record))
        )
        if self.observation_result is not None and not isinstance(
            self.observation_result, RecordObservationResult
        ):
            raise TypeError(
                "observation_result 必须是 RecordObservationResult 或 None。"
            )
        intents = tuple(self.intents)
        if any(not isinstance(item, PresentationIntent) for item in intents):
            raise TypeError("intents 只能包含 PresentationIntent。")
        object.__setattr__(self, "intents", intents)


class SharedRecordService:
    """Run extraction, deterministic evaluation, save, then projection."""

    def __init__(
        self,
        *,
        current_session_id: Callable[[], str],
        next_segment_id: Callable[[str], int],
        list_records: Callable[[str], Sequence[Mapping[str, object]]],
        extract_entities_llm: Callable[..., Mapping[str, object]],
        extract_entities_rule: Callable[[str, tuple[str, ...]], object],
        current_terms: Callable[[], tuple[str, ...]],
        evaluate: Callable[[dict[str, str]], object],
        step_view: Callable[[], object],
        save_record: Callable[[dict[str, object]], Mapping[str, object]],
        clock: Callable[[], datetime],
        request_id_factory: Callable[[], str],
    ) -> None:
        dependencies = {
            "current_session_id": current_session_id,
            "next_segment_id": next_segment_id,
            "list_records": list_records,
            "extract_entities_llm": extract_entities_llm,
            "extract_entities_rule": extract_entities_rule,
            "current_terms": current_terms,
            "evaluate": evaluate,
            "step_view": step_view,
            "save_record": save_record,
            "clock": clock,
            "request_id_factory": request_id_factory,
        }
        for name, dependency in dependencies.items():
            if not callable(dependency):
                raise TypeError(f"{name} 必须是可调用对象。")
        self._current_session_id = current_session_id
        self._next_segment_id = next_segment_id
        self._list_records = list_records
        self._extract_entities_llm = extract_entities_llm
        self._extract_entities_rule = extract_entities_rule
        self._current_terms = current_terms
        self._evaluate = evaluate
        self._step_view = step_view
        self._save_record = save_record
        self._clock = clock
        self._request_id_factory = request_id_factory

    def record(self, command: RecordCommand) -> SharedRecordResult:
        if not isinstance(command, RecordCommand):
            raise TypeError("command 必须是 RecordCommand。")

        text = command.transcript.strip()
        session_id = self._current_session_id()
        segment_id = self._next_segment_id(session_id)
        entities: dict[str, str] = {}
        extraction: Mapping[str, object] | None = None
        extraction_source = "none"

        if command.extract:
            try:
                extraction = self._extract_entities_llm(
                    text,
                    session_id,
                    segment_id,
                    recent_context=self._recent_context(session_id),
                )
                for event in extraction["events"]:
                    for name, value in event["entities"].items():
                        if value and not entities.get(name):
                            entities[name] = value
                extraction_source = (
                    "degraded" if extraction.get("degraded") else "llm"
                )
            except Exception as error:
                extraction = {
                    "events": [],
                    "degraded": True,
                    "error": f"{type(error).__name__}: {error}",
                }
                extraction_source = "degraded"

        if not entities:
            rule_entities = self._extract_entities_rule(
                text, self._current_terms()
            )
            rule_fields = {
                name: value
                for name, value in vars(rule_entities).items()
                if value
            }
            if rule_fields:
                entities.update(rule_fields)
                extraction_source = "rule"

        protocol_evaluation = self._evaluate(entities)
        step = self._step_view()
        evaluation = _select_effective_evaluation(
            extraction=extraction,
            protocol_evaluation=protocol_evaluation,
            step=step,
        )
        observed_at = self._clock()
        if not isinstance(observed_at, datetime):
            raise TypeError("clock 必须返回 datetime。")
        item: dict[str, object] = {
            "segment_id": segment_id,
            "session_id": session_id,
            "transcript": text,
            "entities": entities,
            "extraction": extraction,
            "extraction_source": extraction_source,
            "evaluation": evaluation,
            "step": step,
            "at": observed_at.isoformat(timespec="seconds"),
        }
        try:
            saved = self._save_record(item)
        except Exception as error:
            raise RecordPersistenceError(
                f"实验记录落盘失败：{error}"
            ) from error

        shared_result = _shared_result_after_save(
            session_id=session_id,
            segment_id=segment_id,
            transcript=text,
            entities=entities,
            extraction_source=extraction_source,
            evaluation=evaluation,
        )
        presentation_evaluation = (
            {
                "missing_fields": list(shared_result.missing_fields),
                "follow_up_question": shared_result.follow_up_question,
                "follow_up_required": bool(shared_result.follow_up_question),
            }
            if shared_result is not None
            else evaluation
        )
        observation = degraded_producer.produce_partial_observation(
            request_id=self._request_id_factory(),
            session_id=session_id,
            segment_id=segment_id,
            evaluation=presentation_evaluation,
            entities=(dict(shared_result.entities) if shared_result else entities),
        )
        intents = messages_for_observation(observation)
        return SharedRecordResult(saved, shared_result, intents)

    def _recent_context(self, session_id: str, count: int = 5) -> tuple[str, ...]:
        records = self._list_records(session_id)
        return tuple(
            str(item["transcript"]).strip()
            for item in records[-count:]
            if item.get("transcript") and str(item["transcript"]).strip()
        )


def _select_effective_evaluation(
    *,
    extraction: Mapping[str, object] | None,
    protocol_evaluation: object,
    step: object,
) -> object:
    """自由模式保留统一语义追问；方案模式维持确定性评估权威。"""

    if not isinstance(protocol_evaluation, dict):
        return protocol_evaluation
    if not isinstance(step, Mapping) or step.get("mode") != "free":
        return protocol_evaluation
    if not isinstance(extraction, Mapping):
        return protocol_evaluation
    if extraction.get("degraded") is True:
        return protocol_evaluation
    if extraction.get("input_kind") not in {None, "experiment"}:
        return protocol_evaluation
    if extraction.get("should_ask_follow_up") is not True:
        return protocol_evaluation

    question = extraction.get("follow_up_question")
    if not isinstance(question, str) or not question.strip():
        return protocol_evaluation
    missing = extraction.get("missing_fields")
    if missing is None:
        missing = [
            field
            for event in extraction.get("events", ())
            if isinstance(event, Mapping)
            for field in event.get("missing_fields", ())
        ]
    if not isinstance(missing, (list, tuple)) or any(
        not isinstance(field, str) or not field.strip() for field in missing
    ):
        return protocol_evaluation

    effective = dict(protocol_evaluation)
    effective["missing_fields"] = list(dict.fromkeys(missing))
    effective["follow_up_question"] = question.strip()
    effective["follow_up_required"] = True
    return effective


def _shared_result_after_save(
    *,
    session_id: str,
    segment_id: int,
    transcript: str,
    entities: dict[str, str],
    extraction_source: str,
    evaluation: object,
) -> RecordObservationResult | None:
    if not isinstance(evaluation, dict):
        return None
    if entities:
        try:
            source = ExtractionSource(extraction_source)
        except ValueError:
            source = ExtractionSource.RULE
        if source in {ExtractionSource.DEGRADED, ExtractionSource.NONE}:
            source = ExtractionSource.RULE
        status = RecordStructureStatus.STRUCTURED
    else:
        source = ExtractionSource.DEGRADED
        status = RecordStructureStatus.DEGRADED
    try:
        return RecordObservationResult(
            session_id=session_id,
            segment_id=segment_id,
            transcript=transcript,
            entities=entities,
            extraction_source=source,
            structure_status=status,
            missing_fields=tuple(evaluation.get("missing_fields") or ()),
            follow_up_question=(
                (evaluation.get("follow_up_question") or "").strip() or None
            ),
            deviations=tuple(evaluation.get("deviations") or ()),
        )
    except (TypeError, ValueError):
        return None
