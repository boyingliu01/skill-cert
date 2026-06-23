import logging
from typing import Any

import httpx

from .base import ModelAdapter

logger = logging.getLogger(__name__)


class OpenAICompatAdapter(ModelAdapter):
    """Adapter for OpenAI-compatible APIs — uses sync httpx.Client for thread safety.
    Supports fallback to a different endpoint when primary is unreachable."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        fallback_model: str | None = None,
        fallback_base_url: str | None = None,
        fallback_api_key: str | None = None,
        rpm_limit: int = 60,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.fallback_model = fallback_model
        self.fallback_base_url = fallback_base_url.rstrip("/") if fallback_base_url else None
        self.fallback_api_key = fallback_api_key
        self._has_fallback = bool(
            self.fallback_model and self.fallback_base_url and self.fallback_api_key
        )
        # Force HTTP/1.1 to avoid HTTP/2 negotiation issues with some proxies
        self.client = httpx.Client(
            timeout=httpx.Timeout(120.0),
            http1=True,
            http2=False,
        )

    @staticmethod
    def _extract_error_detail(response: httpx.Response) -> str:
        """Extract error detail from API response body, if available."""
        try:
            body = response.json()
            msg = body.get("error", {}).get("message", "") or body.get("message", "")
            if msg:
                return msg[:200]
        except Exception:
            pass
        return response.text[:200] if response.text else "No detail provided"

    def _call_with_usage(
        self,
        messages: list[dict[str, str]],
        model: str,
        timeout: int,
        base_url: str | None = None,
        api_key: str | None = None,
        use_requests_fallback: bool = False,
    ) -> tuple[str, dict[str, int]]:
        use_base = base_url or self.base_url
        use_key = api_key or self.api_key

        headers = {"Authorization": f"Bearer {use_key}", "Content-Type": "application/json"}

        payload = {"model": model, "messages": messages, "temperature": 0.0}

        try:
            response = self.client.post(
                f"{use_base}/chat/completions", headers=headers, json=payload, timeout=timeout
            )
        except httpx.ConnectError as e:
            # Fallback to requests when httpx SSL fails (corporate proxy compatibility)
            if not use_requests_fallback:
                logger.warning(f"httpx SSL failed, falling back to requests: {e}")
                import requests as _requests

                response = _requests.post(  # type: ignore[assignment]
                    f"{use_base}/chat/completions", headers=headers, json=payload, timeout=timeout
                )
                if response.status_code == 401:
                    raise RuntimeError("Invalid API key")
                elif response.status_code == 404:
                    raise RuntimeError("Model not found")
                elif response.status_code == 429:
                    raise RuntimeError("Insufficient quota")
                else:
                    response.raise_for_status()

                result = response.json()
                content = result["choices"][0]["message"]["content"]
                usage = result.get("usage", {})
                token_data = {
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                }
                return content, token_data
            raise

        if response.status_code == 401:
            raise RuntimeError("Invalid API key")
        elif response.status_code == 400:
            detail = self._extract_error_detail(response)
            raise RuntimeError(
                f"API returned 400 for model '{model}'. "
                f"Verify the model name matches the API endpoint's expected format. "
                f"Detail: {detail}"
            )
        elif response.status_code == 404:
            raise RuntimeError("Model not found")
        elif response.status_code == 429:
            raise RuntimeError("Insufficient quota")
        else:
            response.raise_for_status()

        result = response.json()
        content = result["choices"][0]["message"]["content"]
        usage = result.get("usage", {})
        token_data = {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        }
        return content, token_data

    def _call_with_usage_sync(
        self, messages: list[dict[str, str]], system: str | None = None, timeout: int = 120
    ) -> tuple[str, dict[str, int]]:
        prepared_messages = []
        if system:
            prepared_messages.append({"role": "system", "content": system})
        prepared_messages.extend(messages)

        return self._call_with_usage_with_fallback(prepared_messages, self.model, timeout)

    def _call_with_usage_with_fallback(
        self, messages: list[dict[str, str]], model: str, timeout: int
    ) -> tuple[str, dict[str, int]]:
        try:
            return self._call_with_usage(messages, model, timeout, use_requests_fallback=True)
        except (httpx.ConnectError, httpx.ConnectTimeout, OSError) as e:
            if self._has_fallback:
                logger.warning(
                    f"Primary endpoint unreachable ({self.base_url}, {self.model}), "
                    f"falling back to {self.fallback_base_url}/{self.fallback_model}: {e}"
                )
                return self._call_with_usage(
                    messages,
                    self.fallback_model or model,
                    timeout,
                    base_url=self.fallback_base_url,
                    api_key=self.fallback_api_key,
                    use_requests_fallback=True,
                )
            raise

    def chat(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        timeout: int = 120,
    ) -> str:
        content, _ = self._call_with_usage_sync(messages, system, timeout)
        return content

    def chat_with_usage(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        timeout: int = 120,
    ) -> tuple[str, dict[str, int]]:
        return self._call_with_usage_sync(messages, system, timeout)

    def batch_chat(self, requests: list[dict[str, Any]], max_concurrency: int = 5) -> list[str]:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results: list[str] = []
        with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
            futures = {
                executor.submit(
                    self.chat,
                    req.get("messages", []),
                    req.get("system"),
                    req.get("timeout", 120),
                ): i
                for i, req in enumerate(requests)
            }
            result_map: dict[int, str] = {}
            for future in as_completed(futures):
                result_map[futures[future]] = future.result()
            results = [result_map[i] for i in range(len(requests))]
        return results

    def __del__(self):
        try:
            self.client.close()
        except Exception:
            pass
