"""Unit tests for the opencode harness adapter (mocked subprocess).

Event fixtures mirror the real stream captured in the M1 spike
(docs/plans/harness-spike-notes.md, opencode 1.18.21).
"""

import json
import os
import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from adapters.harness import (
    DshHarness,
    HarnessRunResult,
    OpenCodeHarness,
    extract_skill_name,
    parse_events,
)

E2E_ENABLED = (
    os.environ.get("SKILL_CERT_HARNESS_E2E") == "1" and shutil.which("opencode") is not None
)


# -- fixtures -----------------------------------------------------------------


def make_skill_dir(root: Path, name: str = "demo-skill") -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: demo skill\n---\n\n# Demo\n", encoding="utf-8"
    )
    return skill_dir


def ev(etype: str, part: dict, session_id: str = "ses_abc123") -> str:
    return json.dumps({"type": etype, "timestamp": 0, "sessionID": session_id, "part": part})


def skill_tool_event(called_name: str) -> str:
    return ev(
        "tool_use",
        {
            "type": "tool",
            "tool": "skill",
            "callID": "call_1",
            "state": {
                "status": "completed",
                "input": {"name": called_name},
                "output": "---\nname: demo\n---\nskill body",
                "time": {"start": 0, "end": 1},
            },
        },
    )


def step_finish_event(inp: int, out: int, reasoning: int = 0, cost: float = 0.0) -> str:
    return ev(
        "step_finish",
        {
            "type": "step-finish",
            "reason": "stop",
            "tokens": {
                "total": inp + out + reasoning,
                "input": inp,
                "output": out,
                "reasoning": reasoning,
                "cache": {"write": 0, "read": 0},
            },
            "cost": cost,
        },
    )


def full_stream() -> str:
    """Two-turn agent: loads the skill, then answers (spike-shaped)."""
    return "\n".join(
        [
            ev("step_start", {"type": "step-start", "id": "st_1"}),
            skill_tool_event("demo-skill"),
            step_finish_event(inp=58932, out=22, reasoning=48),
            ev("step_start", {"type": "step-start", "id": "st_2"}),
            ev("text", {"type": "text", "text": "intermediate thought"}),
            step_finish_event(inp=120, out=30, reasoning=0, cost=0.001),
            ev("text", {"type": "text", "text": "GREETING-PROTO v1\n- a\n- b\nEND-OF-GREETING"}),
        ]
    )


# -- extract_skill_name -------------------------------------------------------


def test_extract_skill_name_valid(tmp_path):
    skill_dir = make_skill_dir(tmp_path, "my-cool-skill")
    assert extract_skill_name(skill_dir) == "my-cool-skill"


def test_extract_skill_name_rejects_uppercase(tmp_path):
    skill_dir = tmp_path / "s"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: MySkill\ndescription: x\n---\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="naming rule"):
        extract_skill_name(skill_dir)


def test_extract_skill_name_rejects_underscore(tmp_path):
    skill_dir = tmp_path / "s"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: my_skill\ndescription: x\n---\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="naming rule"):
        extract_skill_name(skill_dir)


def test_extract_skill_name_missing_field(tmp_path):
    skill_dir = tmp_path / "s"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\ndescription: x\n---\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no 'name' field"):
        extract_skill_name(skill_dir)


def test_extract_skill_name_no_skill_md(tmp_path):
    with pytest.raises(FileNotFoundError):
        extract_skill_name(tmp_path)


def test_extract_skill_name_requires_frontmatter(tmp_path):
    """A ``name:`` line in the body must not be read as the declared skill name."""
    skill_dir = tmp_path / "s"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# Title\n\nname: sneaky-name\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"no '---' frontmatter"):
        extract_skill_name(skill_dir)


# -- prepare -------------------------------------------------------------------


def test_prepare_installs_skill_into_sandbox(tmp_path):
    skill_dir = make_skill_dir(tmp_path, "demo-skill")
    sandbox = tmp_path / "sbx"
    sandbox.mkdir()

    OpenCodeHarness(model="prov/m").prepare(sandbox, skill_dir)

    installed = sandbox / ".opencode" / "skills" / "demo-skill" / "SKILL.md"
    assert installed.is_file()
    assert "name: demo-skill" in installed.read_text(encoding="utf-8")


def test_prepare_without_skill_creates_nothing(tmp_path):
    sandbox = tmp_path / "sbx"
    sandbox.mkdir()

    OpenCodeHarness(model="prov/m").prepare(sandbox, None)

    assert not (sandbox / ".opencode").exists()


def test_prepare_replaces_existing_install(tmp_path):
    skill_dir = make_skill_dir(tmp_path, "demo-skill")
    sandbox = tmp_path / "sbx"
    stale = sandbox / ".opencode" / "skills" / "demo-skill" / "stale.txt"
    stale.parent.mkdir(parents=True)

    OpenCodeHarness(model="prov/m").prepare(sandbox, skill_dir)

    assert not stale.exists()
    assert (sandbox / ".opencode" / "skills" / "demo-skill" / "SKILL.md").is_file()


# -- parse_events --------------------------------------------------------------


def test_parse_events_full_stream():
    summary = parse_events(full_stream(), skill_name="demo-skill")

    assert summary["session_id"] == "ses_abc123"
    assert summary["final_output"] == "GREETING-PROTO v1\n- a\n- b\nEND-OF-GREETING"
    assert summary["skill_loaded"] is True
    assert summary["tool_call_count"] == 1
    # tokens: sum of per-step increments; out includes reasoning tokens
    assert summary["tokens_in"] == 58932 + 120
    assert summary["tokens_out"] == (22 + 48) + (30 + 0)
    assert summary["cost"] == pytest.approx(0.001)
    assert len(summary["events"]) == 7


def test_parse_events_skill_name_mismatch():
    summary = parse_events(full_stream(), skill_name="other-skill")
    assert summary["skill_loaded"] is False


def test_parse_events_any_skill_when_name_none():
    summary = parse_events(full_stream(), skill_name=None)
    assert summary["skill_loaded"] is True


def test_parse_events_tolerates_garbage_lines():
    stream = "not json\n\n" + full_stream() + "\n{broken"
    summary = parse_events(stream, skill_name="demo-skill")
    assert summary["skill_loaded"] is True
    assert len(summary["events"]) == 7


def test_parse_events_without_metering_returns_none():
    stream = "\n".join(
        [
            ev("step_start", {"type": "step-start"}),
            ev("text", {"type": "text", "text": "hi"}),
        ]
    )
    summary = parse_events(stream)
    assert summary["final_output"] == "hi"
    assert summary["tokens_in"] is None
    assert summary["tokens_out"] is None
    assert summary["cost"] is None


def test_parse_events_empty_stream():
    summary = parse_events("", skill_name="demo-skill")
    assert summary["final_output"] == ""
    assert summary["skill_loaded"] is False
    assert summary["session_id"] == ""


# -- run_task (mocked subprocess) -----------------------------------------------


def make_completed(stdout: str = "", returncode: int = 0, stderr: str = "") -> MagicMock:
    fake = MagicMock(spec=subprocess.CompletedProcess)
    fake.stdout = stdout
    fake.returncode = returncode
    fake.stderr = stderr
    return fake


def test_run_task_success_builds_command_and_parses(tmp_path):
    sandbox = tmp_path / "sbx"
    (sandbox / ".opencode" / "skills" / "demo-skill").mkdir(parents=True)
    harness = OpenCodeHarness(model="deepseek/deepseek-chat", title="skill-cert/ev1/with")

    with patch(
        "adapters.harness.opencode_harness.subprocess.run",
        return_value=make_completed(full_stream()),
    ) as mock_run:
        result = harness.run_task("greet me", sandbox)

    assert isinstance(result, HarnessRunResult)
    assert result.error is None
    assert result.exit_code == 0
    assert result.session_id == "ses_abc123"
    assert result.skill_loaded is True
    assert result.final_output.startswith("GREETING-PROTO")
    assert result.tokens_in == 59052
    assert result.duration_s >= 0.0

    cmd = mock_run.call_args[0][0]
    assert isinstance(cmd, list)  # list argv avoids Windows shell quoting
    assert cmd[0] == harness.opencode_bin
    idx = lambda flag: cmd.index(flag)  # noqa: E731
    assert cmd[idx("--format") + 1] == "json"
    assert cmd[idx("--model") + 1] == "deepseek/deepseek-chat"
    assert cmd[idx("--dir") + 1] == str(sandbox)
    assert cmd[idx("--title") + 1] == "skill-cert/ev1/with"
    assert "--auto" in cmd
    assert cmd[-1] == "greet me"


def test_run_task_detects_skill_from_sandbox_install(tmp_path):
    sandbox = tmp_path / "sbx"
    (sandbox / ".opencode" / "skills" / "demo-skill").mkdir(parents=True)
    harness = OpenCodeHarness(model="prov/m")

    with patch(
        "adapters.harness.opencode_harness.subprocess.run",
        return_value=make_completed(skill_tool_event("demo-skill")),
    ):
        result = harness.run_task("go", sandbox)
    assert result.skill_loaded is True


def test_run_task_no_skill_installed_means_match_any(tmp_path):
    sandbox = tmp_path / "sbx"
    sandbox.mkdir()
    harness = OpenCodeHarness(model="prov/m")

    with patch(
        "adapters.harness.opencode_harness.subprocess.run",
        return_value=make_completed(skill_tool_event("whatever")),
    ):
        result = harness.run_task("go", sandbox)
    assert result.skill_loaded is True


def test_run_task_timeout(tmp_path):
    sandbox = tmp_path / "sbx"
    sandbox.mkdir()
    harness = OpenCodeHarness(model="prov/m", timeout_s=5)

    with patch(
        "adapters.harness.opencode_harness.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=["opencode"], timeout=5),
    ):
        result = harness.run_task("go", sandbox)

    assert result.error is not None
    assert "timed out" in result.error
    assert result.exit_code == -1


def test_run_task_opencode_missing(tmp_path):
    sandbox = tmp_path / "sbx"
    sandbox.mkdir()
    harness = OpenCodeHarness(model="prov/m", opencode_bin="definitely-missing-oc")

    with patch(
        "adapters.harness.opencode_harness.subprocess.run",
        side_effect=FileNotFoundError("no such file"),
    ):
        result = harness.run_task("go", sandbox)

    assert result.error is not None
    assert "not found" in result.error


def test_run_task_nonzero_exit_reports_stderr(tmp_path):
    sandbox = tmp_path / "sbx"
    sandbox.mkdir()
    harness = OpenCodeHarness(model="prov/m")

    with patch(
        "adapters.harness.opencode_harness.subprocess.run",
        return_value=make_completed("", returncode=1, stderr="boom: bad model"),
    ):
        result = harness.run_task("go", sandbox)

    assert result.exit_code == 1
    assert result.error == "boom: bad model"


def test_run_task_attach_url_adds_flag(tmp_path):
    sandbox = tmp_path / "sbx"
    sandbox.mkdir()
    harness = OpenCodeHarness(model="prov/m")
    harness._attach_url = "http://127.0.0.1:4096"

    with patch(
        "adapters.harness.opencode_harness.subprocess.run",
        return_value=make_completed(""),
    ) as mock_run:
        harness.run_task("go", sandbox)

    cmd = mock_run.call_args[0][0]
    assert cmd[cmd.index("--attach") + 1] == "http://127.0.0.1:4096"


def test_run_task_rejects_missing_sandbox_without_spawning(tmp_path):
    harness = OpenCodeHarness(model="prov/m")

    with patch("adapters.harness.opencode_harness.subprocess.run") as mock_run:
        result = harness.run_task("go", tmp_path / "absent")

    assert result.exit_code == -1
    assert "sandbox directory does not exist" in result.error
    mock_run.assert_not_called()


def test_run_task_rejects_empty_prompt_without_spawning(tmp_path):
    sandbox = tmp_path / "sbx"
    sandbox.mkdir()
    harness = OpenCodeHarness(model="prov/m")

    with patch("adapters.harness.opencode_harness.subprocess.run") as mock_run:
        result = harness.run_task("   ", sandbox)

    assert result.error == "task prompt is empty"
    mock_run.assert_not_called()


def test_run_task_rejects_flag_like_prompt(tmp_path):
    """A prompt beginning with '-' must not reach argv as a possible flag."""
    sandbox = tmp_path / "sbx"
    sandbox.mkdir()
    harness = OpenCodeHarness(model="prov/m")

    with patch("adapters.harness.opencode_harness.subprocess.run") as mock_run:
        result = harness.run_task("--model other - do the task", sandbox)

    assert result.exit_code == -1
    assert "as a flag" in result.error
    mock_run.assert_not_called()


def test_run_task_rejects_whitespace_then_dash_prompt(tmp_path):
    """The guard is a superset: leading blank space cannot smuggle a flag in."""
    sandbox = tmp_path / "sbx"
    sandbox.mkdir()
    harness = OpenCodeHarness(model="prov/m")

    with patch("adapters.harness.opencode_harness.subprocess.run") as mock_run:
        result = harness.run_task("   --model other", sandbox)

    assert result.exit_code == -1
    assert "as a flag" in result.error
    mock_run.assert_not_called()


def test_run_task_warns_when_sandbox_holds_two_skills(tmp_path, caplog):
    """Ambiguous install widens skill matching — loudly, not silently."""
    sandbox = tmp_path / "sbx"
    for name in ("alpha-skill", "beta-skill"):
        (sandbox / ".opencode" / "skills" / name).mkdir(parents=True)
    harness = OpenCodeHarness(model="prov/m")

    with patch(
        "adapters.harness.opencode_harness.subprocess.run",
        return_value=make_completed(skill_tool_event("beta-skill")),
    ):
        with caplog.at_level("WARNING", logger="adapters.harness.opencode_harness"):
            result = harness.run_task("go", sandbox)

    assert "2 installed skills" in caplog.text
    assert "alpha-skill, beta-skill" in caplog.text
    assert result.skill_loaded is True


# -- serve mode -----------------------------------------------------------------


def test_ensure_server_attaches_when_port_open():
    harness = OpenCodeHarness(model="prov/m")
    with patch.object(OpenCodeHarness, "_port_open", return_value=True):
        url = harness.ensure_server()
    assert url == "http://127.0.0.1:4096"
    assert harness._attach_url == url


def test_ensure_server_raises_when_opencode_dies():
    harness = OpenCodeHarness(model="prov/m")
    dead = MagicMock()
    dead.poll.return_value = 1
    dead.returncode = 1
    with patch.object(OpenCodeHarness, "_port_open", return_value=False):
        with patch("adapters.harness.opencode_harness.subprocess.Popen", return_value=dead):
            with pytest.raises(RuntimeError, match="exited early"):
                harness.ensure_server(wait_s=0.1)


def test_ensure_server_does_not_spawn_when_the_port_is_already_open():
    harness = OpenCodeHarness(model="prov/m")
    with patch.object(OpenCodeHarness, "_port_open", return_value=True):
        with patch("adapters.harness.opencode_harness.subprocess.Popen") as mock_popen:
            harness.ensure_server()

    mock_popen.assert_not_called()
    assert harness._server_process is None


def test_ensure_server_warns_when_attaching_to_a_foreign_listener(caplog):
    """A server on 4096 that this process did not start must be named out loud."""
    import logging

    harness = OpenCodeHarness(model="prov/m")
    with caplog.at_level(logging.WARNING):
        with patch.object(OpenCodeHarness, "_port_open", return_value=True):
            harness.ensure_server()

    assert "did not start" in caplog.text


def test_ensure_server_terminates_a_child_that_never_becomes_ready():
    harness = OpenCodeHarness(model="prov/m")
    child = MagicMock()
    child.poll.return_value = None
    with patch.object(OpenCodeHarness, "_port_open", return_value=False):
        with patch("adapters.harness.opencode_harness.subprocess.Popen", return_value=child):
            with pytest.raises(TimeoutError, match="did not become ready"):
                harness.ensure_server(wait_s=0.0)

    child.terminate.assert_called_once()
    assert harness._server_process is None
    assert harness._attach_url is None


def test_shutdown_server_terminates_only_the_child_this_instance_started():
    harness = OpenCodeHarness(model="prov/m")
    child = MagicMock()
    child.poll.return_value = None
    with patch.object(OpenCodeHarness, "_port_open", side_effect=[False, True]):
        with patch("adapters.harness.opencode_harness.subprocess.Popen", return_value=child):
            url = harness.ensure_server(wait_s=1.0)

    assert url == "http://127.0.0.1:4096"
    assert harness._server_process is child

    harness.shutdown_server()
    child.terminate.assert_called_once()
    assert harness._server_process is None

    harness.shutdown_server()
    assert child.terminate.call_count == 1


# -- dsh stub --------------------------------------------------------------------


def test_dsh_harness_stub_raises(tmp_path):
    stub = DshHarness()
    with pytest.raises(NotImplementedError, match="stub"):
        stub.prepare(tmp_path, None)
    with pytest.raises(NotImplementedError, match="stub"):
        stub.run_task("go", tmp_path)


# -- E2E smoke (opt-in) ------------------------------------------------------------


@pytest.mark.skipif(not E2E_ENABLED, reason="set SKILL_CERT_HARNESS_E2E=1 with opencode installed")
def test_e2e_opencode_run_smoke(tmp_path):
    """1 task x 1 run against a real opencode (no skill installed)."""
    harness = OpenCodeHarness(model="opencode/hy3-free", timeout_s=300)
    sandbox = tmp_path / "sbx"
    sandbox.mkdir()
    harness.prepare(sandbox, None)

    result = harness.run_task("Reply with exactly: OK", sandbox)

    assert result.error is None, f"opencode failed: {result.error}"
    assert result.session_id.startswith("ses_")
    assert result.final_output.strip() != ""
