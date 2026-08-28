"""安全分派计划交给执行边界时使用的请求与结果合同。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from src.asr.schemas import ASRResult
from src.core.unified_dispatch import (
    UnifiedDispatchDestination,
    UnifiedDispatchPermission,
    UnifiedDispatchPlan,
    required_permission_for,
)


class DispatchExecutionStatus(str, Enum):
    """执行边界对一份请求作出的最终报告。"""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    FAILED = "failed"
    NO_ACTION = "no_action"


@dataclass(frozen=True)
class DispatchExecutionRequest:
    """带可信身份、原文和可选 ASR 证据的分派执行请求。"""

    request_id: str
    session_id: str
    segment_id: int
    asr_evidence: ASRResult | None
    plan: UnifiedDispatchPlan
    raw_text: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.request_id, "request_id")
        _require_text(self.session_id, "session_id")
        if self.segment_id <= 0 or isinstance(self.segment_id, bool):
            raise ValueError("segment_id必须是正整数。")
        raw_text = self.raw_text
        if raw_text is None and self.asr_evidence is not None:
            raw_text = self.asr_evidence.asr_transcript
            object.__setattr__(self, "raw_text", raw_text)
        _require_text(raw_text, "raw_text")
        if self.asr_evidence is not None:
            if not self.asr_evidence.is_final:
                raise ValueError("执行请求只接受最终ASR证据。")
            if self.asr_evidence.asr_transcript != raw_text:
                raise ValueError("ASR证据与请求原文不一致。")
        if raw_text != self.plan.asr_transcript:
            raise ValueError("执行请求原文与分派计划原文不一致。")

    @property
    def destination(self) -> UnifiedDispatchDestination:
        return self.plan.destination

    @property
    def permission(self) -> UnifiedDispatchPermission:
        return self.plan.permission


@dataclass(frozen=True)
class DispatchExecutionResult:
    """执行边界的可审计结果，不把“接收”冒充为“已产生副作用”。"""

    request_id: str
    session_id: str
    segment_id: int
    destination: UnifiedDispatchDestination
    permission: UnifiedDispatchPermission
    status: DispatchExecutionStatus
    state_changed: bool
    persisted: bool
    reason: str
    produced_message_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.request_id, "request_id")
        _require_text(self.session_id, "session_id")
        _require_text(self.reason, "reason")
        if self.segment_id <= 0 or isinstance(self.segment_id, bool):
            raise ValueError("segment_id必须是正整数。")
        if not isinstance(self.state_changed, bool):
            raise TypeError("state_changed必须是布尔值。")
        if not isinstance(self.persisted, bool):
            raise TypeError("persisted必须是布尔值。")
        if self.permission != required_permission_for(self.destination):
            raise ValueError("执行结果的分派目标与最小权限不匹配。")
        if not isinstance(self.produced_message_ids, tuple):
            raise TypeError("produced_message_ids必须是tuple。")
        if len(self.produced_message_ids) != len(set(self.produced_message_ids)):
            raise ValueError("produced_message_ids不得重复。")
        for message_id in self.produced_message_ids:
            _require_text(message_id, "produced_message_ids元素")
        if (
            self.status != DispatchExecutionStatus.ACCEPTED
            and (
                self.state_changed
                or self.persisted
                or self.produced_message_ids
            )
        ):
            raise ValueError("未接受的请求不能声称已产生副作用或消息。")
        if (
            self.status == DispatchExecutionStatus.NO_ACTION
            and self.permission != UnifiedDispatchPermission.NO_ACTION
        ):
            raise ValueError("只有NO_ACTION权限可以返回no_action。")
        if (
            self.permission == UnifiedDispatchPermission.NO_ACTION
            and self.status != DispatchExecutionStatus.NO_ACTION
        ):
            raise ValueError("NO_ACTION权限必须返回no_action。")

    @classmethod
    def from_request(
        cls,
        request: DispatchExecutionRequest,
        *,
        status: DispatchExecutionStatus,
        reason: str,
        state_changed: bool = False,
        persisted: bool = False,
        produced_message_ids: tuple[str, ...] = (),
    ) -> "DispatchExecutionResult":
        return cls(
            request_id=request.request_id,
            session_id=request.session_id,
            segment_id=request.segment_id,
            destination=request.destination,
            permission=request.permission,
            status=status,
            state_changed=state_changed,
            persisted=persisted,
            reason=reason,
            produced_message_ids=produced_message_ids,
        )


class DispatchExecutor(Protocol):
    """未来真实下游必须遵守的最小执行接口。"""

    def execute(
        self,
        request: DispatchExecutionRequest,
    ) -> DispatchExecutionResult: ...


class FakeDispatchExecutor:
    """只在内存报告结果的Fake；不连接任何真实副作用服务。"""

    def __init__(
        self,
        *,
        accepted_permissions: frozenset[UnifiedDispatchPermission] = (
            frozenset()
        ),
        failing_request_ids: frozenset[str] = frozenset(),
    ) -> None:
        self._accepted_permissions = accepted_permissions
        self._failing_request_ids = failing_request_ids
        self._handled: dict[
            str,
            tuple[DispatchExecutionRequest, DispatchExecutionResult],
        ] = {}
        self.execution_attempts = 0

    def execute(
        self,
        request: DispatchExecutionRequest,
    ) -> DispatchExecutionResult:
        previous = self._handled.get(request.request_id)
        if previous is not None:
            previous_request, previous_result = previous
            if previous_request != request:
                raise ValueError("同一request_id不能代表不同执行请求。")
            return previous_result

        self.execution_attempts += 1
        if request.permission == UnifiedDispatchPermission.NO_ACTION:
            result = DispatchExecutionResult.from_request(
                request,
                status=DispatchExecutionStatus.NO_ACTION,
                reason="分派合同明确要求不执行任何动作。",
            )
        elif request.request_id in self._failing_request_ids:
            result = DispatchExecutionResult.from_request(
                request,
                status=DispatchExecutionStatus.FAILED,
                reason="Fake执行边界模拟内部失败。",
            )
        elif request.permission not in self._accepted_permissions:
            result = DispatchExecutionResult.from_request(
                request,
                status=DispatchExecutionStatus.REJECTED,
                reason="Fake执行边界没有被授予该最小权限。",
            )
        else:
            result = DispatchExecutionResult.from_request(
                request,
                status=DispatchExecutionStatus.ACCEPTED,
                reason="Fake执行边界接受请求，但未产生真实副作用。",
            )

        self._handled[request.request_id] = (request, result)
        return result


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name}不能为空。")
