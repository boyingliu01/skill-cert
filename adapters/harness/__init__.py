"""Harness execution backends (opencode today, dsh reserved for v1)."""

from .base import HarnessAdapter, HarnessRunResult
from .dsh_harness import DshHarness
from .opencode_harness import (
    OpenCodeHarness,
    ServeListenerMismatchError,
    extract_skill_name,
    parse_events,
    probe_serve_listener,
)

__all__ = [
    "HarnessAdapter",
    "HarnessRunResult",
    "OpenCodeHarness",
    "DshHarness",
    "ServeListenerMismatchError",
    "extract_skill_name",
    "parse_events",
    "probe_serve_listener",
]
