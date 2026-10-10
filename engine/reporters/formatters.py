"""Formatting helpers for report generation.

Extracted utility functions for numeric conversion, config redaction,
and other formatting operations used across the reporters package.
"""

from typing import Any


def num(value: Any, default: float = 0.0) -> float:
    """Convert a value to float, returning default if None.

    Args:
        value: The value to convert.
        default: Default value to return if value is None.

    Returns:
        Float representation of value, or default if None.
    """
    if value is None:
        return default
    return float(value)


def redact_config(config: dict[str, Any]) -> dict[str, Any]:
    """Strip secrets (api keys, header values) from config for safe reporting.

    Args:
        config: Configuration dictionary potentially containing secrets.

    Returns:
        A new dict with the secret-bearing model fields removed or masked.
    """
    redacted = dict(config)
    models_raw = redacted.get("models")
    if isinstance(models_raw, list):
        cleaned_models = []
        for m in models_raw:
            if not isinstance(m, dict):
                continue
            entry = {k: v for k, v in m.items() if not k.endswith("api_key")}
            headers = entry.get("headers")
            if isinstance(headers, dict):
                # tunnel/auth headers carry tokens just like api_key does
                entry["headers"] = {name: "***" for name in headers}
            cleaned_models.append(entry)
        redacted["models"] = cleaned_models
    return redacted
