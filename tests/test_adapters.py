from unittest.mock import MagicMock, patch

import httpx
import pytest

from adapters.base import ModelAdapter, StructuredOutputRejectedError
from adapters.openai_compat import OpenAICompatAdapter


def test_model_adapter_abstract_methods():
    class ConcreteAdapter(ModelAdapter):
        def chat(self, messages, system=None, timeout=120):
            return "test response"

        def batch_chat(self, requests, max_concurrency=5):
            return ["test response"]

    adapter = ConcreteAdapter()
    assert adapter.chat([]) == "test response"
    assert adapter.batch_chat([]) == ["test response"]


def test_openai_compat_adapter_initialization():
    adapter = OpenAICompatAdapter(
        base_url="https://api.openai.com",
        api_key="test-key",
        model="gpt-4",
        fallback_model="gpt-3.5",
        rpm_limit=100,
    )

    assert adapter.base_url == "https://api.openai.com"
    assert adapter.api_key == "test-key"
    assert adapter.model == "gpt-4"
    assert adapter.fallback_model == "gpt-3.5"
    assert isinstance(adapter.client, httpx.Client)


def test_openai_compat_fallback_model():
    adapter = OpenAICompatAdapter(
        base_url="https://api.openai.com",
        api_key="test-key",
        model="primary-model",
        fallback_model="fallback-model",
    )

    assert adapter.model == "primary-model"
    assert adapter.fallback_model == "fallback-model"


def test_openai_compat_chat_sync():
    adapter = OpenAICompatAdapter(
        base_url="https://api.openai.com",
        api_key="test-key",
        model="gpt-4",
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": [{"message": {"content": "sync response"}}]}

    with patch.object(adapter.client, "post", return_value=mock_response):
        result = adapter.chat([{"role": "user", "content": "Hello"}])
        assert result == "sync response"


def test_openai_compat_chat_with_usage():
    adapter = OpenAICompatAdapter(
        base_url="https://api.openai.com",
        api_key="test-key",
        model="gpt-4",
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "response with usage"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }

    with patch.object(adapter.client, "post", return_value=mock_response):
        content, usage = adapter.chat_with_usage([{"role": "user", "content": "Hello"}])
        assert content == "response with usage"
        assert usage["prompt_tokens"] == 10
        assert usage["total_tokens"] == 30


def test_openai_compat_chat_401_error():
    adapter = OpenAICompatAdapter(
        base_url="https://api.openai.com",
        api_key="invalid-key",
        model="gpt-4",
    )

    mock_response = MagicMock()
    mock_response.status_code = 401

    with patch.object(adapter.client, "post", return_value=mock_response):
        with pytest.raises(RuntimeError, match="Invalid API key"):
            adapter.chat([{"role": "user", "content": "Hello"}])


def test_openai_compat_chat_404_error():
    adapter = OpenAICompatAdapter(
        base_url="https://api.openai.com",
        api_key="test-key",
        model="nonexistent-model",
    )

    mock_response = MagicMock()
    mock_response.status_code = 404

    with patch.object(adapter.client, "post", return_value=mock_response):
        with pytest.raises(RuntimeError, match="Model not found"):
            adapter.chat([{"role": "user", "content": "Hello"}])


def test_openai_compat_chat_429_error():
    adapter = OpenAICompatAdapter(
        base_url="https://api.openai.com",
        api_key="test-key",
        model="gpt-4",
    )

    mock_response = MagicMock()
    mock_response.status_code = 429

    with patch.object(adapter.client, "post", return_value=mock_response):
        with pytest.raises(RuntimeError, match="Insufficient quota"):
            adapter.chat([{"role": "user", "content": "Hello"}])


def test_openai_compat_batch_chat():
    adapter = OpenAICompatAdapter(
        base_url="https://api.openai.com",
        api_key="test-key",
        model="gpt-4",
    )

    call_count = [0]
    responses = ["batch response 1", "batch response 2"]

    def mock_chat(messages, system=None, timeout=120):
        result = responses[call_count[0]]
        call_count[0] += 1
        return result

    with patch.object(adapter, "chat", side_effect=mock_chat):
        result = adapter.batch_chat(
            [
                {"messages": [{"role": "user", "content": "Hello"}]},
                {"messages": [{"role": "user", "content": "World"}]},
            ]
        )
        assert result == ["batch response 1", "batch response 2"]


def test_openai_compat_cleanup():
    adapter = OpenAICompatAdapter(
        base_url="https://api.openai.com",
        api_key="test-key",
        model="gpt-4",
    )

    with patch.object(adapter.client, "close") as mock_close:
        adapter.__del__()
        mock_close.assert_called_once()


def test_openai_compat_model_alias_400_helpful_error():
    """RED: When API returns 400 due to bad model alias, error must be helpful."""
    adapter = OpenAICompatAdapter(
        base_url="https://api.whalecloud.com",
        api_key="test-key",
        model="whalecloud-minimax",
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 400
    mock_response.text = '{"error": {"message": "Model whalecloud-minimax not found"}}'
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "400 Bad Request", request=MagicMock(), response=mock_response
    )

    with patch.object(adapter.client, "post", return_value=mock_response):
        with pytest.raises(RuntimeError) as excinfo:
            adapter._call_with_usage_sync(
                [{"role": "user", "content": "hello"}],
                timeout=30,
            )

    error_msg = str(excinfo.value)
    assert "model" in error_msg.lower(), "Error must mention model"
    assert "400" in error_msg or "Bad Request" in error_msg, "Error must include HTTP status"


def test_openai_compat_400_with_response_format_is_typed_rejection():
    """A 400 on a structured call is a schema rejection, not a bad model name."""
    adapter = OpenAICompatAdapter(
        base_url="https://api.whalecloud.com",
        api_key="test-key",
        model="gpt-proxy-model",
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 400
    mock_response.json.return_value = {"error": {"message": "response_format not supported"}}
    mock_response.text = '{"error": {"message": "response_format not supported"}}'

    with patch.object(adapter.client, "post", return_value=mock_response):
        with pytest.raises(StructuredOutputRejectedError) as excinfo:
            adapter._call_with_usage_sync(
                [{"role": "user", "content": "hello"}],
                timeout=30,
                response_format={"type": "json_schema", "json_schema": {}},
            )

    assert "response_format" in str(excinfo.value)


def test_openai_compat_extra_headers_sent():
    """extra_headers (e.g. ngrok tunnel headers) must reach the request."""
    adapter = OpenAICompatAdapter(
        base_url="https://tunnel.example.com/v1",
        api_key="test-key",
        model="m",
        extra_headers={"ngrok-skip-browser-warning": "true"},
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
    with patch.object(adapter.client, "post", return_value=mock_response) as mock_post:
        content = adapter.chat([{"role": "user", "content": "hi"}])

    assert content == "ok"
    headers = mock_post.call_args.kwargs["headers"]
    assert headers["ngrok-skip-browser-warning"] == "true"
    assert headers["Authorization"] == "Bearer test-key"


def test_openai_compat_rejects_reserved_extra_headers():
    """A configured header must not silently replace the adapter's own auth header."""
    with pytest.raises(ValueError, match="adapter-owned headers"):
        OpenAICompatAdapter(
            base_url="https://x.example.com/v1",
            api_key="test-key",
            model="m",
            extra_headers={"Authorization": "Bearer other", "X-Trace": "1"},
        )


def test_openai_compat_reserved_header_check_is_case_and_space_insensitive():
    with pytest.raises(ValueError, match="api-key"):
        OpenAICompatAdapter(
            base_url="https://x.example.com/v1",
            api_key="test-key",
            model="m",
            extra_headers={" API-Key ": "secret"},
        )


def test_factory_passes_headers_to_openai_adapter():
    from adapters.factory import create_adapter
    from engine.config import ModelConfig

    cfg = ModelConfig(
        base_url="https://tunnel.example.com/v1",
        api_key="k",
        model_name="qwen-tunnel",
        headers={"x-custom": "1"},
    )
    adapter = create_adapter(cfg)
    assert isinstance(adapter, OpenAICompatAdapter)
    assert adapter.extra_headers == {"x-custom": "1"}


if __name__ == "__main__":
    pytest.main([__file__])
