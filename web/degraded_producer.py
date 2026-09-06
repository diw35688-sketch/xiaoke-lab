# -*- coding: utf-8 -*-
"""web 降级生产者：把确定性评估结果翻译成部分 UnifiedObservation。

降级生产者契约（docs/VOICE_WEB_MIGRATION_PLAN.md B1）：
确定性、不调 LLM、不改输入、不托管有状态会话。它只做一件事——
把 web 现有薄字典评估（domain.evaluate 的 evaluation dict）翻译成
统一输出层认识的"部分观察"，让投影层/渲染层零改动即可消费。
"""

from __future__ import annotations

import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    REPO_ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
else:
    REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.unified_dispatch import UnifiedDispatchDestination  # noqa: E402
from src.core.unified_observer import (  # noqa: E402
    UnifiedObservation,
    UnifiedObservationStatus,
)

DEGRADED_NOTE = "degraded_evidence_note"
PARTIAL_RECORDED = "partial_recorded"


def produce_partial_observation(
    *,
    request_id: str,
    session_id: str,
    segment_id: int,
    evaluation: dict,
    entities: dict | None = None,
) -> UnifiedObservation:
    """把 evaluation 翻译成部分观察；畸形输入一律降级为 FAILED 观察。

    - 有非空追问文本 → 追问部分观察（CLARIFICATION_CONTEXT / acceptance_kind=None）
    - 无追问且抽到实体 → 记录成功部分观察（EXPERIMENT_PIPELINE / partial_recorded）
    - 无追问且未抽到实体 → 降级部分观察（EXPERIMENT_PIPELINE / degraded_evidence_note）
    - evaluation 非 dict 或读取异常 → FAILED 观察（走现有失败投影）

    "要不要追问"以追问文本非空为准（投影层消费的是 partial_question，
    判定必须与投影分支同源，避免 follow_up_required 与空文本的矛盾状态）；
    follow_up_required 字段仍如实抄录，不参与判定。
    无追问时 acceptance_kind 区分"结构化成功（已记录）"与"真降级（不可用）"，
    避免"结构化成功却说不可用"的话术撒谎（真实验收发现的硬问题）。
    """
    try:
        if not isinstance(evaluation, dict):
            raise TypeError("evaluation 必须是 dict。")
        question = (evaluation.get("follow_up_question") or "").strip()
        is_followup = bool(question)
        if is_followup:
            acceptance_kind = None
        elif entities:
            acceptance_kind = PARTIAL_RECORDED
        else:
            acceptance_kind = DEGRADED_NOTE
        return UnifiedObservation(
            request_id=request_id,
            session_id=session_id,
            segment_id=segment_id,
            status=UnifiedObservationStatus.OBSERVED,
            partial=True,
            destination=(
                UnifiedDispatchDestination.CLARIFICATION_CONTEXT.value
                if is_followup
                else UnifiedDispatchDestination.EXPERIMENT_PIPELINE.value
            ),
            acceptance_kind=acceptance_kind,
            missing_fields=tuple(evaluation.get("missing_fields") or ()),
            follow_up_required=bool(evaluation.get("follow_up_required")),
            partial_question=question if is_followup else None,
        )
    except Exception as error:
        return UnifiedObservation(
            request_id=request_id,
            session_id=session_id,
            segment_id=segment_id,
            status=UnifiedObservationStatus.FAILED,
            error_type=type(error).__name__,
        )
