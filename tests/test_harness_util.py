"""Unit tests for the shared harness helpers (prompt templates, path-safe names)."""

import pytest

from engine.harness.util import render_template, safe_path_component, strip_frontmatter

# ---------- strip_frontmatter ----------


def test_strip_frontmatter_removes_leading_block():
    text = "---\nname: judge\nversion: 2\n---\n\n# Body\nScore the run.\n"
    assert strip_frontmatter(text) == "# Body\nScore the run."


def test_strip_frontmatter_keeps_horizontal_rule_in_body():
    text = "---\nname: judge\n---\n\nIntro\n\n---\n\nOutro\n"
    assert strip_frontmatter(text) == "Intro\n\n---\n\nOutro"


def test_strip_frontmatter_without_block_is_noop():
    assert strip_frontmatter("# Plain body\n") == "# Plain body"


def test_strip_frontmatter_needs_closing_fence_at_line_start():
    """An unterminated frontmatter opener is content, not a fence to hunt for."""
    text = "--- not a fence\nbody ---\n"
    assert strip_frontmatter(text) == "--- not a fence\nbody ---"


# ---------- render_template ----------


def test_render_template_substitutes_known_placeholders():
    out = render_template("task {task_id} of {task_count}", {"task_id": "t1", "task_count": "6"})
    assert out == "task t1 of 6"


def test_render_template_leaves_unknown_and_json_braces():
    template = 'schema: {"id": "x"} — unknown: {other}'
    out = render_template(template, {"task_id": "t1"})
    assert out == template


def test_render_template_warns_about_placeholders_it_cannot_bind(caplog):
    """A renamed template slot used to reach the model as literal braces."""
    import logging

    with caplog.at_level(logging.WARNING):
        out = render_template("output: {judge_output}\n{task_id}", {"task_id": "t1"})

    assert "{judge_output}" in out
    assert "judge_output" in caplog.text
    assert "task_id" not in caplog.text


def test_template_placeholders_ignores_json_example_braces():
    from engine.harness.util import template_placeholders

    template = (
        "fill {skill_name} then answer\n"
        '```\n{\n  "tasks": [\n    {"id": "t1", "points": 2}\n  ]\n}\n```'
    )

    assert template_placeholders(template) == {"skill_name"}


def test_render_template_is_single_pass():
    """A value containing a placeholder literal must not be expanded again."""
    template = "skill: {skill_content}\nrubric: {rubric_json}"
    out = render_template(
        template,
        {"skill_content": "invoke {rubric_json} yourself", "rubric_json": '{"items": []}'},
    )
    assert "invoke {rubric_json} yourself" in out
    assert '{"items": []}' in out


def test_render_template_handles_newlines_in_values():
    out = render_template("output:\n{final_output}", {"final_output": "line1\nline2"})
    assert out == "output:\nline1\nline2"


# ---------- safe_path_component ----------


@pytest.mark.parametrize(
    "name,expected",
    [
        ("demo-skill", "demo-skill"),
        ("Demo Skill 2", "Demo-Skill-2"),
        ("../../etc/passwd", "etc-passwd"),
        ("a/b\\c", "a-b-c"),
        ("中文 技能", "中文-技能"),
        ("", "skill"),
        ("...", "skill"),
    ],
)
def test_safe_path_component(name, expected):
    assert safe_path_component(name) == expected
