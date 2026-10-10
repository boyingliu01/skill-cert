"""Tests for the 'skill-cert harness' CLI argument surface."""

import pytest

from skill_cert.cli.harness import _build_parser

BASE = ["--skill", "SKILL.md", "--model", "prov/m"]

NON_POSITIVE = [("tasks", "0"), ("runs", "0"), ("task-timeout", "-1")]


def test_parser_defaults():
    args = _build_parser().parse_args(BASE)

    assert (args.tasks, args.runs, args.task_timeout, args.harness) == (6, 1, 600, "opencode")


def test_parser_accepts_positive_counts():
    args = _build_parser().parse_args(
        [*BASE, "--tasks", "3", "--runs", "2", "--task-timeout", "90"]
    )

    assert (args.tasks, args.runs, args.task_timeout) == (3, 2, 90)


@pytest.mark.parametrize("flag,value", NON_POSITIVE)
def test_parser_rejects_non_positive_counts(flag, value, capsys):
    """Zero/negative counts must fail at parse time, naming the bound."""
    with pytest.raises(SystemExit):
        _build_parser().parse_args([*BASE, f"--{flag}", value])

    assert "must be >= 1" in capsys.readouterr().err


@pytest.mark.parametrize("flag,value", NON_POSITIVE)
def test_parser_rejects_non_integer_counts(flag, value):
    with pytest.raises(SystemExit):
        _build_parser().parse_args([*BASE, f"--{flag}", "abc"])


def test_warn_circularity_uses_the_public_family_helper(capsys):
    """The CLI must not reach into a private engine symbol for this check."""
    from skill_cert.cli.harness import _warn_circularity

    _warn_circularity("openai/gpt-4o", "gpt-4o-mini")
    assert "circularity risk" in capsys.readouterr().err

    _warn_circularity("deepseek/deepseek-chat", "gpt-4o-mini")
    assert "circularity risk" not in capsys.readouterr().err


def test_dsh_harness_is_rejected_before_any_instantiation(tmp_path, capsys):
    """The dsh stub stays behind the CLI guard — no adapter object is constructed."""
    from skill_cert.cli.harness import _handle_harness

    skill = tmp_path / "SKILL.md"
    skill.write_text("---\nname: demo\n---\n\nbody\n", encoding="utf-8")

    code = _handle_harness(
        ["harness", "--skill", str(skill), "--model", "prov/m", "--harness", "dsh"]
    )

    assert code == 1
    assert "dsh harness is not implemented" in capsys.readouterr().err
