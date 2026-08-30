"""SQLite source of truth and transaction boundary for unified Web Turns."""

from __future__ import annotations

import hashlib
import json
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Mapping, Sequence

from database.db import get_connection, initialize_database
from src.core.turn_input import TurnInput
from src.core.turn_request_envelope import TurnRequestEnvelope


class TurnRequestConflictError(RuntimeError):
    """A global request identity was reused with different immutable input."""


class ExperimentStateConflictError(RuntimeError):
    """Experiment session state changed after a navigation decision was made."""


@dataclass(frozen=True)
class TurnReservation:
    disposition: str
    conversation_id: str
    request_id: str
    turn_id: str
    attempt: int
    result: Mapping[str, object] | None = None
    timings: Mapping[str, object] | None = None


def canonical_request_hash(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class TurnStore:
    def __init__(
        self,
        *,
        connection_factory: Callable[[], object] = get_connection,
        clock: Callable[[], str] = _now,
    ) -> None:
        self._connection_factory = connection_factory
        self._clock = clock

    def reserve(self, turn: TurnInput, request_hash: str) -> TurnReservation:
        if not isinstance(turn, TurnInput):
            raise TypeError("turn 必须是 TurnInput。")
        if not isinstance(request_hash, str) or not request_hash.strip():
            raise ValueError("request_hash 不能为空。")
        initialize_database()
        now = self._clock()
        with closing(self._connection_factory()) as connection, connection:
            connection.execute(
                "INSERT OR IGNORE INTO conversations(id) VALUES (?)",
                (turn.conversation_id,),
            )
            row = connection.execute(
                "SELECT * FROM turn_requests WHERE request_id = ?",
                (turn.request_id,),
            ).fetchone()
            if row is None:
                connection.execute(
                    """INSERT INTO turn_requests
                       (request_id, turn_id, conversation_id, lab_session_id,
                        interaction_mode, experiment_context, mode_version,
                        input_source, raw_text, request_hash, status, attempt,
                        created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'processing', 1, ?, ?)""",
                    (
                        turn.request_id, turn.turn_id, turn.conversation_id,
                        turn.lab_session_id, turn.interaction_mode.value,
                        turn.experiment_context.value, turn.mode_version,
                        turn.input_source.value, turn.raw_text, request_hash,
                        now, now,
                    ),
                )
                return TurnReservation(
                    "new", turn.conversation_id, turn.request_id, turn.turn_id, 1
                )
            if row["request_hash"] != request_hash or row["turn_id"] != turn.turn_id:
                raise TurnRequestConflictError(
                    "同一 request_id 已绑定不同的不可变 Turn 输入。"
                )
            if row["status"] == "committed":
                return TurnReservation(
                    "committed", row["conversation_id"], row["request_id"],
                    row["turn_id"], row["attempt"],
                    json.loads(row["result_json"] or "{}"),
                    json.loads(row["timing_json"] or "{}"),
                )
            if row["status"] == "processing":
                return TurnReservation(
                    "processing", row["conversation_id"], row["request_id"],
                    row["turn_id"], row["attempt"],
                )
            attempt = int(row["attempt"]) + 1
            connection.execute(
                """UPDATE turn_requests
                   SET status='processing', attempt=?, error_code=NULL,
                       error_detail=NULL, updated_at=? WHERE request_id=?""",
                (attempt, now, turn.request_id),
            )
            return TurnReservation(
                "retry", row["conversation_id"], row["request_id"],
                row["turn_id"], attempt,
            )

    def reserve_envelope(
        self, envelope: TurnRequestEnvelope, request_hash: str
    ) -> TurnReservation:
        """Reserve an audio request before its authoritative transcript exists."""

        initialize_database()
        now = self._clock()
        with closing(self._connection_factory()) as connection, connection:
            connection.execute(
                "INSERT OR IGNORE INTO conversations(id) VALUES (?)",
                (envelope.conversation_id,),
            )
            row = connection.execute(
                "SELECT * FROM turn_requests WHERE request_id=?",
                (envelope.request_id,),
            ).fetchone()
            if row is None:
                connection.execute(
                    """INSERT INTO turn_requests
                       (request_id, turn_id, conversation_id, lab_session_id,
                        interaction_mode, experiment_context, mode_version,
                        input_source, raw_text, request_hash, status, attempt,
                        created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, 'processing', 1, ?, ?)""",
                    (
                        envelope.request_id, envelope.turn_id,
                        envelope.conversation_id, envelope.lab_session_id,
                        envelope.interaction_mode.value,
                        envelope.experiment_context.value,
                        envelope.mode_version, envelope.input_source.value,
                        request_hash, now, now,
                    ),
                )
                return TurnReservation(
                    "new", envelope.conversation_id, envelope.request_id,
                    envelope.turn_id, 1,
                )
            if row["request_hash"] != request_hash or row["turn_id"] != envelope.turn_id:
                raise TurnRequestConflictError(
                    "同一 request_id 已绑定不同音频或模式快照。"
                )
            if row["status"] == "committed":
                return TurnReservation(
                    "committed", row["conversation_id"], row["request_id"],
                    row["turn_id"], row["attempt"],
                    json.loads(row["result_json"] or "{}"),
                    json.loads(row["timing_json"] or "{}"),
                )
            if row["status"] == "processing":
                return TurnReservation(
                    "processing", row["conversation_id"], row["request_id"],
                    row["turn_id"], row["attempt"],
                )
            attempt = int(row["attempt"]) + 1
            connection.execute(
                """UPDATE turn_requests SET status='processing', attempt=?,
                   error_code=NULL, error_detail=NULL, updated_at=?
                   WHERE request_id=?""",
                (attempt, now, envelope.request_id),
            )
            return TurnReservation(
                "retry", row["conversation_id"], row["request_id"],
                row["turn_id"], attempt,
            )

    def commit(
        self,
        *,
        turn: TurnInput,
        result: Mapping[str, object],
        timings: Mapping[str, object],
        messages: Sequence[Mapping[str, object]] = (),
        lab_record: Mapping[str, object] | None = None,
        asr_evidence: Mapping[str, object] | None = None,
        experiment_events: Sequence[Mapping[str, object]] = (),
        session_state: Mapping[str, object] | None = None,
    ) -> None:
        now = self._clock()
        with closing(self._connection_factory()) as connection, connection:
            row = connection.execute(
                "SELECT status FROM turn_requests WHERE request_id=?",
                (turn.request_id,),
            ).fetchone()
            if row is None or row["status"] != "processing":
                raise RuntimeError("Turn 必须处于 processing 才能提交。")

            if asr_evidence is not None:
                connection.execute(
                    """INSERT INTO asr_evidence
                       (request_id, payload_json, audio_rel_path, audio_sha256,
                        audio_bytes, created_at) VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        turn.request_id,
                        _json(asr_evidence["payload"]),
                        str(asr_evidence["audio_rel_path"]),
                        str(asr_evidence["audio_sha256"]),
                        int(asr_evidence["audio_bytes"]),
                        now,
                    ),
                )

            for index, event in enumerate(experiment_events, start=1):
                connection.execute(
                    """INSERT INTO experiment_events
                       (request_id, event_index, event_json, created_at)
                       VALUES (?, ?, ?, ?)""",
                    (turn.request_id, index, _json(event), now),
                )

            for message in messages:
                connection.execute(
                    """INSERT INTO messages
                       (conversation_id, role, content, request_id, turn_id, block_id)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        turn.conversation_id, str(message["role"]),
                        str(message["content"]), turn.request_id, turn.turn_id,
                        str(message.get("block_id") or ""),
                    ),
                )

            if lab_record is not None:
                connection.execute(
                    """INSERT INTO lab_records
                       (session_id, segment_id, transcript, entities, extraction,
                        extraction_source, evaluation, step, at,
                        request_id, conversation_id, turn_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(lab_record["session_id"]),
                        int(lab_record["segment_id"]),
                        str(lab_record["transcript"]),
                        _json(lab_record.get("entities") or {}),
                        _json(lab_record.get("extraction"))
                        if lab_record.get("extraction") is not None else None,
                        str(lab_record.get("extraction_source") or "none"),
                        _json(lab_record.get("evaluation") or {}),
                        _json(lab_record.get("step"))
                        if lab_record.get("step") is not None else None,
                        str(lab_record["at"]), turn.request_id,
                        turn.conversation_id, turn.turn_id,
                    ),
                )

            if session_state is not None:
                expected_revision = int(session_state["revision"]) - 1
                current_row = connection.execute(
                    """SELECT revision FROM experiment_session_state
                       WHERE conversation_id=? AND lab_session_id=?""",
                    (turn.conversation_id, turn.lab_session_id),
                ).fetchone()
                current_revision = (
                    int(current_row["revision"])
                    if current_row is not None else 0
                )
                if current_revision != expected_revision:
                    raise ExperimentStateConflictError(
                        f"实验会话状态已变化（期望 {expected_revision}，"
                        f"当前 {current_revision}），本轮未提交。"
                    )
                connection.execute(
                    """INSERT INTO experiment_session_state
                       (conversation_id, lab_session_id, revision,
                        reply_coordinator_json, session_context_json,
                        protocol_step_facts_json, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(conversation_id, lab_session_id) DO UPDATE SET
                         revision=excluded.revision,
                         reply_coordinator_json=excluded.reply_coordinator_json,
                         session_context_json=excluded.session_context_json,
                         protocol_step_facts_json=excluded.protocol_step_facts_json,
                         updated_at=excluded.updated_at""",
                    (
                        turn.conversation_id, turn.lab_session_id,
                        int(session_state["revision"]),
                        _json(session_state["reply_coordinator"]),
                        _json(session_state["session_context"]),
                        _json(session_state.get("protocol_step_facts") or {}), now,
                    ),
                )

            connection.execute(
                """UPDATE turn_requests SET status='committed', raw_text=?,
                   result_json=?, timing_json=?, error_code=NULL,
                   error_detail=NULL, updated_at=?, committed_at=?
                   WHERE request_id=?""",
                (
                    turn.raw_text, _json(result), _json(timings), now, now,
                    turn.request_id,
                ),
            )

    def fail(
        self, request_id: str, *, code: str, detail: str,
        timings: Mapping[str, object]
    ) -> None:
        now = self._clock()
        with closing(self._connection_factory()) as connection, connection:
            connection.execute(
                """UPDATE turn_requests SET status='failed', error_code=?,
                   error_detail=?, timing_json=?, updated_at=?
                   WHERE request_id=? AND status='processing'""",
                (code, detail, _json(timings), now, request_id),
            )

    def diagnostics(self, request_id: str) -> dict[str, object] | None:
        with closing(self._connection_factory()) as connection:
            row = connection.execute(
                """SELECT request_id, turn_id, conversation_id, status, attempt,
                          timing_json, error_code, created_at, updated_at,
                          committed_at FROM turn_requests WHERE request_id=?""",
                (request_id,),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["timings"] = json.loads(result.pop("timing_json") or "{}")
        return result

    def update_committed_result(
        self,
        request_id: str,
        *,
        result: Mapping[str, object],
        timings: Mapping[str, object],
    ) -> None:
        """Add post-COMMIT timing marks without reopening business rows."""

        now = self._clock()
        with closing(self._connection_factory()) as connection, connection:
            cursor = connection.execute(
                """UPDATE turn_requests SET result_json=?, timing_json=?, updated_at=?
                   WHERE request_id=? AND status='committed'""",
                (_json(result), _json(timings), now, request_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("找不到已提交 Turn，无法补写最终计时。")

    def load_experiment_state(
        self, conversation_id: str, lab_session_id: str
    ) -> dict[str, object]:
        with closing(self._connection_factory()) as connection:
            row = connection.execute(
                """SELECT revision, reply_coordinator_json, session_context_json,
                          protocol_step_facts_json
                   FROM experiment_session_state
                   WHERE conversation_id=? AND lab_session_id=?""",
                (conversation_id, lab_session_id),
            ).fetchone()
            segment_row = connection.execute(
                """SELECT COALESCE(MAX(segment_id), 0), COUNT(*)
                   FROM lab_records WHERE session_id=?""",
                (lab_session_id,),
            ).fetchone()
        if row is None:
            return {
                "revision": 0,
                "reply_coordinator": {},
                "session_context": {},
                "protocol_step_facts": {},
                "next_segment_id": int(segment_row[0]) + 1,
                "experiment_step_count": int(segment_row[1]),
            }
        return {
            "revision": int(row["revision"]),
            "reply_coordinator": json.loads(row["reply_coordinator_json"]),
            "session_context": json.loads(row["session_context_json"]),
            "protocol_step_facts": json.loads(row["protocol_step_facts_json"]),
            "next_segment_id": int(segment_row[0]) + 1,
            "experiment_step_count": int(segment_row[1]),
        }

    def save_protocol_navigation(
        self,
        *,
        conversation_id: str,
        lab_session_id: str,
        expected_revision: int,
        protocol_step_facts: Mapping[str, object],
    ) -> int:
        """Persist one navigation decision with optimistic revision checking."""

        initialize_database()
        now = self._clock()
        with closing(self._connection_factory()) as connection, connection:
            connection.execute(
                "INSERT OR IGNORE INTO conversations(id) VALUES (?)",
                (conversation_id,),
            )
            row = connection.execute(
                """SELECT revision FROM experiment_session_state
                   WHERE conversation_id=? AND lab_session_id=?""",
                (conversation_id, lab_session_id),
            ).fetchone()
            actual_revision = int(row["revision"]) if row is not None else 0
            if actual_revision != expected_revision:
                raise ExperimentStateConflictError(
                    f"实验会话状态已变化（期望 {expected_revision}，"
                    f"当前 {actual_revision}）。"
                )
            next_revision = actual_revision + 1
            if row is None:
                connection.execute(
                    """INSERT INTO experiment_session_state
                       (conversation_id, lab_session_id, revision,
                        reply_coordinator_json, session_context_json,
                        protocol_step_facts_json, updated_at)
                       VALUES (?, ?, ?, '{}', '{}', ?, ?)""",
                    (
                        conversation_id,
                        lab_session_id,
                        next_revision,
                        _json(protocol_step_facts),
                        now,
                    ),
                )
            else:
                cursor = connection.execute(
                    """UPDATE experiment_session_state
                       SET revision=?, protocol_step_facts_json=?, updated_at=?
                       WHERE conversation_id=? AND lab_session_id=?
                         AND revision=?""",
                    (
                        next_revision,
                        _json(protocol_step_facts),
                        now,
                        conversation_id,
                        lab_session_id,
                        expected_revision,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ExperimentStateConflictError(
                        "实验会话状态并发变化，切步未保存。"
                    )
            connection.execute(
                "UPDATE conversations SET updated_at=? WHERE id=?",
                (now, conversation_id),
            )
        return next_revision

    def referenced_audio_paths(self) -> tuple[str, ...]:
        with closing(self._connection_factory()) as connection:
            rows = connection.execute(
                "SELECT audio_rel_path FROM asr_evidence"
            ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def load_lab_record(self, request_id: str) -> dict[str, object] | None:
        with closing(self._connection_factory()) as connection:
            row = connection.execute(
                "SELECT * FROM lab_records WHERE request_id=?", (request_id,)
            ).fetchone()
        if row is None:
            return None
        item = dict(row)
        for field in ("entities", "extraction", "evaluation", "step"):
            if item.get(field) is not None:
                item[field] = json.loads(item[field])
        return item

    def load_experiment_ledger(
        self, conversation_id: str, lab_session_id: str
    ) -> dict[str, object]:
        """Read the complete user-visible ledger for one unified experiment."""

        state = self.load_experiment_state(conversation_id, lab_session_id)
        with closing(self._connection_factory()) as connection:
            rows = connection.execute(
                """SELECT * FROM lab_records
                   WHERE conversation_id=? AND session_id=?
                   ORDER BY segment_id, id""",
                (conversation_id, lab_session_id),
            ).fetchall()
            turn_rows = connection.execute(
                """SELECT request_id, raw_text, result_json, committed_at
                   FROM turn_requests
                   WHERE conversation_id=? AND lab_session_id=?
                     AND status='committed'
                   ORDER BY committed_at, created_at, request_id""",
                (conversation_id, lab_session_id),
            ).fetchall()
        records = []
        for row in rows:
            item = dict(row)
            for field in ("entities", "extraction", "evaluation", "step"):
                if item.get(field) is not None:
                    item[field] = json.loads(item[field])
            records.append(item)
        answer_projection = self._project_clarification_answers(
            turn_rows,
            state.get("protocol_step_facts") or {},
        )
        return {
            "conversation_id": conversation_id,
            "lab_session_id": lab_session_id,
            "revision": int(state["revision"]),
            "records": records,
            "reply_coordinator": state.get("reply_coordinator") or {},
            "protocol_execution": state.get("protocol_step_facts") or {},
            "clarification_answers": answer_projection,
        }

    @staticmethod
    def _project_clarification_answers(
        turn_rows: object, protocol_execution: dict[str, object]
    ) -> dict[str, list[dict[str, object]]]:
        """Join answer Turns to questions and protocol facts without text guessing."""

        written_by_request: dict[str, list[dict[str, object]]] = {}
        raw_steps = protocol_execution.get("steps") or {}
        if isinstance(raw_steps, dict):
            for raw_step_number, raw_step in raw_steps.items():
                if not isinstance(raw_step, dict):
                    continue
                values = raw_step.get("values") or {}
                if not isinstance(values, dict):
                    continue
                for field_name, observed in values.items():
                    if not isinstance(observed, dict) or not observed.get("request_id"):
                        continue
                    request_id = str(observed["request_id"])
                    written_by_request.setdefault(request_id, []).append({
                        "field": str(field_name),
                        "value": observed.get("value"),
                        "protocol_step_number": int(raw_step_number),
                    })

        projected: dict[str, list[dict[str, object]]] = {}
        for row in turn_rows:
            result = json.loads(row["result_json"] or "{}")
            business = result.get("business") or {}
            if business.get("clarification_action") != "answer":
                continue
            turn = result.get("turn") or {}
            blocks = turn.get("blocks") or []
            card = next((
                block.get("payload") or {}
                for block in blocks
                if isinstance(block, dict)
                and block.get("type") == "confirmation_card"
                and isinstance(block.get("payload"), dict)
                and block["payload"].get("clarification_id")
            ), None)
            if card is None:
                # Old Turn data without a question identity cannot be joined safely.
                continue
            clarification_id = str(card["clarification_id"])
            request_id = str(row["request_id"])
            projected.setdefault(clarification_id, []).append({
                "request_id": request_id,
                "raw_text": row["raw_text"],
                "committed_at": row["committed_at"],
                "written_fields": written_by_request.get(request_id, []),
            })
        return projected

    def delete_experiment_session(
        self, conversation_id: str, lab_session_id: str
    ) -> tuple[str, ...]:
        """Delete one experiment ledger scope and return its committed audio paths."""

        with closing(self._connection_factory()) as connection, connection:
            rows = connection.execute(
                """SELECT e.audio_rel_path FROM asr_evidence e
                   JOIN turn_requests r ON r.request_id=e.request_id
                   WHERE r.conversation_id=? AND r.lab_session_id=?""",
                (conversation_id, lab_session_id),
            ).fetchall()
            connection.execute(
                "DELETE FROM turn_requests WHERE conversation_id=? AND lab_session_id=?",
                (conversation_id, lab_session_id),
            )
            connection.execute(
                "DELETE FROM lab_records WHERE conversation_id=? AND session_id=?",
                (conversation_id, lab_session_id),
            )
            connection.execute(
                """DELETE FROM experiment_session_state
                   WHERE conversation_id=? AND lab_session_id=?""",
                (conversation_id, lab_session_id),
            )
        return tuple(str(row[0]) for row in rows)

    def list_committed_turns(self, conversation_id: str) -> list[dict]:
        """按时间顺序列出某个会话已提交的完整 Turn（含 result blocks）。"""
        initialize_database()
        with closing(self._connection_factory()) as connection:
            rows = connection.execute(
                "SELECT request_id, turn_id, status, result_json, timing_json, created_at "
                "FROM turn_requests WHERE conversation_id=? AND status='committed' "
                "ORDER BY created_at ASC",
                (conversation_id,),
            ).fetchall()
        turns = []
        for row in rows:
            result = None
            if row["result_json"]:
                try:
                    result = json.loads(row["result_json"])
                except Exception:
                    result = None
            turns.append({
                "request_id": row["request_id"],
                "turn_id": row["turn_id"],
                "status": row["status"],
                "result": result,
                "timings": json.loads(row["timing_json"] or "{}"),
                "created_at": row["created_at"],
            })
        return turns

    def delete_conversation_turn_data(self, conversation_id: str) -> tuple[str, ...]:
        """Delete unified Turn-owned rows for a conversation, leaving unrelated tasks."""

        with closing(self._connection_factory()) as connection, connection:
            rows = connection.execute(
                """SELECT e.audio_rel_path FROM asr_evidence e
                   JOIN turn_requests r ON r.request_id=e.request_id
                   WHERE r.conversation_id=?""",
                (conversation_id,),
            ).fetchall()
            connection.execute(
                "DELETE FROM turn_requests WHERE conversation_id=?", (conversation_id,)
            )
            connection.execute(
                "DELETE FROM lab_records WHERE conversation_id=?", (conversation_id,)
            )
            connection.execute(
                "DELETE FROM experiment_session_state WHERE conversation_id=?",
                (conversation_id,),
            )
            connection.execute(
                "DELETE FROM messages WHERE conversation_id=?", (conversation_id,)
            )
        return tuple(str(row[0]) for row in rows)

    def recover_processing(self) -> int:
        now = self._clock()
        with closing(self._connection_factory()) as connection, connection:
            cursor = connection.execute(
                """UPDATE turn_requests SET status='failed',
                   error_code='INTERRUPTED_BY_RESTART',
                   error_detail='服务重启中断了未提交 Turn，可使用原 request_id 重试。',
                   updated_at=? WHERE status='processing'""",
                (now,),
            )
            return int(cursor.rowcount)
