"""Tests for engine/analyzer.py — SKILL.md parsing."""

import pytest

from engine.analyzer import parse_skill_md


def _section_patterns() -> dict[str, list[str]]:
    """Return all section name aliases that should be recognized.
    Mirrors the patterns in _extract_* functions.
    """
    return {
        "workflow": [
            "Workflow",
            "Process",
            "Flow",
            "完整流程",
            "核心流程",
            "流程",
            "步骤",
            "工作流程",
        ],
        "anti_patterns": [
            "Anti-Patterns",
            "Anti-Patterns",
            "What Not To Do",
            "Gotchas",
            "反模式",
            "错误做法",
            "注意事项",
        ],
        "output_format": ["Output Format", "Response Format", "返回格式", "输出格式", "响应格式"],
        "triggers": [
            "Triggers",
            "Trigger",
            "What I Do",
            "When To Use",
            "触发条件",
            "何时使用",
            "使用场景",
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
            tmp_path,
            alias,
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
            tmp_path,
            alias,
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
            tmp_path,
            alias,
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
            tmp_path,
            alias,
            "- trigger-a\n- trigger-b\n",
        )
        result = parse_skill_md(skill_path)
        assert len(result["triggers"]) >= 2, (
            f"Alias '{alias}' should yield >= 2 triggers, got {result['triggers']}"
        )


class TestSkillTypeDetection:
    """Test skill_type field detection in SkillSpec and parse_skill_md()."""

    def test_skill_spec_has_skill_type_default(self):
        """SkillSpec should have skill_type field defaulting to 'agent_guide'."""
        from engine.analyzer import SkillSpec

        spec = SkillSpec(name="test")
        assert spec.skill_type == "agent_guide"

    def test_skill_type_in_model_dump(self):
        """skill_type should appear in model_dump output."""
        from engine.analyzer import SkillSpec

        spec = SkillSpec(name="test")
        dumped = spec.model_dump(by_alias=True)
        assert "skill_type" in dumped
        assert dumped["skill_type"] == "agent_guide"

    def test_parse_agent_guide_default(self, tmp_path):
        """Regular agent guide skill should have skill_type='agent_guide'."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""---
name: review-skill
description: A code review skill
---
# Review Skill

## Workflow
1. Read the code
2. Check for issues
3. Provide feedback
""")
        result = parse_skill_md(str(skill_file))
        assert result["skill_type"] == "agent_guide"

    def test_parse_cli_tool_detection(self, tmp_path):
        """CLI tool skill should be detected from ## Commands section + flag patterns."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""---
name: skill-cert
description: AI Skill Evaluation Engine
---
# Skill-Cert

## Usage

```bash
skill-cert --skill /path/to/SKILL.md --models "m1=url,key"
```

## Commands

- `skill-cert evaluate` — Run evaluation
- `skill-cert setup` — Interactive config
- `skill-cert --version` — Print version

## CLI Flags

- `--skill` — Path to SKILL.md
- `--models` — Model configuration
- `--output` — Output directory
- `--strict-schema` — Strict schema validation
""")
        result = parse_skill_md(str(skill_file))
        assert result["skill_type"] == "cli_tool"

    def test_parse_cli_tool_from_usage_with_flags(self, tmp_path):
        """CLI tool detected from ## Usage section with --flag patterns."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""---
name: my-cli
description: A CLI helper tool
---
# My CLI

## Usage

```
my-cli --input file.txt --output result.json --verbose
```

Some description of the tool.
""")
        result = parse_skill_md(str(skill_file))
        assert result["skill_type"] == "cli_tool"

    def test_parse_library_detection(self, tmp_path):
        """Library skill should be detected from ## API section."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""---
name: data-utils
description: Data utility library
---
# Data Utils

## API

### parse_csv(content: str) -> list[dict]
Parse CSV content into list of dicts.

### validate_schema(data: dict, schema: dict) -> bool
Validate data against schema.

## Functions

- `parse_csv` — Parse CSV files
- `validate_schema` — Schema validation
""")
        result = parse_skill_md(str(skill_file))
        assert result["skill_type"] == "library"

    def test_parse_library_from_import_patterns(self, tmp_path):
        """Library detected from import statements in code blocks."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""---
name: my-lib
description: A utility library
---
# My Lib

## Usage

```python
from my_lib import parse_data, transform
result = parse_data("input.csv")
```
""")
        result = parse_skill_md(str(skill_file))
        assert result["skill_type"] == "library"

    def test_backward_compat_existing_skills(self, tmp_path):
        """Existing skills without skill_type signals should default to agent_guide."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""---
name: delphi-review
description: Multi-expert consensus review
---
# Delphi Review

## Workflow
- Phase 0: Preparation
- Round 1: Anonymous review

## Anti-Patterns
| Pattern | Fix |
|---------|-----|
| Skip Round 1 | Always run all rounds |

## Output Format
- Consensus report
""")
        result = parse_skill_md(str(skill_file))
        assert result["skill_type"] == "agent_guide"
        assert result["name"] == "delphi-review"
        assert len(result["workflow_steps"]) >= 1


class TestReferencesLoading:
    """Test references/ directory loading in parse_skill_md()."""

    def test_no_references_dir_returns_empty(self, tmp_path):
        """When no references/ dir exists, references should be empty dict."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""---
name: test
description: test
---
# Test
""")
        result = parse_skill_md(str(skill_file))
        assert "references" in result
        assert result["references"] == {}

    def test_loads_reference_files(self, tmp_path):
        """All .md files in references/ should be loaded."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""---
name: test
description: test
---
# Test
""")
        refs_dir = tmp_path / "references"
        refs_dir.mkdir()
        (refs_dir / "setup.md").write_text("# Setup\nConfig goes here.")
        (refs_dir / "metrics.md").write_text("# Metrics\nL1-L8 details.")

        result = parse_skill_md(str(skill_file))
        refs = result["references"]
        assert len(refs) == 2
        assert refs["setup.md"].startswith("# Setup")
        assert refs["metrics.md"].startswith("# Metrics")

    def test_references_in_skill_spec(self, tmp_path):
        """SkillSpec.model_dump should include references field."""
        from engine.analyzer import SkillSpec

        spec = SkillSpec(name="test", references={"a.md": "content"})
        dumped = spec.model_dump(by_alias=True)
        assert "references" in dumped
        assert dumped["references"] == {"a.md": "content"}

    def test_overloaded_name_uses_file_disambiguation(self, tmp_path):
        """_load_references sorts files, ensuring deterministic loading order."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""---
name: test
description: test
---
# Test
""")
        refs_dir = tmp_path / "references"
        refs_dir.mkdir()
        (refs_dir / "z.md").write_text("z")
        (refs_dir / "a.md").write_text("a")

        result = parse_skill_md(str(skill_file))
        keys = list(result["references"].keys())
        assert keys == ["a.md", "z.md"]

    def test_backward_compat_no_references(self, tmp_path):
        """Existing skills without references/ should continue to work."""
        result = parse_skill_md(str(tmp_path / "nonexistent.md")) if False else None
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""---
name: legacy
description: Legacy skill
---
# Legacy
""")
        result = parse_skill_md(str(skill_file))
        assert result["references"] == {}
        assert result["name"] == "legacy"
        assert result["description"] == "Legacy skill"

    def test_non_md_files_ignored(self, tmp_path):
        """Only .md files are loaded; other extensions are skipped."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""---
name: test
description: test
---
# Test
""")
        refs_dir = tmp_path / "references"
        refs_dir.mkdir()
        (refs_dir / "readme.md").write_text("ref content")
        (refs_dir / "notes.txt").write_text("not loaded")
        (refs_dir / "config.yaml").write_text("yaml: data")

        result = parse_skill_md(str(skill_file))
        assert len(result["references"]) == 1
        assert "readme.md" in result["references"]

    def test_routing_skill_md_extracts_from_references(self, tmp_path):
        """Routing SKILL.md with references/ should extract structural fields from merged content."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""---
name: routing-skill
description: A routing skill
---
# Routing Skill

Short routing file. See references/ for details.

| Reference | Content |
|-----------|---------|
| [references/flow.md](references/flow.md) | Flow details |
""")
        refs_dir = tmp_path / "references"
        refs_dir.mkdir()
        (refs_dir / "flow.md").write_text("""## Workflow

1. Parse input from user
2. Validate the input
3. Execute the task

Phase 1: Init
Phase 2: Run

## Anti-Patterns

| 错误 | 正确 |
|------|------|
| skip validation | always validate |

## Triggers

- `run command`
- `execute task`

## Output Format

- verdict
- overall_score
- metric_results
""")

        result = parse_skill_md(str(skill_file))
        assert len(result["workflow_steps"]) >= 2
        assert len(result["anti_patterns"]) >= 1
        assert len(result["triggers"]) >= 2
        assert len(result["output_format"]) >= 2
        assert result["parse_confidence"] >= 0.6

    def test_fulsome_skill_md_not_overwritten_by_references(self, tmp_path):
        """When SKILL.md already has full sections, references should not overwrite them."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""---
name: fulsome-skill
description: A fulsome skill
---
# Fulsome Skill

## Workflow

1. Step A
2. Step B

## Anti-Patterns

- Do not skip A

## Output Format

- field_a
- field_b

## Triggers

- `trigger x`

| Reference | Content |
|-----------|---------|
| [references/extra.md](references/extra.md) | Extra details |
""")
        refs_dir = tmp_path / "references"
        refs_dir.mkdir()
        (refs_dir / "extra.md").write_text("""# Extra

## Workflow

1. Extra Step 1
2. Extra Step 2

## Anti-Patterns

- Extra anti-pattern

## Output Format

- extra_field

## Triggers

- `extra trigger`
""")

        result = parse_skill_md(str(skill_file))
        step_names = [s["name"] for s in result["workflow_steps"]]
        assert any("Step A" in n for n in step_names), "Main SKILL.md steps should be preserved"
        assert any("Step B" in n for n in step_names), "Main SKILL.md steps should be preserved"
        assert not any("Extra" in n for n in step_names), "References should not overwrite existing steps"

    def test_no_references_no_re_extraction(self, tmp_path):
        """Without references/ dir, behavior should be unchanged."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""---
name: plain-skill
description: A plain skill
---
# Plain Skill

No references directory.
""")
        result = parse_skill_md(str(skill_file))
        assert result["references"] == {}
        assert result["parse_confidence"] < 0.6
        assert "notes.txt" not in result["references"]
