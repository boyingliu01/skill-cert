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

import atexit
import json
import logging
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path

from .base import HarnessRunResult

logger = logging.getLogger(__name__)

# opencode requires skill directory names to match this pattern
SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
FRONTMATTER_NAME_RE = re.compile(r"^name:\s*[\"']?([A-Za-z0-9_-]+)[\"']?\s*$", re.MULTILINE)

DEFAULT_TIMEOUT_S = 600
SERVE_HOST = "127.0.0.1"
SERVE_PORT = 4096


def extract_skill_name(skill_dir: Path) -> str:
    """Parse the ``name`` field from SKILL.md frontmatter and validate it.

    The search is limited to the frontmatter block: a body line such as
    ``name: something`` must not be mistaken for the declared skill name.
    """
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        raise FileNotFoundError(f"SKILL.md not found in {skill_dir}")
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    fm = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if fm is None:
        raise ValueError(f"SKILL.md has no '---' frontmatter block: {skill_md}")
    name_match = FRONTMATTER_NAME_RE.search(fm.group(1))
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
        self._server_process: subprocess.Popen | None = None
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
        """Run ``opencode run`` non-interactively and parse its event stream.

        The prompt is the last argv element, so a leading ``-`` would be read as
        an option by opencode's parser instead of as task text. No end-of-options
        separator is verified for the pinned CLI version, so such a prompt is
        refused: silently executing something else is worse than a failed run.
        """
        if not task_prompt.strip():
            return HarnessRunResult(exit_code=-1, duration_s=0.0, error="task prompt is empty")
        if task_prompt.lstrip().startswith("-"):
            return HarnessRunResult(
                exit_code=-1,
                duration_s=0.0,
                error="task prompt must not start with '-' (opencode would parse it as a flag)",
            )
        if not sandbox_dir.is_dir():
            return HarnessRunResult(
                exit_code=-1,
                duration_s=0.0,
                error=f"sandbox directory does not exist: {sandbox_dir}",
            )

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
            stderr_tail = (proc.stderr or "").strip()[-2000:]
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
        """Name of the single skill installed in the sandbox (None = match any).

        ``prepare`` installs exactly one skill, so more than one directory means
        the sandbox was reused or hand-modified: the trigger metric would
        silently widen to "any skill call counts", so it is logged.
        """
        skills_root = sandbox_dir / ".opencode" / "skills"
        if not skills_root.is_dir():
            return None
        names = [p.name for p in skills_root.iterdir() if p.is_dir()]
        if len(names) > 1:
            logger.warning(
                "sandbox %s holds %d installed skills (%s); skill_loaded falls back to "
                "matching any skill call",
                sandbox_dir,
                len(names),
                ", ".join(sorted(names)),
            )
            return None
        return names[0] if names else None

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
        """Detect or start ``opencode serve``; enable --attach for later runs.

        A server this instance started is owned by it: the handle is kept so the
        child is terminated on failure paths, at interpreter exit, and by
        ``shutdown_server``. A server that was already listening is left alone.
        """
        url = f"http://{host}:{port}"
        if self._port_open(host, port):
            if self._server_process is None:
                # Identity of an already-listening server cannot be verified from
                # here — say plainly that this run attaches to someone else's proc.
                logger.warning(
                    "attaching to an existing listener on %s that this process did not "
                    "start; it will not be terminated by shutdown_server",
                    url,
                )
            self._attach_url = url
            return url

        proc = subprocess.Popen(
            [self.opencode_bin, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._server_process = proc
        atexit.register(self.shutdown_server)
        deadline = time.time() + wait_s
        while time.time() < deadline:
            if self._port_open(host, port):
                self._attach_url = url
                return url
            if proc.poll() is not None:
                self.shutdown_server()
                raise RuntimeError(f"opencode serve exited early (code {proc.returncode})")
            time.sleep(0.5)
        self.shutdown_server()
        raise TimeoutError(f"opencode serve did not become ready in {wait_s}s")

    def shutdown_server(self) -> None:
        """Terminate the ``opencode serve`` child started by this instance, if any."""
        proc, self._server_process = self._server_process, None
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
