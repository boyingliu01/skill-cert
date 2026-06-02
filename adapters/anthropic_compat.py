import json
import time
from typing import Any

import requests

from .base import ModelAdapter


class AnthropicCompatAdapter(ModelAdapter):
    SUPPORTED_MODELS = [
        "qwen3.6-plus", "qwen3.5-plus", "qwen3-max-2026-01-23",
        "qwen3-coder-next", "qwen3-coder-plus",
        "glm-5", "glm-4.7", "kimi-k2.5", "MiniMax-M2.5",
    ]

    def __init__(self, base_url: str, api_key: str, model: str,
                 fallback_model: str | None = None, rpm_limit: int = 60):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.fallback_model = fallback_model
        self.session = requests.Session()
        self.session.headers.update({
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        })

    def chat(self, messages: list[dict[str, str]], system: str | None = None, timeout: int = 120) -> str:
        formatted = [
            {"role": "user" if m["role"] == "user" else "assistant", "content": m["content"]}
            for m in messages if m["role"] in ("user", "assistant")
        ]
        payload = {"model": self.model, "max_tokens": 8192, "messages": formatted}
        if system:
            payload["system"] = system
        return self._request(payload)

    def chat_with_usage(self, messages: list[dict[str, str]], system: str | None = None, timeout: int = 120) -> tuple[str, dict[str, int]]:
        formatted = [
            {"role": "user" if m["role"] == "user" else "assistant", "content": m["content"]}
            for m in messages if m["role"] in ("user", "assistant")
        ]
        payload = {"model": self.model, "max_tokens": 8192, "messages": formatted}
        if system:
            payload["system"] = system
        return self._request_with_usage(payload)

    def batch_chat(self, requests_list: list[dict[str, Any]], max_concurrency: int = 5) -> list[str]:
        results = []
        for req in requests_list:
            try:
                results.append(self.chat(req.get("messages", []), req.get("system")))
            except Exception as e:
                results.append(f"ERROR: {e}")
        return results

    def _request(self, payload: dict[str, Any], max_retries: int = 3) -> str:
        content, _ = self._request_with_usage(payload, max_retries)
        return content

    def _request_with_usage(self, payload: dict[str, Any], max_retries: int = 3) -> tuple[str, dict[str, int]]:
        for attempt in range(max_retries):
            try:
                resp = self.session.post(
                    f"{self.base_url}/messages",
                    json=payload,
                    timeout=120,
                )
                resp.raise_for_status()
                data = resp.json()
                content = ""
                for block in data.get("content", []):
                    if block.get("type") == "text":
                        content = block["text"]
                        break
                if not content:
                    content = json.dumps(data)
                usage = data.get("usage", {})
                token_data = {
                    "prompt_tokens": usage.get("input_tokens", 0),
                    "completion_tokens": usage.get("output_tokens", 0),
                    "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
                }
                return content, token_data
            except Exception:
                if attempt == max_retries - 1:
                    raise
                time.sleep(2 ** attempt)
        raise RuntimeError("Request failed after retries")
