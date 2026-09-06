import json
import logging
import time
from dataclasses import dataclass
from typing import Protocol

import httpx


logger = logging.getLogger(__name__)


class LLMClientError(RuntimeError):
    """
    LLM客户端对外统一抛出的错误。

    失败异常也携带尝试次数和耗时，
    让降级结果可以保存运行指标。
    """

    def __init__(
        self,
        message: str,
        *,
        attempts: int = 0,
        processing_seconds: float = 0.0,
    ) -> None:
        super().__init__(message)

        self.attempts = attempts
        self.processing_seconds = (
            processing_seconds
        )


@dataclass(frozen=True)
class LLMGenerationResult:
    """
    一次成功LLM调用的结果。
    """

    content: str
    attempts: int
    processing_seconds: float

class LLMTransientError(LLMClientError):
    """
    可能通过重试恢复的临时错误。

    例如：
    - 空响应；
    - 请求超时；
    - 临时网络错误；
    - HTTP 429；
    - HTTP 5xx。
    """


class LLMClient(Protocol):
    """
    业务层依赖的最小模型接口。
    """

    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> LLMGenerationResult:
        ...


class UnavailableLLMClient:
    """
    LLM 初始化失败时使用的降级客户端。
    """

    def __init__(
        self,
        reason: str,
    ) -> None:
        self.reason = reason

    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> LLMGenerationResult:
        raise LLMClientError(
            self.reason,
            attempts=0,
            processing_seconds=0.0,
        )


class OpenAICompatibleLLMClient:
    """
    调用 OpenAI-compatible Chat Completions API。

    支持对空响应、超时、临时网络错误、
    HTTP 429 和 HTTP 5xx 进行有限重试。
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 30.0,
        max_tokens: int = 2000,
        max_attempts: int = 2,
        retry_delay_seconds: float = 0.5,
    ) -> None:
        if not base_url.strip():
            raise ValueError(
                "base_url 不能为空"
            )

        if not api_key.strip():
            raise ValueError(
                "api_key 不能为空"
            )

        if not model.strip():
            raise ValueError(
                "model 不能为空"
            )

        if timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds 必须大于 0"
            )

        if max_tokens <= 0:
            raise ValueError(
                "max_tokens 必须大于 0"
            )

        if max_attempts <= 0:
            raise ValueError(
                "max_attempts 必须大于 0"
            )

        if retry_delay_seconds < 0:
            raise ValueError(
                "retry_delay_seconds 不能小于 0"
            )

        self.endpoint = (
            f"{base_url.rstrip('/')}"
            "/chat/completions"
        )

        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.max_attempts = max_attempts
        self.retry_delay_seconds = (
            retry_delay_seconds
        )
        # 持久 HTTP 连接 + trust_env=False：跟 OpenAI SDK 一样跳过环境代理，
        # 避免 SSL 握手被代理拦截导致 UNEXPECTED_EOF。
        self._http_client = httpx.Client(
            trust_env=False,
            timeout=httpx.Timeout(timeout_seconds, connect=10),
        )

    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> LLMGenerationResult:
        """
        请求模型并返回内容及运行指标。

        processing_seconds包含：
        - 所有HTTP请求耗时；
        - 重试等待时间。

        只有LLMTransientError会触发重试。
        """

        started_at = time.perf_counter()
        last_error = None

        for attempt in range(
            1,
            self.max_attempts + 1,
        ):
            try:
                content = self._request_once(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                )

                processing_seconds = (
                    time.perf_counter()
                    - started_at
                )

                return LLMGenerationResult(
                    content=content,
                    attempts=attempt,
                    processing_seconds=round(
                        processing_seconds,
                        3,
                    ),
                )

            except LLMTransientError as error:
                last_error = error

                if attempt >= self.max_attempts:
                    break

                delay_seconds = (
                    self.retry_delay_seconds
                    * attempt
                )

                logger.warning(
                    "LLM第%s次请求发生临时错误："
                    "%s；%.2f秒后重试。",
                    attempt,
                    error,
                    delay_seconds,
                )

                time.sleep(
                    delay_seconds
                )

            except LLMClientError as error:
                processing_seconds = (
                    time.perf_counter()
                    - started_at
                )

                raise LLMClientError(
                    str(error),
                    attempts=attempt,
                    processing_seconds=round(
                        processing_seconds,
                        3,
                    ),
                ) from error

        processing_seconds = (
            time.perf_counter()
            - started_at
        )

        raise LLMClientError(
            "LLM请求在"
            f"{self.max_attempts}"
            "次尝试后仍然失败："
            f"{last_error}",
            attempts=self.max_attempts,
            processing_seconds=round(
                processing_seconds,
                3,
            ),
        ) from last_error

    def _request_once(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """
        执行一次 HTTP 请求。

        本方法不负责循环重试，只负责：
        - 构造请求；
        - 解析响应；
        - 对错误进行分类；
        - 检查 content 是否为空。
        """

        payload = {
            "model": self.model,
            "thinking": {
                "type": "disabled",
            },
            "temperature": 0,
            "max_tokens": self.max_tokens,
            "response_format": {
                "type": "json_object",
            },
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
        }
        logger.debug(
            "[LLM请求] "
            f"model={payload['model']}，"
            f"thinking.type="
            f"{payload['thinking']['type']}，"
            f"max_tokens="
            f"{payload['max_tokens']}"
        )

        try:
            response = self._http_client.post(
                self.endpoint,
                json=payload,
                headers={
                    "Authorization": (
                        f"Bearer {self.api_key}"
                    ),
                    "Content-Type": (
                        "application/json; "
                        "charset=utf-8"
                    ),
                },
            )

            if (
                response.status_code == 429
                or 500 <= response.status_code < 600
            ):
                raise LLMTransientError(
                    f"模型 HTTP {response.status_code}: "
                    f"{response.text[:500]}"
                )

            if response.status_code != 200:
                raise LLMClientError(
                    f"模型 HTTP {response.status_code}: "
                    f"{response.text[:500]}"
                )

            response_data = response.json()

            choice = (
                response_data[
                    "choices"
                ][0]
            )

            message = choice[
                "message"
            ]

            content = message.get(
                "content"
            )

            reasoning_content = (
                message.get(
                    "reasoning_content"
                )
            )

            finish_reason = (
                choice.get(
                    "finish_reason"
                )
            )

            usage = response_data.get(
                "usage",
                {},
            )

        except httpx.TimeoutException as error:
            raise LLMTransientError(
                f"模型请求超时：{error}"
            ) from error

        except (
            httpx.ConnectError,
            httpx.NetworkError,
            httpx.RemoteProtocolError,
        ) as error:
            raise LLMTransientError(
                f"模型请求失败：{error}"
            ) from error

        except json.JSONDecodeError as error:
            raise LLMClientError(
                "模型 API 返回的响应"
                "不是合法 JSON。"
            ) from error

        except (
            KeyError,
            IndexError,
            TypeError,
        ) as error:
            raise LLMClientError(
                "模型 API 响应结构无效。"
            ) from error

        if isinstance(
            reasoning_content,
            str,
        ):
            reasoning_length = len(
                reasoning_content
            )
        else:
            reasoning_length = 0
        if isinstance(content, str):
            content_length = len(content)
        else:
            content_length = 0

        logger.debug(
            "[LLM响应] "
            f"finish_reason="
            f"{finish_reason!r}，"
            f"content_length="
            f"{content_length}，"
            f"reasoning_length="
            f"{reasoning_length}，"
            f"usage={usage}"
        )
        if (
            not isinstance(content, str)
            or not content.strip()
        ):
            raise LLMTransientError(
                "模型返回内容为空，"
                f"finish_reason="
                f"{finish_reason!r}，"
                f"reasoning_length="
                f"{reasoning_length}，"
                f"usage={usage}"
            )

        return content
