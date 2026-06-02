from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def to_dict(self) -> dict[str, int]:
        return {"input_tokens": self.input_tokens, "output_tokens": self.output_tokens, "total_tokens": self.total_tokens}

    @classmethod
    def from_dict(cls, data: dict[str, int]) -> "TokenUsage":
        return cls(input_tokens=data.get("input_tokens", 0), output_tokens=data.get("output_tokens", 0), total_tokens=data.get("total_tokens", 0))


@dataclass
class LLMResponse:
    text: str
    token_usage: TokenUsage | None = None
    latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "token_usage": self.token_usage.to_dict() if self.token_usage else None, "latency_ms": self.latency_ms}


class ModelAdapter(ABC):
    """
    Abstract base class for model adapters.
    Defines the interface for interacting with different LLM providers.
    """

    @abstractmethod
    def chat(self, messages: list[dict[str, str]], system: str | None = None, timeout: int = 120) -> str:
        """
        Send a chat request to the model.

        Args:
            messages: List of message dictionaries with 'role' and 'content'
            system: Optional system message
            timeout: Request timeout in seconds

        Returns:
            Model response as a string
        """
        pass

    def chat_with_usage(self, messages: list[dict[str, str]], system: str | None = None, timeout: int = 120) -> tuple[str, dict[str, int]]:
        """
        Send a chat request and return both content and token usage.
        Default fallback: uses chat() and estimates usage.
        Override in subclasses for real token counts.

        Returns:
            Tuple of (response_text, {"prompt_tokens": N, "completion_tokens": N, "total_tokens": N})
        """
        content = self.chat(messages, system, timeout)
        estimated = len(content.split()) if content else 0
        return content, {"prompt_tokens": 0, "completion_tokens": estimated, "total_tokens": estimated}

    @abstractmethod
    def batch_chat(self, requests: list[dict[str, Any]], max_concurrency: int = 5) -> list[str]:
        """
        Send multiple chat requests concurrently.

        Args:
            requests: List of request dictionaries containing messages, system, timeout
            max_concurrency: Maximum number of concurrent requests

        Returns:
            List of model responses in the same order as requests
        """
        pass
