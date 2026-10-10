"""Harness adapter contracts — execution backends for skill evaluation.

A "harness" is a coding-agent runtime (opencode, dsh, ...) that loads skills
through its native progressive-disclosure mechanism. Adapters install a skill
into a sandbox directory and run tasks non-interactively, returning the raw
event stream so downstream layers can analyze behavior and metering.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field


class HarnessRunResult(BaseModel):
    """Outcome of one non-interactive task run inside a harness sandbox."""

    session_id: str = ""
    exit_code: int = 0
    final_output: str = ""  # agent final reply text (last text event)
    events: list[dict] = Field(default_factory=list)  # raw --format json events
    skill_loaded: bool = False  # a native skill tool call appears in the stream
    tool_call_count: int = 0
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost: float | None = None  # as reported by the harness (None = not reported)
    duration_s: float = 0.0
    error: str | None = None


class HarnessAdapter(Protocol):
    """Execution backend protocol: sandbox preparation + non-interactive runs."""

    # The evaluator rewrites this before every run, so backends must read it at
    # run time rather than capturing it at construction.
    title: str

    def prepare(self, sandbox_dir: Path, skill_dir: Path | None) -> None:
        """Install the skill into the sandbox (skill_dir=None is the without condition)."""
        ...

    def run_task(self, task_prompt: str, sandbox_dir: Path) -> HarnessRunResult:
        """Execute one task non-interactively inside the sandbox directory."""
        ...
