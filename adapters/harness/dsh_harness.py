"""DeepSeek Harness (dsh) stub — reserved for v1, not wired into the MVP.

Status as of 2026-08-22 (docs/plans/harness-spike-notes.md): dsh is a
developer preview (0.1.0-rc.6) with a Web UI entry point only — no
non-interactive CLI/server mode, and breaking changes have been announced.

Re-check deepseek-ai/deepseek-harness weekly until v1; implement this
adapter once a stable headless API exists. Until then, DeepSeek models are
evaluated through OpenCodeHarness via ``--model deepseek/<model>``.
"""

from __future__ import annotations

from pathlib import Path

from .base import HarnessRunResult


class DshHarness:
    """Placeholder adapter: raises NotImplementedError until dsh exposes a
    stable non-interactive API."""

    _STUB_MSG = (
        "DshHarness is a stub: dsh (developer preview) has no stable non-interactive "
        "CLI yet — see docs/plans/harness-spike-notes.md. Use OpenCodeHarness with a "
        "deepseek model meanwhile."
    )

    def prepare(self, sandbox_dir: Path, skill_dir: Path | None) -> None:
        raise NotImplementedError(self._STUB_MSG)

    def run_task(self, task_prompt: str, sandbox_dir: Path) -> HarnessRunResult:
        raise NotImplementedError(self._STUB_MSG)
