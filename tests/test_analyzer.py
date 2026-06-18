"""Tests for engine/analyzer.py — SKILL.md parsing."""


import pytest

from engine.analyzer import parse_skill_md


def _section_patterns() -> dict[str, list[str]]:
    """Return all section name aliases that should be recognized.
    Mirrors the patterns in _extract_* functions.
    """
    return {
        "workflow": [
            "Workflow", "Process", "Flow", "完整流程", "核心流程", "流程", "步骤", "工作流程"
        ],
        "anti_patterns": [
            "Anti-Patterns", "Anti-Patterns", "What Not To Do", "Gotchas",
            "反模式", "错误做法", "注意事项",
        ],
        "output_format": ["Output Format", "Response Format", "返回格式", "输出格式", "响应格式"],
        "triggers": [
            "Triggers", "Trigger", "What I Do", "When To Use", "触发条件", "何时使用", "使用场景"
        ],
    }


class TestParseSkillMd:
    """Test SKILL.md parsing with various formats."""

    def test_parse_minimal_skill(self, tmp_path):
        """Parse a minimal SKILL.md with just name and description."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""---
name: test-skill
description: A simple test skill
---
# Test Skill

## Workflow
1. Step one
2. Step two
""")
        result = parse_skill_md(str(skill_file))
        assert result["name"] == "test-skill"
        assert "simple test skill" in result["description"]
        assert len(result["workflow_steps"]) == 2

    def test_parse_full_skill(self, tmp_path):
        """Parse a complete SKILL.md with all sections."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""---
name: delphi-review
description: Multi-expert consensus review
---
# Delphi Review

## Workflow
- Phase 0: Preparation
- Round 1: Anonymous review
- Round 2: Consensus check

## Anti-Patterns
| Pattern | Fix |
|---------|-----|
| Skip Round 1 | Always run all rounds |

## Output Format
- Consensus report
- specification.yaml

## Examples
- Review design documents
- Code walkthrough
""")
        result = parse_skill_md(str(skill_file))
        assert result["name"] == "delphi-review"
        assert len(result["workflow_steps"]) == 3
        assert len(result["anti_patterns"]) == 1
        assert len(result["output_format"]) == 2
        assert len(result["examples"]) == 2
        assert result["parse_method"] in ("regex", "hybrid")
        assert result["parse_confidence"] > 0

    def test_parse_no_frontmatter(self, tmp_path):
        """Parse SKILL.md without YAML frontmatter — should fallback."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""# My Skill

Some description here.

## Process
1. Do something
""")
        result = parse_skill_md(str(skill_file))
        assert result["name"] == "my-skill"
        assert result["parse_method"] in ("regex", "llm", "hybrid")

    def test_parse_long_skill_truncation(self, tmp_path):
        """Very long SKILL.md should record content_length."""
        skill_file = tmp_path / "SKILL.md"
        content = "---\nname: long-skill\ndescription: test\n---\n" + "# Header\n" * 500
        skill_file.write_text(content)
        result = parse_skill_md(str(skill_file))
        assert result["content_length"] > 0
        assert result["name"] == "long-skill"

    def test_parse_nonexistent_file(self):
        """Should raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            parse_skill_md("/nonexistent/SKILL.md")

    def test_bash_fenced_code_block_not_interactive(self, tmp_path):
        """Regression test for #10: fenced bash blocks must not trigger
        the interactive skill false positive penalty."""
        bt = "\x60\x60\x60"
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(f"""---
name: cli-helper
description: A CLI helper tool with installation commands
---
# CLI Helper

## Workflow
1. Run the installation command

### Installation

{bt}bash
npm install my-package
{bt}

{bt}bash
export MY_VAR=hello
{bt}

## Scope
Use: run installation commands. Does NOT modify source code.
""")
        result = parse_skill_md(str(skill_file))
        sv = result.get("schema_validation", {})
        assert sv.get("is_valid") is True, f"False positive: {sv}"
        assert sv.get("confidence_penalty", 0) == pytest.approx(0.0, abs=0.01)

    def test_really_interactive_skill_still_detected(self, tmp_path):
        """Interactive skills with Security Notes should still work after #10 fix."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""---
name: interactive-shell
description: An interactive shell skill
---
# Interactive Shell

## Workflow
1. Ask the user for a command

## Security Notes
This skill executes arbitrary shell commands.

## Permissions
- dangerous_cmd: shell execution

## Scope
Use: execute user-provided shell commands. Does NOT run commands autonomously.
""")
        result = parse_skill_md(str(skill_file))
        sv = result.get("schema_validation", {})
        assert sv.get("is_valid") is True

    # ── Section alias tests (v0.4.0, Issue #47) ──────────────────────────────

    def _make_alias_skill(self, tmp_path, section_name: str, section_content: str) -> str:
        """Helper: create a SKILL.md with a custom section name and frontmatter."""
        safe_name = section_name.replace(" ", "-").replace("/", "-")
        desc = section_name.replace('"', "'")
        path = tmp_path / f"alias-{safe_name}.md"
        path.write_text(f"""---
name: alias-test
description: test-{desc}
---

# Alias Test

## {section_name}
{section_content}
""")
        return str(path)

    @pytest.mark.parametrize("alias", _section_patterns()["anti_patterns"])
    def test_anti_patterns_alias(self, tmp_path, alias: str):
        """Each anti-pattern alias should be extracted as anti_patterns."""
        skill_path = self._make_alias_skill(
            tmp_path, alias,
            "- First anti-pattern\n- Second anti-pattern\n",
        )
        result = parse_skill_md(skill_path)
        assert len(result["anti_patterns"]) == 2, (
            f"Alias '{alias}' should yield 2 anti_patterns, got {result['anti_patterns']}"
        )

    @pytest.mark.parametrize("alias", _section_patterns()["workflow"])
    def test_workflow_alias(self, tmp_path, alias: str):
        """Each workflow alias should be extracted as workflow_steps."""
        skill_path = self._make_alias_skill(
            tmp_path, alias,
            "1. Step Alpha\n2. Step Beta\n",
        )
        result = parse_skill_md(skill_path)
        assert len(result["workflow_steps"]) == 2, (
            f"Alias '{alias}' should yield 2 workflow steps, got {result['workflow_steps']}"
        )

    @pytest.mark.parametrize("alias", _section_patterns()["output_format"])
    def test_output_format_alias(self, tmp_path, alias: str):
        """Each output format alias should be extracted as output_format."""
        skill_path = self._make_alias_skill(
            tmp_path, alias,
            "- JSON report\n- YAML config\n",
        )
        result = parse_skill_md(skill_path)
        assert len(result["output_format"]) == 2, (
            f"Alias '{alias}' should yield 2 output_format items, got {result['output_format']}"
        )

    @pytest.mark.parametrize("alias", _section_patterns()["triggers"])
    def test_triggers_alias(self, tmp_path, alias: str):
        """Each triggers alias should be extracted as triggers."""
        skill_path = self._make_alias_skill(
            tmp_path, alias,
            "- trigger-a\n- trigger-b\n",
        )
        result = parse_skill_md(skill_path)
        assert len(result["triggers"]) >= 2, (
            f"Alias '{alias}' should yield >= 2 triggers, got {result['triggers']}"
        )
