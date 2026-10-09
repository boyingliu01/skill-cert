"""Shared LLM structured-output helper for harness taskgen/judge.

Strategy: call ``adapter.chat`` with an OpenAI-style ``response_format``
json_schema; gateways that reject the parameter (HTTP 400, e.g. older
gpt-proxy) degrade to a plain call — the prompts already embed the JSON
format — followed by the battle-tested ``EvalGenerator._extract_json``
4-level fallback chain.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def chat_json(
    adapter: Any,
    prompt: str,
    schema: dict[str, Any] | None,
    timeout: int = 180,
) -> dict[str, Any]:
    """Call adapter.chat expecting a JSON object response; degrade gracefully."""
    messages = [{"role": "user", "content": prompt}]
    try:
        resp = adapter.chat(messages, timeout=timeout, response_format=schema)
    except RuntimeError as e:
        if schema is None or "400" not in str(e):
            raise
        logger.warning("structured output rejected (%s); degrading to prompt-embedded schema", e)
        resp = adapter.chat(messages, timeout=timeout)

    data = _parse_json(resp)
    if not isinstance(data, dict):
        raise ValueError(f"LLM did not return a JSON object: {str(resp)[:200]}")
    return data


def _parse_json(resp: str) -> Any:
    try:
        return json.loads(resp)
    except (json.JSONDecodeError, TypeError):
        pass
    from engine.testgen import EvalGenerator  # lazy import — 4-level fallback chain

    return EvalGenerator._extract_json(resp)
