"""OpenCode harness — drives ``opencode run`` as a non-interactive subprocess.

Event-stream parsing rules come from the M1 spike
(docs/plans/harness-spike-notes.md, opencode 1.18.21 on Windows):

- stdout carries one JSON event per line: ``{"type", "timestamp", "sessionID", "part"}``
- final_output  = ``part.text`` of the LAST ``type=="text"`` event
- skill_loaded  = any ``tool_use`` event whose ``part.tool == "skill"`` and
  ``part.state.input.name`` matches the skill installed in the sandbox
- tokens        = sum over ``step_finish`` events (input / output+reasoning);
  each step reports increments, cache reads excluded
- cost          = sum of ``part.cost`` over ``step_finish`` events (0 for free
  models — pricing-table estimation happens at report level, not here)
"""

from __future__ import annotations

import json
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path

from .base import HarnessRunResult

# opencode requires skill directory names to match this pattern
SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
FRONTMATTER_NAME_RE = re.compile(r"^name:\s*[\"']?([A-Za-z0-9_-]+)[\"']?\s*$", re.MULTILINE)

DEFAULT_TIMEOUT_S = 600
SERVE_HOST = "127.0.0.1"
SERVE_PORT = 4096


def extract_skill_name(skill_dir: Path) -> str:
    """Parse the ``name`` field from SKILL.md frontmatter and validate it."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        raise FileNotFoundError(f"SKILL.md not found in {skill_dir}")
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    fm = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    block = fm.group(1) if fm else text
    name_match = FRONTMATTER_NAME_RE.search(block)
    if not name_match:
        raise ValueError(f"SKILL.md frontmatter has no 'name' field: {skill_md}")
    name = name_match.group(1)
    if not SKILL_NAME_RE.match(name):
        raise ValueError(
            f"Skill name '{name}' violates opencode naming rule ^[a-z0-9]+(-[a-z0-9]+)*$"
        )
    return name


def parse_events(raw_stdout: str, skill_name: str | None = None) -> dict:
    """Parse ``opencode run --format json`` stdout into summary fields.

    Malformed lines are skipped (the stream may interleave non-JSON output).
    ``skill_name=None`` means any native skill tool call counts as loaded.
    """
    events: list[dict] = []
    for line in raw_stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    session_id = ""
    final_output = ""
    skill_loaded = False
    tool_call_count = 0
    tokens_in = 0
    tokens_out = 0
    cost = 0.0
    has_token_event = False
    has_cost_event = False

    for ev in events:
        session_id = ev.get("sessionID") or session_id
        etype = ev.get("type")
        part = ev.get("part") or {}
        if etype == "tool_use":
            tool_call_count += 1
            if part.get("tool") == "skill":
                called = ((part.get("state") or {}).get("input") or {}).get("name")
                if skill_name is None or called == skill_name:
                    skill_loaded = True
        elif etype == "text":
            # multi-turn agents emit several text events; the last one is the reply
            if part.get("text"):
                final_output = part["text"]
        elif etype == "step_finish":
            tokens = part.get("tokens") or {}
            if tokens:
                has_token_event = True
                tokens_in += tokens.get("input") or 0
                tokens_out += (tokens.get("output") or 0) + (tokens.get("reasoning") or 0)
            if part.get("cost") is not None:
                has_cost_event = True
                cost += part["cost"]

    return {
        "session_id": session_id,
        "final_output": final_output,
        "skill_loaded": skill_loaded,
        "tool_call_count": tool_call_count,
        "tokens_in": tokens_in if has_token_event else None,
        "tokens_out": tokens_out if has_token_event else None,
        "cost": cost if has_cost_event else None,
        "events": events,
    }


class OpenCodeHarness:
    """HarnessAdapter implementation backed by the opencode CLI."""

    def __init__(
        self,
        model: str,
        opencode_bin: str | None = None,
        timeout_s: int = DEFAULT_TIMEOUT_S,
        title: str = "skill-cert/run",
        serve: bool = False,
    ):
        self.model = model  # provider/model, e.g. deepseek/deepseek-chat
        self.opencode_bin = opencode_bin or shutil.which("opencode") or "opencode"
        self.timeout_s = timeout_s
        self.title = title  # --title value; the evaluator updates it per run
        self._attach_url: str | None = None
        if serve:
            self.ensure_server()

    # -- HarnessAdapter protocol ------------------------------------------

    def prepare(self, sandbox_dir: Path, skill_dir: Path | None) -> None:
        """Install the skill into ``<sandbox>/.opencode/skills/<name>/``.

        skill_dir=None means the "without" condition: no skills directory is
        created at all, so the agent cannot discover the skill.
        """
        if skill_dir is None:
            return
        name = extract_skill_name(skill_dir)
        dest = sandbox_dir / ".opencode" / "skills" / name
        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(skill_dir, dest)

    def run_task(self, task_prompt: str, sandbox_dir: Path) -> HarnessRunResult:
        """Run ``opencode run`` non-interactively and parse its event stream."""
        cmd = [
            self.opencode_bin,
            "run",
            "--format",
            "json",
            "--model",
            self.model,
            "--auto",
            "--dir",
            str(sandbox_dir),
            "--title",
            self.title,
        ]
        if self._attach_url:
            cmd += ["--attach", self._attach_url]
        cmd.append(task_prompt)

        start = time.perf_counter()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_s,
            )
        except subprocess.TimeoutExpired:
            return HarnessRunResult(
                exit_code=-1,
                duration_s=time.perf_counter() - start,
                error=f"opencode run timed out after {self.timeout_s}s",
            )
        except FileNotFoundError:
            return HarnessRunResult(
                exit_code=-1,
                duration_s=time.perf_counter() - start,
                error=f"opencode executable not found: {self.opencode_bin}",
            )
        duration_s = time.perf_counter() - start

        summary = parse_events(proc.stdout, skill_name=self._installed_skill_name(sandbox_dir))
        error = None
        if proc.returncode != 0:
            stderr_tail = (proc.stderr or "").strip()[-500:]
            error = stderr_tail or f"opencode exited with code {proc.returncode}"

        return HarnessRunResult(
            session_id=summary["session_id"],
            exit_code=proc.returncode,
            final_output=summary["final_output"],
            events=summary["events"],
            skill_loaded=summary["skill_loaded"],
            tool_call_count=summary["tool_call_count"],
            tokens_in=summary["tokens_in"],
            tokens_out=summary["tokens_out"],
            cost=summary["cost"],
            duration_s=duration_s,
            error=error,
        )

    # -- serve mode --------------------------------------------------------

    def _installed_skill_name(self, sandbox_dir: Path) -> str | None:
        """Name of the single skill installed in the sandbox (None = match any)."""
        skills_root = sandbox_dir / ".opencode" / "skills"
        if not skills_root.is_dir():
            return None
        names = [p.name for p in skills_root.iterdir() if p.is_dir()]
        return names[0] if len(names) == 1 else None

    @staticmethod
    def _port_open(host: str, port: int, timeout_s: float = 1.0) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout_s):
                return True
        except OSError:
            return False

    def ensure_server(
        self, host: str = SERVE_HOST, port: int = SERVE_PORT, wait_s: float = 30.0
    ) -> str:
        """Detect or start ``opencode serve``; enable --attach for later runs."""
        url = f"http://{host}:{port}"
        if not self._port_open(host, port):
            proc = subprocess.Popen(
                [self.opencode_bin, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            deadline = time.time() + wait_s
            while time.time() < deadline:
                if self._port_open(host, port):
                    break
                if proc.poll() is not None:
                    raise RuntimeError(f"opencode serve exited early (code {proc.returncode})")
                time.sleep(0.5)
            else:
                raise TimeoutError(f"opencode serve did not become ready in {wait_s}s")
        self._attach_url = url
        return url
