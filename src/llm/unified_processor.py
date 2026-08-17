"""调用LLM并生成正式统一理解结果。"""

from __future__ import annotations

import logging

from src.core.unified_prompts import (
    UNIFIED_UNDERSTANDING_SYSTEM_PROMPT,
    build_unified_understanding_user_prompt,
)
from src.core.unified_understanding import (
    UnifiedUnderstandingError,
    UnifiedUnderstandingInput,
    UnifiedUnderstandingResult,
    build_degraded_understanding,
    parse_unified_understanding,
)
from src.llm.client import LLMClient, LLMClientError
from src.llm.processor import ProcessOutcome

logger = logging.getLogger(__name__)


class UnifiedUnderstandingProcessor:
    """负责一次模型调用、严格解析、指标记录和安全降级。"""

    def __init__(self, client: LLMClient) -> None:
        self._client = client

    def understand(
        self,
        request: UnifiedUnderstandingInput,
    ) -> ProcessOutcome[UnifiedUnderstandingResult]:
        generation = None
        try:
            generation = self._client.generate_json(
                system_prompt=UNIFIED_UNDERSTANDING_SYSTEM_PROMPT,
                user_prompt=build_unified_understanding_user_prompt(request),
            )
            result = parse_unified_understanding(
                generation.content,
                expected_raw_text=request.raw_text,
                session_id=request.session_id,
                segment_id=request.segment_id,
            )
            return ProcessOutcome(
                value=result,
                degraded=False,
                error=None,
                llm_attempts=generation.attempts,
                llm_processing_seconds=generation.processing_seconds,
            )
        except (LLMClientError, UnifiedUnderstandingError) as error:
            # 预期内失败：外部服务不可用或模型输出违反合同。
            # 这是设计好的降级路径，安静处理。
            return self._degrade(request, generation, error)
        except Exception as error:
            # 预期外失败：走到这里说明本模块存在缺陷，
            # 而不是外部环境的问题。仍然降级以保护主流程，
            # 但必须显式暴露，否则代码缺陷会被伪装成网络故障。
            logger.error(
                "[统一理解] 非契约异常，疑似代码缺陷：%s: %s",
                type(error).__name__,
                error,
                exc_info=True,
            )
            return self._degrade(request, generation, error)

    def _degrade(
        self,
        request: UnifiedUnderstandingInput,
        generation,
        error: Exception,
    ) -> ProcessOutcome[UnifiedUnderstandingResult]:
        """统一的降级出口：保存未分类NOTE并带回真实指标。"""

        attempts, seconds = self._read_metrics(generation, error)
        reason = f"{type(error).__name__}: {error}"
        return ProcessOutcome(
            value=build_degraded_understanding(
                raw_text=request.raw_text,
                session_id=request.session_id,
                segment_id=request.segment_id,
                reason=reason,
            ),
            degraded=True,
            error=reason,
            llm_attempts=attempts,
            llm_processing_seconds=seconds,
        )

    @staticmethod
    def _read_metrics(generation, error: Exception) -> tuple[int, float]:
        if generation is not None:
            return generation.attempts, generation.processing_seconds
        return (
            int(getattr(error, "attempts", 0)),
            float(getattr(error, "processing_seconds", 0.0)),
        )
