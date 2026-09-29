import json
import unittest
from unittest.mock import patch

import httpx

from src.llm.client import (
    LLMClientError,
    OpenAICompatibleLLMClient,
)


class FakeHTTPResponse:
    """模拟 httpx.Response：只需要 status_code / text / json()。"""

    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self):
        return self.payload


def make_response(
    content,
    *,
    reasoning_content=None,
    finish_reason="stop",
    status_code=200,
) -> FakeHTTPResponse:
    """构造一个符合 DeepSeek Chat Completions 格式的假响应。"""

    return FakeHTTPResponse(
        {
            "choices": [
                {
                    "message": {
                        "content": content,
                        "reasoning_content": reasoning_content,
                    },
                    "finish_reason": finish_reason,
                }
            ],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
            },
        },
        status_code=status_code,
    )


def make_client() -> OpenAICompatibleLLMClient:
    """创建测试客户端；httpx.Client.post 会被 Mock 替换，不产生真实网络请求。"""

    return OpenAICompatibleLLMClient(
        base_url="https://example.com",
        api_key="test-api-key",
        model="test-model",
        timeout_seconds=1.0,
        max_tokens=100,
        max_attempts=2,
        retry_delay_seconds=0.01,
    )


class LLMClientRetryTests(unittest.TestCase):
    @patch("src.llm.client.time.sleep")
    @patch("httpx.Client.post")
    def test_empty_response_retries_and_succeeds(self, mock_post, mock_sleep):
        """第一次返回空内容，第二次返回有效内容。"""

        mock_post.side_effect = [
            make_response(""),
            make_response('{"events": []}'),
        ]

        client = make_client()

        result = client.generate_json(
            system_prompt="输出 JSON",
            user_prompt="测试输入",
        )

        self.assertEqual(result.content, '{"events": []}')
        self.assertEqual(result.attempts, 2)
        self.assertGreaterEqual(result.processing_seconds, 0.0)
        self.assertEqual(mock_post.call_count, 2)
        mock_sleep.assert_called_once_with(0.01)

    @patch("src.llm.client.time.sleep")
    @patch("httpx.Client.post")
    def test_two_empty_responses_raise_error(self, mock_post, mock_sleep):
        """连续两次返回空内容，应抛出 LLMClientError 并记录指标。"""

        mock_post.side_effect = [
            make_response("", reasoning_content="第一次思考", finish_reason="length"),
            make_response("", reasoning_content="第二次思考", finish_reason="length"),
        ]

        client = make_client()

        with self.assertRaises(LLMClientError) as context:
            client.generate_json(
                system_prompt="输出 JSON",
                user_prompt="测试输入",
            )

        error = context.exception
        error_message = str(error)

        self.assertIn("2次尝试", error_message)
        self.assertIn("finish_reason='length'", error_message)
        self.assertIn("reasoning_length", error_message)
        self.assertEqual(error.attempts, 2)
        self.assertGreaterEqual(error.processing_seconds, 0.0)
        self.assertEqual(mock_post.call_count, 2)
        mock_sleep.assert_called_once_with(0.01)

    @patch("src.llm.client.time.sleep")
    @patch("httpx.Client.post")
    def test_timeout_retries_and_succeeds(self, mock_post, mock_sleep):
        """第一次超时（httpx.TimeoutException），第二次成功。"""

        mock_post.side_effect = [
            httpx.TimeoutException("模拟请求超时"),
            make_response('{"ok": true}'),
        ]

        client = make_client()

        result = client.generate_json(
            system_prompt="输出 JSON",
            user_prompt="测试输入",
        )

        self.assertEqual(result.content, '{"ok": true}')
        self.assertEqual(result.attempts, 2)
        self.assertGreaterEqual(result.processing_seconds, 0.0)
        self.assertEqual(mock_post.call_count, 2)
        mock_sleep.assert_called_once_with(0.01)

    @patch("src.llm.client.time.sleep")
    @patch("httpx.Client.post")
    def test_http_401_does_not_retry(self, mock_post, mock_sleep):
        """HTTP 401 属于认证错误，不应重试。"""

        mock_post.return_value = FakeHTTPResponse(
            {"error": {"message": "invalid api key"}},
            status_code=401,
        )

        client = make_client()

        with self.assertRaises(LLMClientError) as context:
            client.generate_json(
                system_prompt="输出 JSON",
                user_prompt="测试输入",
            )

        error = context.exception

        self.assertIn("HTTP 401", str(error))
        self.assertEqual(error.attempts, 1)
        self.assertGreaterEqual(error.processing_seconds, 0.0)
        self.assertEqual(mock_post.call_count, 1)
        mock_sleep.assert_not_called()

    @patch("httpx.Client.post")
    def test_request_disables_thinking_mode(self, mock_post):
        """请求必须关闭 DeepSeek 思考模式，并带上固定采样参数。"""

        mock_post.return_value = make_response('{"ok": true}')

        client = make_client()

        result = client.generate_json(
            system_prompt="输出 JSON",
            user_prompt="测试输入",
        )

        self.assertEqual(result.content, '{"ok": true}')
        self.assertEqual(result.attempts, 1)
        self.assertGreaterEqual(result.processing_seconds, 0.0)
        self.assertEqual(mock_post.call_count, 1)

        payload = mock_post.call_args.kwargs["json"]

        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(payload["temperature"], 0)
        self.assertEqual(payload["max_tokens"], 100)


if __name__ == "__main__":
    unittest.main()
