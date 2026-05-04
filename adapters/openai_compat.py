import httpx
from typing import List, Dict, Any, Optional, Tuple
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from .base import ModelAdapter


class OpenAICompatAdapter(ModelAdapter):
    """Adapter for OpenAI-compatible APIs — uses sync httpx.Client for thread safety."""
    
    def __init__(
        self, 
        base_url: str, 
        api_key: str, 
        model: str, 
        fallback_model: Optional[str] = None,
        rpm_limit: int = 60
    ):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.fallback_model = fallback_model
        self.client = httpx.Client(timeout=httpx.Timeout(120.0))
        
    def _call_with_usage(
        self,
        messages: List[Dict[str, str]],
        model: str,
        timeout: int
    ) -> Tuple[str, Dict[str, int]]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.0
        }

        response = self.client.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=timeout
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
    
    def chat(self, messages: List[Dict[str, str]], system: str = None, timeout: int = 120) -> str:
        content, _ = self._call_with_usage_sync(messages, system, timeout)
        return content

    def _call_with_usage_sync(
        self,
        messages: List[Dict[str, str]],
        system: str = None,
        timeout: int = 120
    ) -> Tuple[str, Dict[str, int]]:
        prepared_messages = []
        if system:
            prepared_messages.append({"role": "system", "content": system})
        prepared_messages.extend(messages)
        
        return self._call_with_usage(prepared_messages, self.model, timeout)

    def chat_with_usage(self, messages: List[Dict[str, str]], system: str = None, timeout: int = 120) -> Tuple[str, Dict[str, int]]:
        return self._call_with_usage_sync(messages, system, timeout)
    
    def batch_chat(self, requests: List[Dict[str, Any]], max_concurrency: int = 5) -> List[str]:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        results = [None] * len(requests)
        with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
            futures = {executor.submit(self.chat, req.get("messages", []), req.get("system"), req.get("timeout", 120)): i 
                      for i, req in enumerate(requests)}
            for future in as_completed(futures):
                results[futures[future]] = future.result()
        return results
    
    def __del__(self):
        try:
            self.client.close()
        except Exception:
            pass
