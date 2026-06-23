"""Tests for uncovered coverage gaps in adapters/openai_compat.py."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from adapters.openai_compat import OpenAICompatAdapter


def test_extract_error_detail_json_exception():
    """Covers lines 49-51: _extract_error_detail when response.json() raises."""
    adapter = OpenAICompatAdapter(
        base_url="https://api.openai.com",
        api_key="test-key",
        model="gpt-4",
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.side_effect = ValueError("Invalid JSON")
    mock_response.text = "Plain text error detail"

    result = adapter._extract_error_detail(mock_response)
    assert result == "Plain text error detail"


def test_extract_error_detail_no_text():
    """Covers line 51: _extract_error_detail when response.text is empty."""
    adapter = OpenAICompatAdapter(
        base_url="https://api.openai.com",
        api_key="test-key",
        model="gpt-4",
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.side_effect = ValueError("Invalid JSON")
    mock_response.text = ""

    result = adapter._extract_error_detail(mock_response)
    assert result == "No detail provided"


def test_call_with_usage_connect_error_fallback():
    """Covers lines 73-101: httpx.ConnectError -> requests fallback success."""
    import requests

    adapter = OpenAICompatAdapter(
        base_url="https://api.openai.com",
        api_key="test-key",
        model="gpt-4",
    )

    mock_requests_response = MagicMock(spec=requests.Response)
    mock_requests_response.status_code = 200
    mock_requests_response.json.return_value = {
        "choices": [{"message": {"content": "fallback response"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }

    with patch.object(adapter.client, "post", side_effect=httpx.ConnectError("SSL failed")):
        with patch("requests.post", return_value=mock_requests_response):
            content, usage = adapter._call_with_usage(
                messages=[{"role": "user", "content": "test"}],
                model="gpt-4",
                timeout=30,
                use_requests_fallback=False,
            )

    assert content == "fallback response"
    assert usage["total_tokens"] == 15


def test_call_with_usage_connect_error_fallback_401():
    """Covers line 84-85: requests fallback with 401."""
    import requests

    adapter = OpenAICompatAdapter(
        base_url="https://api.openai.com",
        api_key="test-key",
        model="gpt-4",
    )

    mock_requests_response = MagicMock(spec=requests.Response)
    mock_requests_response.status_code = 401

    with patch.object(adapter.client, "post", side_effect=httpx.ConnectError("SSL failed")):
        with patch("requests.post", return_value=mock_requests_response):
            with pytest.raises(RuntimeError, match="Invalid API key"):
                adapter._call_with_usage(
                    messages=[{"role": "user", "content": "test"}],
                    model="gpt-4",
                    timeout=30,
                    use_requests_fallback=False,
                )


def test_call_with_usage_connect_error_fallback_404():
    """Covers line 86-87: requests fallback with 404."""
    import requests

    adapter = OpenAICompatAdapter(
        base_url="https://api.openai.com",
        api_key="test-key",
        model="gpt-4",
    )

    mock_requests_response = MagicMock(spec=requests.Response)
    mock_requests_response.status_code = 404

    with patch.object(adapter.client, "post", side_effect=httpx.ConnectError("SSL failed")):
        with patch("requests.post", return_value=mock_requests_response):
            with pytest.raises(RuntimeError, match="Model not found"):
                adapter._call_with_usage(
                    messages=[{"role": "user", "content": "test"}],
                    model="gpt-4",
                    timeout=30,
                    use_requests_fallback=False,
                )


def test_call_with_usage_connect_error_fallback_429():
    """Covers line 88-89: requests fallback with 429."""
    import requests

    adapter = OpenAICompatAdapter(
        base_url="https://api.openai.com",
        api_key="test-key",
        model="gpt-4",
    )

    mock_requests_response = MagicMock(spec=requests.Response)
    mock_requests_response.status_code = 429

    with patch.object(adapter.client, "post", side_effect=httpx.ConnectError("SSL failed")):
        with patch("requests.post", return_value=mock_requests_response):
            with pytest.raises(RuntimeError, match="Insufficient quota"):
                adapter._call_with_usage(
                    messages=[{"role": "user", "content": "test"}],
                    model="gpt-4",
                    timeout=30,
                    use_requests_fallback=False,
                )


def test_call_with_usage_connect_error_fallback_500():
    """Covers line 90-91: requests fallback with non-401/404/429 status -> raise_for_status."""
    import requests

    adapter = OpenAICompatAdapter(
        base_url="https://api.openai.com",
        api_key="test-key",
        model="gpt-4",
    )

    mock_requests_response = MagicMock(spec=requests.Response)
    mock_requests_response.status_code = 500
    mock_requests_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500 Error", request=MagicMock(), response=mock_requests_response
    )

    with patch.object(adapter.client, "post", side_effect=httpx.ConnectError("SSL failed")):
        with patch("requests.post", return_value=mock_requests_response):
            with pytest.raises(httpx.HTTPStatusError):
                adapter._call_with_usage(
                    messages=[{"role": "user", "content": "test"}],
                    model="gpt-4",
                    timeout=30,
                    use_requests_fallback=False,
                )


def test_call_with_usage_connect_error_raises_when_fallback_none():
    """Covers line 102: httpx.ConnectError re-raises when use_requests_fallback=True."""
    adapter = OpenAICompatAdapter(
        base_url="https://api.openai.com",
        api_key="test-key",
        model="gpt-4",
    )

    with patch.object(adapter.client, "post", side_effect=httpx.ConnectError("SSL failed")):
        with pytest.raises(httpx.ConnectError):
            adapter._call_with_usage(
                messages=[{"role": "user", "content": "test"}],
                model="gpt-4",
                timeout=30,
                use_requests_fallback=True,
            )


def test_call_with_usage_sync_with_system():
    """Covers line 135: system message branch in _call_with_usage_sync."""
    adapter = OpenAICompatAdapter(
        base_url="https://api.openai.com",
        api_key="test-key",
        model="gpt-4",
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "response with system"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
    }

    with patch.object(adapter.client, "post", return_value=mock_response) as mock_post:
        content, usage = adapter._call_with_usage_sync(
            messages=[{"role": "user", "content": "hello"}],
            system="You are a helpful assistant",
            timeout=120,
        )
        assert content == "response with system"
        assert usage["total_tokens"] == 15
        # Verify the system message was prepended
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        expected_system = {"role": "system", "content": "You are a helpful assistant"}
        assert payload["messages"][0] == expected_system
        assert payload["messages"][1] == {"role": "user", "content": "hello"}


def test_call_with_usage_with_fallback_triggered():
    """Covers lines 146-157: fallback endpoint when primary raises ConnectError."""
    adapter = OpenAICompatAdapter(
        base_url="https://api.primary.com",
        api_key="primary-key",
        model="primary-model",
        fallback_model="fallback-model",
        fallback_base_url="https://api.fallback.com",
        fallback_api_key="fallback-key",
    )

    assert adapter._has_fallback is True

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "fallback response"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
    }

    with patch.object(adapter.client, "post") as mock_post:
        # First call fails with ConnectError, second succeeds
        mock_post.side_effect = [
            httpx.ConnectError("Primary down"),
            mock_response,
        ]

        content, usage = adapter._call_with_usage_with_fallback(
            messages=[{"role": "user", "content": "test"}],
            model="primary-model",
            timeout=120,
        )
        assert content == "fallback response"
        assert mock_post.call_count == 2

        # Verify the second call used fallback params
        second_call_url = mock_post.call_args[0][0]
        headers = mock_post.call_args[1]["headers"]
        assert "api.fallback.com" in second_call_url
        assert headers["Authorization"] == "Bearer fallback-key"


def test_call_with_usage_with_fallback_not_triggered_no_fallback():
    """Covers line 158: raises when _has_fallback is False."""
    adapter = OpenAICompatAdapter(
        base_url="https://api.primary.com",
        api_key="primary-key",
        model="primary-model",
    )

    assert adapter._has_fallback is False

    with patch.object(adapter.client, "post", side_effect=httpx.ConnectError("Primary down")):
        with pytest.raises(httpx.ConnectError):
            adapter._call_with_usage_with_fallback(
                messages=[{"role": "user", "content": "test"}],
                model="primary-model",
                timeout=120,
            )


def test_call_with_usage_with_fallback_oserror():
    """Covers lines 146-157: OSError also triggers fallback."""
    adapter = OpenAICompatAdapter(
        base_url="https://api.primary.com",
        api_key="primary-key",
        model="primary-model",
        fallback_model="fallback-model",
        fallback_base_url="https://api.fallback.com",
        fallback_api_key="fallback-key",
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "os fallback"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }

    with patch.object(adapter.client, "post") as mock_post:
        mock_post.side_effect = [OSError("Connection refused"), mock_response]

        content, usage = adapter._call_with_usage_with_fallback(
            messages=[{"role": "user", "content": "test"}],
            model="primary-model",
            timeout=120,
        )
        assert content == "os fallback"
        assert mock_post.call_count == 2


def test_del_exception_swallowed():
    """Covers lines 200-201: __del__ swallows exceptions from client.close()."""
    adapter = OpenAICompatAdapter(
        base_url="https://api.openai.com",
        api_key="test-key",
        model="gpt-4",
    )

    with patch.object(adapter.client, "close", side_effect=Exception("Close failed")):
        # __del__ should not propagate the exception
        adapter.__del__()  # No assert needed — if it raises, test fails
