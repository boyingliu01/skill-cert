"""Shared fixtures and mock adapters for the skill-cert test suite."""

from typing import Any

import pytest


class MockModelAdapter:
    """Flexible mock LLM adapter for testing.

    Supports two response modes:
    1. List mode: pass a list of strings, each call returns the next in sequence.
    2. Dict mode: pass a dict with keyword keys, content routing extracts keywords
       from the concatenated message content.

    Default mode is list mode (empty list returns default_response).

    Attributes:
        model_name: Name returned by adapter.
        model: Alias for model_name (for runner compatibility).
        _mock_name: Flag to identify this as a mock (runner checks this).
        call_count: Number of times chat() has been called.
        chat_history: List of dicts with 'messages' and 'system' keys.
    """

    def __init__(
        self,
        responses: Any = None,
        model_name: str = "mock-model",
        default_response: str = "Mock response",
    ):
        self.model_name = model_name
        self.model = model_name
        self._mock_name = "mock_adapter"
        self.call_count = 0
        self.chat_history: list[dict[str, Any]] = []

        if responses is None:
            self.responses: list[str] | dict[str, str] = []
        else:
            self.responses = responses

        self.default_response = default_response

    def chat(self, messages: Any, system: str | None = None, timeout: int = 120) -> str:
        """Return the next response based on call order or message content."""
        # Build content string for keyword matching
        content = ""
        if isinstance(messages, list):
            for msg in messages:
                if isinstance(msg, dict) and "content" in msg:
                    content += str(msg["content"])

        self.chat_history.append({"messages": messages, "system": system})
        self.call_count += 1

        # List mode: index by call_count - 1
        if isinstance(self.responses, list):
            idx = self.call_count - 1
            if idx < len(self.responses):
                return self.responses[idx]
            return self.default_response

        # Dict mode: keyword routing
        if isinstance(self.responses, dict):
            content_lower = content.lower()
            for key, value in self.responses.items():
                if key != "default" and key in content_lower:
                    return value
            return self.responses.get("default", self.default_response)

        return self.default_response

    def chat_with_usage(
        self, messages: Any, system: str | None = None, timeout: int = 120
    ) -> tuple[str, dict[str, int]]:
        """Mock chat with token usage tracking."""
        response = self.chat(messages, system, timeout)
        return response, {
            "prompt_tokens": 100,
            "completion_tokens": len(response.split()) if response else 0,
            "total_tokens": 100 + (len(response.split()) if response else 0),
        }

    def generate(self, prompt: str) -> str:
        """Convenience wrapper for generate-style calls."""
        return self.chat([{"role": "user", "content": prompt}])


@pytest.fixture
def mock_adapter() -> MockModelAdapter:
    """Return a fresh MockModelAdapter with default list-mode responses."""
    return MockModelAdapter()
