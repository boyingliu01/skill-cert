"""Harness execution backends (opencode today, dsh reserved for v1)."""

from .base import HarnessAdapter, HarnessRunResult
from .dsh_harness import DshHarness
from .opencode_harness import OpenCodeHarness, extract_skill_name, parse_events

__all__ = [
    "HarnessAdapter",
    "HarnessRunResult",
    "OpenCodeHarness",
    "DshHarness",
    "extract_skill_name",
    "parse_events",
]
