import httpx
from unittest.mock import MagicMock, patch
import pytest
from adapters.base import ModelAdapter
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
        rpm_limit=100
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
        fallback_model="fallback-model"
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
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "sync response"}}]
    }
    
    with patch.object(adapter.client, 'post', return_value=mock_response):
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
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
    }
    
    with patch.object(adapter.client, 'post', return_value=mock_response):
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
    
    with patch.object(adapter.client, 'post', return_value=mock_response):
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
    
    with patch.object(adapter.client, 'post', return_value=mock_response):
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
    
    with patch.object(adapter.client, 'post', return_value=mock_response):
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
    
    with patch.object(adapter, 'chat', side_effect=mock_chat):
        result = adapter.batch_chat([
            {"messages": [{"role": "user", "content": "Hello"}]},
            {"messages": [{"role": "user", "content": "World"}]}
        ])
        assert result == ["batch response 1", "batch response 2"]


def test_openai_compat_cleanup():
    adapter = OpenAICompatAdapter(
        base_url="https://api.openai.com",
        api_key="test-key",
        model="gpt-4",
    )
    
    with patch.object(adapter.client, 'close') as mock_close:
        adapter.__del__()
        mock_close.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__])
