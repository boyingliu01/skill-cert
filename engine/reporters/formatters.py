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
    """Strip sensitive fields (api_key) from config dict for safe reporting.

    Args:
        config: Configuration dictionary potentially containing secrets.

    Returns:
        A new dict with api_key fields removed from model entries.
    """
    redacted = dict(config)
    models_raw = redacted.get("models")
    if isinstance(models_raw, list):
        redacted["models"] = [
            {k: v for k, v in m.items() if k != "api_key"}
            for m in models_raw
            if isinstance(m, dict)
        ]
    return redacted
