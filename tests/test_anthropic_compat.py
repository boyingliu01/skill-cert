"""Tests for adapters/anthropic_compat.py — AnthropicCompatAdapter coverage."""

import json
from unittest.mock import MagicMock, patch

import pytest

from adapters.anthropic_compat import AnthropicCompatAdapter


@pytest.fixture
def adapter():
    """Create a test adapter instance."""
    return AnthropicCompatAdapter(
        base_url="https://api.example.com/",
        api_key="test-key",
        model="qwen3.6-plus",
    )


def _mock_response(data, status_code=200, raise_for_status=None):
    """Build a mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = data
    if raise_for_status is not None:
        resp.raise_for_status.side_effect = raise_for_status
    else:
        resp.raise_for_status.return_value = None
    return resp


# ---------------------------------------------------------------------------
# chat() — lines 50-58
# ---------------------------------------------------------------------------


class TestChat:
    """Tests for AnthropicCompatAdapter.chat()."""

    def test_chat_basic_user_message(self, adapter):
        """chat() should format user messages and return content string."""
        mock_resp = _mock_response({"content": [{"type": "text", "text": "Hello!"}], "usage": {}})
        with patch.object(adapter.session, "post", return_value=mock_resp) as mock_post:
            result = adapter.chat([{"role": "user", "content": "Hi"}])

        assert result == "Hello!"
        mock_post.assert_called_once()
        payload = mock_post.call_args.kwargs["json"]
        assert payload["model"] == "qwen3.6-plus"
        assert payload["max_tokens"] == 8192
        assert payload["messages"] == [{"role": "user", "content": "Hi"}]

    def test_chat_with_system_prompt(self, adapter):
        """chat() should include system prompt in payload when provided."""
        mock_resp = _mock_response({"content": [{"type": "text", "text": "OK"}], "usage": {}})
        with patch.object(adapter.session, "post", return_value=mock_resp) as mock_post:
            result = adapter.chat(
                [{"role": "user", "content": "Hi"}],
                system="You are helpful.",
            )

        assert result == "OK"
        payload = mock_post.call_args.kwargs["json"]
        assert payload["system"] == "You are helpful."

    def test_chat_filters_non_user_assistant_roles(self, adapter):
        """chat() should filter out messages with roles other than user/assistant."""
        mock_resp = _mock_response({"content": [{"type": "text", "text": "filtered"}], "usage": {}})
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "system", "content": "ignored"},
            {"role": "assistant", "content": "Hi there"},
            {"role": "tool", "content": "also ignored"},
        ]
        with patch.object(adapter.session, "post", return_value=mock_resp) as mock_post:
            result = adapter.chat(messages)

        assert result == "filtered"
        payload = mock_post.call_args.kwargs["json"]
        assert len(payload["messages"]) == 2
        assert payload["messages"][0] == {"role": "user", "content": "Hello"}
        assert payload["messages"][1] == {"role": "assistant", "content": "Hi there"}

    def test_chat_without_system_prompt_omits_system_key(self, adapter):
        """chat() should not include 'system' key when system is None."""
        mock_resp = _mock_response(
            {"content": [{"type": "text", "text": "no system"}], "usage": {}}
        )
        with patch.object(adapter.session, "post", return_value=mock_resp) as mock_post:
            adapter.chat([{"role": "user", "content": "test"}])

        payload = mock_post.call_args.kwargs["json"]
        assert "system" not in payload

    def test_chat_empty_messages(self, adapter):
        """chat() with empty messages should send empty list."""
        mock_resp = _mock_response({"content": [{"type": "text", "text": "empty"}], "usage": {}})
        with patch.object(adapter.session, "post", return_value=mock_resp) as mock_post:
            result = adapter.chat([])

        assert result == "empty"
        payload = mock_post.call_args.kwargs["json"]
        assert payload["messages"] == []


# ---------------------------------------------------------------------------
# chat_with_usage() — line 73 (system prompt branch)
# ---------------------------------------------------------------------------


class TestChatWithUsage:
    """Tests for AnthropicCompatAdapter.chat_with_usage()."""

    def test_chat_with_usage_system_prompt(self, adapter):
        """chat_with_usage() should include system in payload."""
        mock_resp = _mock_response(
            {
                "content": [{"type": "text", "text": "response"}],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            }
        )
        with patch.object(adapter.session, "post", return_value=mock_resp) as mock_post:
            content, usage = adapter.chat_with_usage(
                [{"role": "user", "content": "Hi"}],
                system="Be concise.",
            )

        assert content == "response"
        assert usage["prompt_tokens"] == 10
        assert usage["completion_tokens"] == 5
        assert usage["total_tokens"] == 15
        payload = mock_post.call_args.kwargs["json"]
        assert payload["system"] == "Be concise."

    def test_chat_with_usage_no_system(self, adapter):
        """chat_with_usage() without system should omit system key."""
        mock_resp = _mock_response(
            {
                "content": [{"type": "text", "text": "resp"}],
                "usage": {"input_tokens": 3, "output_tokens": 2},
            }
        )
        with patch.object(adapter.session, "post", return_value=mock_resp) as mock_post:
            content, usage = adapter.chat_with_usage([{"role": "user", "content": "test"}])

        assert content == "resp"
        payload = mock_post.call_args.kwargs["json"]
        assert "system" not in payload


# ---------------------------------------------------------------------------
# batch_chat() — lines 81-87
# ---------------------------------------------------------------------------


class TestBatchChat:
    """Tests for AnthropicCompatAdapter.batch_chat()."""

    def test_batch_chat_success(self, adapter):
        """batch_chat() should return results for each request."""
        responses = [
            _mock_response({"content": [{"type": "text", "text": "A"}], "usage": {}}),
            _mock_response({"content": [{"type": "text", "text": "B"}], "usage": {}}),
        ]
        with patch.object(adapter.session, "post", side_effect=responses):
            results = adapter.batch_chat(
                [
                    {"messages": [{"role": "user", "content": "1"}]},
                    {"messages": [{"role": "user", "content": "2"}]},
                ]
            )

        assert results == ["A", "B"]

    def test_batch_chat_with_error(self, adapter):
        """batch_chat() should catch exceptions and return error strings."""
        ok_resp = _mock_response({"content": [{"type": "text", "text": "OK"}], "usage": {}})
        # _request_with_usage retries 3 times, so need 3 failures for the 2nd request
        fail = RuntimeError("API down")
        with (
            patch.object(
                adapter.session,
                "post",
                side_effect=[ok_resp, fail, fail, fail],
            ),
            patch("adapters.anthropic_compat.time.sleep"),
        ):
            results = adapter.batch_chat(
                [
                    {"messages": [{"role": "user", "content": "good"}]},
                    {"messages": [{"role": "user", "content": "bad"}]},
                ]
            )

        assert results[0] == "OK"
        assert results[1].startswith("ERROR:")
        assert "API down" in results[1]

    def test_batch_chat_all_errors(self, adapter):
        """batch_chat() should handle all requests failing."""
        fail = ConnectionError("fail")
        with (
            patch.object(
                adapter.session,
                "post",
                side_effect=[fail] * 6,
            ),
            patch("adapters.anthropic_compat.time.sleep"),
        ):
            results = adapter.batch_chat(
                [
                    {"messages": [{"role": "user", "content": "a"}]},
                    {"messages": [{"role": "user", "content": "b"}]},
                ]
            )

        assert all(r.startswith("ERROR:") for r in results)

    def test_batch_chat_empty_requests(self, adapter):
        """batch_chat() with empty list should return empty list."""
        results = adapter.batch_chat([])
        assert results == []

    def test_batch_chat_with_system_in_request(self, adapter):
        """batch_chat() should pass system from request dict."""
        mock_resp = _mock_response({"content": [{"type": "text", "text": "sys"}], "usage": {}})
        with patch.object(adapter.session, "post", return_value=mock_resp) as mock_post:
            results = adapter.batch_chat(
                [
                    {
                        "messages": [{"role": "user", "content": "hi"}],
                        "system": "Be brief.",
                    }
                ]
            )

        assert results == ["sys"]
        payload = mock_post.call_args.kwargs["json"]
        assert payload["system"] == "Be brief."

    def test_batch_chat_missing_messages_key(self, adapter):
        """batch_chat() should handle request dict without 'messages' key."""
        mock_resp = _mock_response({"content": [{"type": "text", "text": "default"}], "usage": {}})
        with patch.object(adapter.session, "post", return_value=mock_resp):
            results = adapter.batch_chat([{}])

        assert results == ["default"]


# ---------------------------------------------------------------------------
# _request() — lines 94-95
# ---------------------------------------------------------------------------


class TestRequest:
    """Tests for AnthropicCompatAdapter._request()."""

    def test_request_delegates_to_request_with_usage(self, adapter):
        """_request() should return just the content string."""
        mock_resp = _mock_response(
            {
                "content": [{"type": "text", "text": "delegated"}],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        )
        with patch.object(adapter.session, "post", return_value=mock_resp):
            result = adapter._request({"model": "test", "max_tokens": 100, "messages": []})

        assert result == "delegated"


# ---------------------------------------------------------------------------
# _request_with_usage() — lines 117, 125-129
# ---------------------------------------------------------------------------


class TestRequestWithUsage:
    """Tests for AnthropicCompatAdapter._request_with_usage()."""

    def test_no_text_content_fallback_to_json(self, adapter):
        """When no text block found, should fallback to json.dumps of data."""
        mock_resp = _mock_response(
            {
                "content": [{"type": "image", "source": "base64"}],
                "usage": {"input_tokens": 5, "output_tokens": 0},
            }
        )
        with patch.object(adapter.session, "post", return_value=mock_resp):
            content, usage = adapter._request_with_usage(
                {"model": "test", "max_tokens": 100, "messages": []}
            )

        # Should be the full JSON dump since no text block
        parsed = json.loads(content)
        assert parsed["content"][0]["type"] == "image"

    def test_empty_content_list_fallback(self, adapter):
        """When content list is empty, should fallback to json.dumps."""
        mock_resp = _mock_response(
            {"content": [], "usage": {"input_tokens": 1, "output_tokens": 0}}
        )
        with patch.object(adapter.session, "post", return_value=mock_resp):
            content, _ = adapter._request_with_usage(
                {"model": "test", "max_tokens": 100, "messages": []}
            )

        parsed = json.loads(content)
        assert parsed["content"] == []

    def test_retry_succeeds_on_second_attempt(self, adapter):
        """Should retry on failure and succeed."""
        fail_resp = MagicMock()
        fail_resp.raise_for_status.side_effect = RuntimeError("temporary error")

        success_resp = _mock_response(
            {
                "content": [{"type": "text", "text": "recovered"}],
                "usage": {"input_tokens": 2, "output_tokens": 1},
            }
        )

        with (
            patch.object(adapter.session, "post", side_effect=[fail_resp, success_resp]),
            patch("adapters.anthropic_compat.time.sleep") as mock_sleep,
        ):
            content, usage = adapter._request_with_usage(
                {"model": "test", "max_tokens": 100, "messages": []},
                max_retries=3,
            )

        assert content == "recovered"
        assert usage["prompt_tokens"] == 2
        mock_sleep.assert_called_once_with(1)  # 2**0 = 1

    def test_retry_exhausted_raises(self, adapter):
        """Should raise after all retries exhausted."""
        fail_resp = MagicMock()
        fail_resp.raise_for_status.side_effect = RuntimeError("persistent error")

        with (
            patch.object(adapter.session, "post", return_value=fail_resp),
            patch("adapters.anthropic_compat.time.sleep") as mock_sleep,
        ):
            with pytest.raises(RuntimeError, match="persistent error"):
                adapter._request_with_usage(
                    {"model": "test", "max_tokens": 100, "messages": []},
                    max_retries=3,
                )

        # Should sleep between retries: attempt 0 -> sleep(1), attempt 1 -> sleep(2)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1)  # 2**0
        mock_sleep.assert_any_call(2)  # 2**1

    def test_single_retry_no_sleep(self, adapter):
        """With max_retries=1, should raise immediately without sleeping."""
        fail_resp = MagicMock()
        fail_resp.raise_for_status.side_effect = RuntimeError("immediate fail")

        with (
            patch.object(adapter.session, "post", return_value=fail_resp),
            patch("adapters.anthropic_compat.time.sleep") as mock_sleep,
        ):
            with pytest.raises(RuntimeError, match="immediate fail"):
                adapter._request_with_usage(
                    {"model": "test", "max_tokens": 100, "messages": []},
                    max_retries=1,
                )

        mock_sleep.assert_not_called()

    def test_usage_extraction(self, adapter):
        """Should correctly extract and compute token usage."""
        mock_resp = _mock_response(
            {
                "content": [{"type": "text", "text": "ok"}],
                "usage": {"input_tokens": 100, "output_tokens": 50},
            }
        )
        with patch.object(adapter.session, "post", return_value=mock_resp):
            _, usage = adapter._request_with_usage(
                {"model": "test", "max_tokens": 100, "messages": []}
            )

        assert usage["prompt_tokens"] == 100
        assert usage["completion_tokens"] == 50
        assert usage["total_tokens"] == 150

    def test_missing_usage_fields_default_to_zero(self, adapter):
        """Should default to 0 when usage fields are missing."""
        mock_resp = _mock_response({"content": [{"type": "text", "text": "ok"}], "usage": {}})
        with patch.object(adapter.session, "post", return_value=mock_resp):
            _, usage = adapter._request_with_usage(
                {"model": "test", "max_tokens": 100, "messages": []}
            )

        assert usage["prompt_tokens"] == 0
        assert usage["completion_tokens"] == 0
        assert usage["total_tokens"] == 0

    def test_missing_usage_key_defaults_to_zero(self, adapter):
        """Should default to 0 when 'usage' key is absent entirely."""
        mock_resp = _mock_response({"content": [{"type": "text", "text": "ok"}]})
        with patch.object(adapter.session, "post", return_value=mock_resp):
            _, usage = adapter._request_with_usage(
                {"model": "test", "max_tokens": 100, "messages": []}
            )

        assert usage["prompt_tokens"] == 0
        assert usage["completion_tokens"] == 0
        assert usage["total_tokens"] == 0


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestInit:
    """Tests for AnthropicCompatAdapter.__init__()."""

    def test_base_url_trailing_slash_stripped(self):
        """Should strip trailing slash from base_url."""
        adapter = AnthropicCompatAdapter(
            base_url="https://api.example.com/",
            api_key="key",
            model="test",
        )
        assert adapter.base_url == "https://api.example.com"

    def test_base_url_no_trailing_slash(self):
        """Should keep base_url as-is if no trailing slash."""
        adapter = AnthropicCompatAdapter(
            base_url="https://api.example.com",
            api_key="key",
            model="test",
        )
        assert adapter.base_url == "https://api.example.com"

    def test_headers_set_correctly(self):
        """Should set required headers on session."""
        adapter = AnthropicCompatAdapter(
            base_url="https://api.example.com",
            api_key="my-secret-key",
            model="test",
        )
        headers = adapter.session.headers
        assert headers["x-api-key"] == "my-secret-key"
        assert headers["Content-Type"] == "application/json"
        assert headers["anthropic-version"] == "2023-06-01"

    def test_fallback_model_stored(self):
        """Should store fallback_model if provided."""
        adapter = AnthropicCompatAdapter(
            base_url="https://api.example.com",
            api_key="key",
            model="primary",
            fallback_model="secondary",
        )
        assert adapter.fallback_model == "secondary"

    def test_fallback_model_default_none(self):
        """fallback_model should default to None."""
        adapter = AnthropicCompatAdapter(
            base_url="https://api.example.com",
            api_key="key",
            model="primary",
        )
        assert adapter.fallback_model is None

    def test_supported_models_list(self):
        """SUPPORTED_MODELS should contain expected models."""
        assert "qwen3.6-plus" in AnthropicCompatAdapter.SUPPORTED_MODELS
        assert "glm-5" in AnthropicCompatAdapter.SUPPORTED_MODELS
        assert "kimi-k2.5" in AnthropicCompatAdapter.SUPPORTED_MODELS
