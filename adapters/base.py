from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple


class ModelAdapter(ABC):
    """
    Abstract base class for model adapters.
    Defines the interface for interacting with different LLM providers.
    """

    @abstractmethod
    def chat(self, messages: List[Dict[str, str]], system: str | None = None, timeout: int = 120) -> str:
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

    def chat_with_usage(self, messages: List[Dict[str, str]], system: str | None = None, timeout: int = 120) -> Tuple[str, Dict[str, int]]:
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
    def batch_chat(self, requests: List[Dict[str, Any]], max_concurrency: int = 5) -> List[str]:
        """
        Send multiple chat requests concurrently.

        Args:
            requests: List of request dictionaries containing messages, system, timeout
            max_concurrency: Maximum number of concurrent requests

        Returns:
            List of model responses in the same order as requests
        """
        pass