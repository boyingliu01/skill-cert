"""Shared LLM structured-output helper for harness taskgen/judge.

Strategy: call ``adapter.chat`` with an OpenAI-style ``response_format``
json_schema; gateways that refuse the parameter raise
``StructuredOutputRejectedError``, which degrades to a plain call — the prompts
already embed the JSON format — followed by the battle-tested
``engine.json_extract.extract_json`` 4-level fallback chain.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from adapters.base import StructuredOutputRejectedError
from engine.json_extract import extract_json

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
    except StructuredOutputRejectedError as e:
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
    return extract_json(resp)
