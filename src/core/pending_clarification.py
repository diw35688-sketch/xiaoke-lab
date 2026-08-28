from dataclasses import dataclass, replace
from enum import Enum


class ClarificationStatus(str, Enum):
    """待确认项的生命周期状态。"""

    ACTIVE = "active"
    DEFERRED = "deferred"
    RESOLVED = "resolved"
    EXPIRED = "expired"


@dataclass(frozen=True)
class PendingClarification:
    """
    一条可以追溯来源的待确认项。

    对象采用不可变设计。状态变化通过方法返回新对象，
    避免其他模块持有引用时看到意外的原地修改。
    """

    clarification_id: str
    display_number: int
    source_segment_id: int
    source_raw_text: str
    question: str
    missing_fields: tuple[str, ...] = ()
    requires_confirmation: bool = False
    status: ClarificationStatus = ClarificationStatus.ACTIVE
    revision: int = 1
    reply_pending: bool = True
    last_updated_segment_id: int | None = None
    protocol_id: str | None = None
    protocol_version: str | None = None
    protocol_step_number: int | None = None

    def __post_init__(self) -> None:
        if not self.clarification_id.strip():
            raise ValueError("clarification_id 不能为空。")
        if self.display_number <= 0:
            raise ValueError("display_number 必须大于 0。")
        if self.source_segment_id <= 0:
            raise ValueError("source_segment_id 必须大于 0。")
        if not self.source_raw_text.strip():
            raise ValueError("source_raw_text 不能为空。")
        if not self.question.strip():
            raise ValueError("question 不能为空。")
        if len(self.missing_fields) != len(set(self.missing_fields)):
            raise ValueError("missing_fields 不得重复。")
        if any(not field_name.strip() for field_name in self.missing_fields):
            raise ValueError("missing_fields 不能包含空字符串。")
        if (
            self.is_unresolved
            and not self.missing_fields
            and not self.requires_confirmation
        ):
            raise ValueError(
                "待确认项必须包含缺失字段或确认请求。"
            )
        if self.revision <= 0:
            raise ValueError("revision 必须大于 0。")
        if (
            self.status != ClarificationStatus.ACTIVE
            and self.reply_pending
        ):
            raise ValueError(
                "只有 ACTIVE 问题可以等待主动提问。"
            )
        protocol_scope = (
            self.protocol_id,
            self.protocol_version,
            self.protocol_step_number,
        )
        if any(value is not None for value in protocol_scope):
            if any(value is None for value in protocol_scope):
                raise ValueError("方案问题必须包含完整的方案步骤归属。")
            if not self.protocol_id.strip() or not self.protocol_version.strip():
                raise ValueError("方案问题的方案身份不能为空。")
            if self.protocol_step_number <= 0:
                raise ValueError("方案问题的步骤号必须为正整数。")

    @property
    def is_active(self) -> bool:
        return self.status == ClarificationStatus.ACTIVE

    @property
    def is_unresolved(self) -> bool:
        return self.status in {
            ClarificationStatus.ACTIVE,
            ClarificationStatus.DEFERRED,
        }

    def supply_fields(
        self,
        field_names: set[str],
        *,
        segment_id: int,
    ) -> "PendingClarification":
        """用后续段落提供的实体字段更新当前待确认项。"""

        if not self.is_unresolved or not field_names:
            return self

        remaining_fields = tuple(
            field_name
            for field_name in self.missing_fields
            if field_name not in field_names
        )

        if remaining_fields == self.missing_fields:
            return self

        if not remaining_fields and not self.requires_confirmation:
            return replace(
                self,
                missing_fields=(),
                status=ClarificationStatus.RESOLVED,
                revision=self.revision + 1,
                reply_pending=False,
                last_updated_segment_id=segment_id,
            )

        return replace(
            self,
            missing_fields=remaining_fields,
            revision=self.revision + 1,
            reply_pending=self.is_active,
            last_updated_segment_id=segment_id,
        )

    def mark_replied(self) -> "PendingClarification":
        """标记当前版本的问题已经交给表现层。"""

        if not self.is_active or not self.reply_pending:
            return self

        return replace(self, reply_pending=False)

    def defer(
        self,
        *,
        segment_id: int,
    ) -> "PendingClarification":
        """暂缓当前问题；问题仍然未解决。"""

        if segment_id <= 0:
            raise ValueError("segment_id 必须大于 0。")
        if not self.is_active:
            return self

        return replace(
            self,
            status=ClarificationStatus.DEFERRED,
            revision=self.revision + 1,
            reply_pending=False,
            last_updated_segment_id=segment_id,
        )

    def reactivate(
        self,
        *,
        segment_id: int,
    ) -> "PendingClarification":
        """将暂缓问题重新放回可提问队列。"""

        if segment_id <= 0:
            raise ValueError("segment_id 必须大于 0。")
        if self.status != ClarificationStatus.DEFERRED:
            return self

        return replace(
            self,
            status=ClarificationStatus.ACTIVE,
            revision=self.revision + 1,
            reply_pending=True,
            last_updated_segment_id=segment_id,
        )

    def expire(
        self,
        *,
        segment_id: int,
    ) -> "PendingClarification":
        """标记问题不再适用，但保留历史记录。"""

        if segment_id <= 0:
            raise ValueError("segment_id 必须大于 0。")
        if not self.is_unresolved:
            return self

        return replace(
            self,
            status=ClarificationStatus.EXPIRED,
            revision=self.revision + 1,
            reply_pending=False,
            last_updated_segment_id=segment_id,
        )

    def confirm(
        self,
        *,
        segment_id: int,
    ) -> "PendingClarification":
        """确认当前 ASR 推测，并保留仍未补充的字段。"""

        if not self.is_unresolved or not self.requires_confirmation:
            return self

        if not self.missing_fields:
            return replace(
                self,
                requires_confirmation=False,
                status=ClarificationStatus.RESOLVED,
                revision=self.revision + 1,
                reply_pending=False,
                last_updated_segment_id=segment_id,
            )

        return replace(
            self,
            requires_confirmation=False,
            revision=self.revision + 1,
            reply_pending=self.is_active,
            last_updated_segment_id=segment_id,
        )
