import re
from dataclasses import asdict, dataclass, fields

from src.core.pending_clarification import (
    ClarificationStatus,
    PendingClarification,
)
from src.llm.schemas import ExperimentEntities, LLMAnalysisResult


FIELD_LABELS = {
    "action": "操作",
    "object": "对象",
    "instrument": "仪器",
    "amount_value": "体积或质量数值",
    "amount_unit": "体积或质量单位",
    "concentration": "浓度",
    "temperature": "温度",
    "duration": "时间",
    "condition": "实验条件",
    "observation": "观察现象",
}


@dataclass(frozen=True)
class CoordinatedReply:
    """协调器交给终端或未来 TTS 层的一条回复。"""

    clarification_id: str
    display_number: int
    source_segment_id: int
    source_raw_text: str
    text: str


@dataclass(frozen=True)
class ConfirmationResolution:
    """一次明确肯定答复成功匹配到待确认项后的结果。"""

    clarification_id: str
    source_segment_id: int
    answer_segment_id: int
    answer_raw_text: str
    fully_resolved: bool
    remaining_fields: tuple[str, ...]


@dataclass(frozen=True)
class PreparedConfirmation:
    """尚未提交的确认计划；创建它不会修改协调器状态。"""

    clarification_id: str
    source_segment_id: int
    answer_segment_id: int
    answer_raw_text: str
    fully_resolved: bool
    remaining_fields: tuple[str, ...]
    expected_revision: int


class ReplyCoordinator:
    """
    管理一次实验会话中的待确认项。

    ingest_analysis 只接收结构化数据，不访问麦克风、文件或模型。
    pop_next_reply 每次最多返回一条回复，由主流程决定何时展示或播放。
    """

    def __init__(self) -> None:
        self._clarifications: list[PendingClarification] = []
        self._next_display_number = 1
        self._current_clarification_id: str | None = None

    def to_snapshot(self) -> dict[str, object]:
        """Return a JSON-safe complete state snapshot for transactional storage."""

        items = []
        for clarification in self._clarifications:
            item = asdict(clarification)
            item["status"] = clarification.status.value
            item["missing_fields"] = list(clarification.missing_fields)
            items.append(item)
        return {
            "clarifications": items,
            "next_display_number": self._next_display_number,
            "current_clarification_id": self._current_clarification_id,
        }

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, object]) -> "ReplyCoordinator":
        """Restore only snapshots produced by ``to_snapshot``."""

        from src.core.pending_clarification import ClarificationStatus

        coordinator = cls()
        raw_items = snapshot.get("clarifications", [])
        if not isinstance(raw_items, list):
            raise ValueError("clarifications 快照必须是列表。")
        restored = []
        for raw in raw_items:
            if not isinstance(raw, dict):
                raise ValueError("clarification 快照必须是对象。")
            item = dict(raw)
            item["missing_fields"] = tuple(item.get("missing_fields") or ())
            item["status"] = ClarificationStatus(item.get("status", "active"))
            restored.append(PendingClarification(**item))
        coordinator._clarifications = restored
        coordinator._next_display_number = int(
            snapshot.get("next_display_number", len(restored) + 1)
        )
        current = snapshot.get("current_clarification_id")
        coordinator._current_clarification_id = (
            str(current) if current is not None else None
        )
        return coordinator

    def ingest_analysis(
        self,
        *,
        segment_id: int,
        raw_text: str,
        analysis: LLMAnalysisResult,
        target_clarification_id: str | None = None,
        confirms_target_suggestion: bool = False,
    ) -> None:
        """先用当前结果更新旧问题，再登记当前段的新问题。"""

        if segment_id <= 0:
            raise ValueError("segment_id 必须大于 0。")
        if not raw_text.strip():
            raise ValueError("raw_text 不能为空。")

        supplied_fields = self._collect_supplied_fields(analysis)
        self._apply_supplied_fields(
            supplied_fields,
            segment_id=segment_id,
            target_clarification_id=target_clarification_id,
        )

        if (
            target_clarification_id is not None
            and confirms_target_suggestion
        ):
            self._confirm_target(
                target_clarification_id,
                segment_id=segment_id,
            )

        if (
            target_clarification_id is None
            and analysis.should_ask_follow_up
        ):
            self._register_clarification(
                segment_id=segment_id,
                raw_text=raw_text,
                analysis=analysis,
            )

    def pop_next_reply(self) -> CoordinatedReply | None:
        """按来源段号选择一条尚未播报的最早问题。"""

        candidates = [
            clarification
            for clarification in self._clarifications
            if clarification.is_active and clarification.reply_pending
        ]

        if not candidates:
            return None

        selected = min(
            candidates,
            key=lambda item: item.source_segment_id,
        )

        index = self._clarifications.index(selected)
        self._clarifications[index] = selected.mark_replied()
        self._current_clarification_id = selected.clarification_id

        return CoordinatedReply(
            clarification_id=selected.clarification_id,
            display_number=selected.display_number,
            source_segment_id=selected.source_segment_id,
            source_raw_text=selected.source_raw_text,
            text=self._build_reply_text(selected),
        )

    def active_clarifications(self) -> tuple[PendingClarification, ...]:
        """返回全部未解决项，兼容现有会话收尾调用。"""

        return tuple(
            clarification
            for clarification in self._clarifications
            if clarification.is_unresolved
        )

    def all_clarifications(self) -> tuple[PendingClarification, ...]:
        """返回含已解决/已过期项的完整问题账本。"""

        return tuple(self._clarifications)

    def find_unresolved_by_display_number(
        self,
        display_number: int,
    ) -> PendingClarification | None:
        """按用户看到的稳定编号查找未解决问题。"""

        if display_number <= 0:
            return None

        for clarification in self._clarifications:
            if (
                clarification.display_number == display_number
                and clarification.is_unresolved
            ):
                return clarification

        return None

    def current_clarification(self) -> PendingClarification | None:
        """返回最近一次交给用户的、仍处于 ACTIVE 的问题。"""

        for clarification in self._clarifications:
            if (
                clarification.clarification_id
                == self._current_clarification_id
                and clarification.is_active
            ):
                return clarification

        return None

    def register_clarification(
        self,
        *,
        segment_id: int,
        raw_text: str,
        question: str,
        missing_fields: tuple[str, ...] = (),
        requires_confirmation: bool = False,
        clarification_id_prefix: str = "segment",
        protocol_id: str | None = None,
        protocol_version: str | None = None,
        protocol_step_number: int | None = None,
    ) -> PendingClarification:
        """从已有字段直接创建一个待确认问题，不从 LLMAnalysisResult 推导。"""

        if segment_id <= 0:
            raise ValueError("segment_id 必须大于 0。")
        if not raw_text.strip():
            raise ValueError("raw_text 不能为空。")
        if not question or not question.strip():
            raise ValueError("question 不能为空。")
        if not missing_fields and not requires_confirmation:
            raise ValueError(
                "missing_fields 和 requires_confirmation 至少需要一个。"
            )

        clarification = PendingClarification(
            clarification_id=f"{clarification_id_prefix}-{segment_id}",
            display_number=self._next_display_number,
            source_segment_id=segment_id,
            source_raw_text=raw_text,
            question=question,
            missing_fields=missing_fields,
            requires_confirmation=requires_confirmation,
            protocol_id=protocol_id,
            protocol_version=protocol_version,
            protocol_step_number=protocol_step_number,
        )
        self._clarifications.append(clarification)
        self._next_display_number += 1
        # 新问题创建即"当前问题"：统一链创建后立即显示给用户，
        # 后续"这个问题先跳过/是/不是"都应能定位到它。
        self._current_clarification_id = clarification.clarification_id
        return clarification

    def defer_clarification(
        self,
        *,
        clarification_id: str,
        expected_revision: int,
        segment_id: int,
    ) -> PendingClarification:
        """按 clarification_id 暂缓一个 ACTIVE 问题；版本不匹配则拒绝。"""

        target = self._find_clarification(clarification_id)
        if target is None:
            raise ValueError(f"未找到待确认项：{clarification_id}")
        if target.revision != expected_revision:
            raise ValueError(
                f"待确认项版本已变更（期望 {expected_revision}，"
                f"当前 {target.revision}），拒绝过期暂缓。"
            )
        if not target.is_active:
            raise ValueError("只能暂缓 ACTIVE 状态的待确认项。")

        updated = target.defer(segment_id=segment_id)
        index = self._clarifications.index(target)
        self._clarifications[index] = updated
        if self._current_clarification_id == clarification_id:
            self._current_clarification_id = None
        return updated

    def confirm_clarification(
        self,
        *,
        clarification_id: str,
        expected_revision: int,
        segment_id: int,
        supplied_fields: set[str] | None = None,
    ) -> PendingClarification:
        """按 clarification_id 确认一个需要确认的问题；版本不匹配则拒绝。

        supplied_fields 非空时先填缺失字段再清除确认标志（确认+补充实体）。
        """

        target = self._find_clarification(clarification_id)
        if target is None:
            raise ValueError(f"未找到待确认项：{clarification_id}")
        if target.revision != expected_revision:
            raise ValueError(
                f"待确认项版本已变更（期望 {expected_revision}，"
                f"当前 {target.revision}），拒绝过期确认。"
            )
        if not target.is_active:
            raise ValueError("只能确认 ACTIVE 状态的待确认项。")
        if not target.requires_confirmation:
            raise ValueError("待确认项不需要确认。")

        updated = target
        if supplied_fields:
            updated = updated.supply_fields(
                supplied_fields, segment_id=segment_id
            )
        updated = updated.confirm(segment_id=segment_id)
        index = self._clarifications.index(target)
        self._clarifications[index] = updated
        return updated

    def answer_clarification(
        self,
        *,
        clarification_id: str,
        expected_revision: int,
        segment_id: int,
        supplied_fields: set[str],
    ) -> PendingClarification:
        """用 ANSWER 携带的实体字段填充目标问题的 missing_fields。"""

        target = self._find_clarification(clarification_id)
        if target is None:
            raise ValueError(f"未找到待确认项：{clarification_id}")
        if target.revision != expected_revision:
            raise ValueError(
                f"待确认项版本已变更（期望 {expected_revision}，"
                f"当前 {target.revision}），拒绝过期答复。"
            )
        if not target.is_active:
            raise ValueError("只能答复 ACTIVE 状态的待确认项。")
        if not supplied_fields:
            raise ValueError("supplied_fields 不能为空。")

        updated = target.supply_fields(supplied_fields, segment_id=segment_id)
        if updated == target:
            return target  # 没有字段匹配，不修改

        index = self._clarifications.index(target)
        self._clarifications[index] = updated
        return updated

    def _find_clarification(
        self,
        clarification_id: str,
    ) -> PendingClarification | None:
        """按 clarification_id 查找，列表很小不需要索引。"""

        for clarification in self._clarifications:
            if clarification.clarification_id == clarification_id:
                return clarification
        return None

    def find_clarification(
        self,
        clarification_id: str,
    ) -> PendingClarification | None:
        """公开查找接口：按 id 返回澄清对象（含已解决的）。

        供主流程持久化确认记录等场景读取澄清信息，
        不修改任何状态。
        """

        return self._find_clarification(clarification_id)

    def defer_current(
        self,
        *,
        segment_id: int,
    ) -> PendingClarification | None:
        """暂缓当前问题；没有当前问题时不猜测目标。"""

        current = self.current_clarification()
        if current is None:
            return None

        updated = current.defer(segment_id=segment_id)
        index = self._clarifications.index(current)
        self._clarifications[index] = updated
        self._current_clarification_id = None
        return updated

    def reactivate_question(
        self,
        *,
        display_number: int,
        segment_id: int,
    ) -> PendingClarification | None:
        """按稳定显示编号重新激活一条暂缓问题。"""

        for index, clarification in enumerate(self._clarifications):
            if clarification.display_number != display_number:
                continue

            updated = clarification.reactivate(
                segment_id=segment_id
            )
            self._clarifications[index] = updated
            return updated if updated != clarification else None

        return None

    def reactivate_clarification(
        self,
        *,
        clarification_id: str,
        expected_revision: int,
        segment_id: int,
    ) -> PendingClarification:
        """按不可变身份和版本恢复一条 DEFERRED 问题。"""

        target = self._find_clarification(clarification_id)
        if target is None:
            raise ValueError(f"未找到待确认项：{clarification_id}")
        if target.revision != expected_revision:
            raise ValueError(
                f"待确认项版本已变更（期望 {expected_revision}，"
                f"当前 {target.revision}），拒绝过期恢复。"
            )
        if target.status != ClarificationStatus.DEFERRED:
            raise ValueError("只能恢复 DEFERRED 状态的待确认项。")

        updated = target.reactivate(segment_id=segment_id)
        index = self._clarifications.index(target)
        self._clarifications[index] = updated
        self._current_clarification_id = updated.clarification_id
        return updated

    def try_confirm_oldest(
        self,
        *,
        segment_id: int,
        raw_text: str,
    ) -> ConfirmationResolution | None:
        """
        用明确肯定答复确认最早的 ASR 错词待确认项。

        返回 None 表示：
        - 当前没有 ASR 确认项；或
        - 文本不是受支持的明确肯定答复。
        """

        prepared = self.prepare_confirmation(
            segment_id=segment_id,
            raw_text=raw_text,
        )

        if prepared is None:
            return None

        return self.commit_confirmation(
            prepared
        )

    def prepare_confirmation(
        self,
        *,
        segment_id: int,
        raw_text: str,
    ) -> PreparedConfirmation | None:
        """计算确认结果，但不修改任何待确认状态。"""

        if segment_id <= 0:
            raise ValueError("segment_id 必须大于 0。")
        if not raw_text.strip():
            raise ValueError("raw_text 不能为空。")
        if not self._is_affirmative_answer(raw_text):
            return None

        candidates = [
            clarification
            for clarification in self._clarifications
            if (
                clarification.is_active
                and clarification.requires_confirmation
                and clarification.source_segment_id < segment_id
            )
        ]

        if not candidates:
            return None

        selected = min(
            candidates,
            key=lambda item: item.source_segment_id,
        )
        preview = selected.confirm(
            segment_id=segment_id
        )

        return PreparedConfirmation(
            clarification_id=selected.clarification_id,
            source_segment_id=selected.source_segment_id,
            answer_segment_id=segment_id,
            answer_raw_text=raw_text,
            fully_resolved=not preview.is_active,
            remaining_fields=preview.missing_fields,
            expected_revision=selected.revision,
        )

    def commit_confirmation(
        self,
        prepared: PreparedConfirmation,
    ) -> ConfirmationResolution:
        """在外部保存成功后，提交已经准备好的状态变化。"""

        matches = [
            clarification
            for clarification in self._clarifications
            if clarification.clarification_id == prepared.clarification_id
        ]

        if not matches:
            raise ValueError(
                "待提交的确认项已经不存在。"
            )

        selected = matches[0]

        if (
            not selected.is_active
            or not selected.requires_confirmation
            or selected.revision != prepared.expected_revision
        ):
            raise ValueError(
                "待确认项状态已经变化，不能提交旧确认计划。"
            )

        updated = selected.confirm(
            segment_id=prepared.answer_segment_id
        )
        index = self._clarifications.index(selected)
        self._clarifications[index] = updated

        return ConfirmationResolution(
            clarification_id=updated.clarification_id,
            source_segment_id=updated.source_segment_id,
            answer_segment_id=prepared.answer_segment_id,
            answer_raw_text=prepared.answer_raw_text,
            fully_resolved=not updated.is_active,
            remaining_fields=updated.missing_fields,
        )

    def _apply_supplied_fields(
        self,
        supplied_fields: set[str],
        *,
        segment_id: int,
        target_clarification_id: str | None = None,
    ) -> None:
        updated_items = []

        for clarification in self._clarifications:
            matches_target = (
                target_clarification_id is None
                or clarification.clarification_id
                == target_clarification_id
            )
            if (
                matches_target
                and clarification.source_segment_id < segment_id
            ):
                clarification = clarification.supply_fields(
                    supplied_fields,
                    segment_id=segment_id,
                )

            updated_items.append(clarification)

        self._clarifications = updated_items

    def _confirm_target(
        self,
        clarification_id: str,
        *,
        segment_id: int,
    ) -> None:
        """用指定编号答复中的明确肯定语句确认原ASR推测。"""

        for index, clarification in enumerate(self._clarifications):
            if clarification.clarification_id != clarification_id:
                continue

            self._clarifications[index] = clarification.confirm(
                segment_id=segment_id
            )
            return

    def _register_clarification(
        self,
        *,
        segment_id: int,
        raw_text: str,
        analysis: LLMAnalysisResult,
    ) -> None:
        question = analysis.follow_up_question

        if not question or not question.strip():
            raise ValueError(
                "需要追问时 follow_up_question 不能为空。"
            )

        missing_fields = tuple(
            dict.fromkeys(
                field_name
                for event in analysis.events
                for field_name in event.missing_fields
            )
        )
        requires_confirmation = any(
            event.needs_confirmation
            for event in analysis.events
        )

        self.register_clarification(
            segment_id=segment_id,
            raw_text=raw_text,
            question=question,
            missing_fields=missing_fields,
            requires_confirmation=requires_confirmation,
        )

    @staticmethod
    def _collect_supplied_fields(
        analysis: LLMAnalysisResult,
    ) -> set[str]:
        supplied_fields: set[str] = set()

        for event in analysis.events:
            for entity_field in fields(ExperimentEntities):
                value = getattr(event.entities, entity_field.name)

                if isinstance(value, str) and value.strip():
                    supplied_fields.add(entity_field.name)

        return supplied_fields

    @staticmethod
    def _build_reply_text(
        clarification: PendingClarification,
    ) -> str:
        source = (
            f"关于第 {clarification.source_segment_id} 段"
            f"“{clarification.source_raw_text}”"
        )

        if clarification.revision == 1:
            question = clarification.question
        elif clarification.missing_fields:
            labels = [
                FIELD_LABELS.get(field_name, field_name)
                for field_name in clarification.missing_fields
            ]
            question = "仍需确认：" + "、".join(labels) + "。"
        else:
            question = clarification.question

        return f"{source}：{question}"

    @staticmethod
    def _is_affirmative_answer(
        raw_text: str,
    ) -> bool:
        """保守识别不会与普通实验操作混淆的肯定答复。"""

        normalized = re.sub(
            r"[\s，。！？、,.!?；;：:]",
            "",
            raw_text,
        )

        exact_answers = {
            "是",
            "是的",
            "对",
            "对的",
            "正确",
            "没错",
            "确认",
        }

        if normalized in exact_answers:
            return True

        safe_prefixes = (
            "是的是",
            "没错是",
            "确认是",
        )

        return normalized.startswith(
            safe_prefixes
        )
