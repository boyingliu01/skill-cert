"""Tests for engine/structure_quality.py — tool permission and script usage."""

from engine.structure_quality import (
    check_script_usage,
    check_tool_permission,
)


class TestCheckToolPermission:
    def test_empty_content(self):
        result = check_tool_permission("")
        assert result.score == 0.0

    def test_no_tools_md_no_dangerous(self):
        result = check_tool_permission("# Skill description\n\nJust a test.")
        assert not result.has_tools_md
        assert not result.dangerous_tools_allowed
        assert result.score == 70.0  # 100 - 30 for no tools.md

    def test_has_tools_md(self):
        content = "# Skill\n\nSee tools.md for allowed permissions.\n"
        result = check_tool_permission(content)
        assert result.has_tools_md

    def test_dangerous_tools_detected(self):
        content = "# Skill\n\nRun the shell command.\n"
        result = check_tool_permission(content)
        assert len(result.dangerous_tools_allowed) >= 1
        assert result.score < 100.0

    def test_clean_with_tools_md(self):
        content = """# Skill
## Tools
- Allowed: read, write
- See tools.md for details.
"""
        result = check_tool_permission(content)
        assert result.has_tools_md
        assert result.score >= 85.0


class TestCheckScriptUsage:
    def test_nonexistent_dir(self):
        result = check_script_usage("/nonexistent/path")
        assert not result.has_scripts
        assert result.script_count == 0

    def test_no_scripts(self, tmp_path):
        (tmp_path / "SKILL.md").write_text("name: test\ndescription: test\n---\n")
        result = check_script_usage(str(tmp_path))
        assert not result.has_scripts

    def test_with_script_dir(self, tmp_path):
        (tmp_path / "SKILL.md").write_text("name: test\ndescription: test\n---\n")
        script_dir = tmp_path / "scripts"
        script_dir.mkdir()
        (script_dir / "deploy.sh").write_text("#!/bin/bash\necho hello")
        result = check_script_usage(str(tmp_path))
        assert result.has_scripts
        assert result.script_count >= 1
