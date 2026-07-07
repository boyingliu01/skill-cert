"""Tests for engine/maintainability.py — SKILL.md maintainability scorer."""

import subprocess
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from engine.maintainability import (
    FreshnessFinding,
    MaintainabilityResult,
    MaintainabilityScorer,
    analyze_description_quality,
    completeness_score,
    detect_catch_all_except,
    detect_deprecated_api,
    detect_freshness_patterns,
    detect_hardcoded_credentials,
    detect_shadowed_builtins,
    detect_stale_todo,
    freshness_score,
    readability_score,
    score_skill_md,
)

# ─── Fixtures ───────────────────────────────────────────────────────────────

GOOD_SKILL = """\
---
name: test-skill
description: >
  A well-structured skill for testing purposes with proper documentation
  and complete workflow descriptions.
triggers:
  - "run test skill"
  - "execute skill test"
---

# Test Skill

A comprehensive skill demonstrating best practices.

## Scope

### What This Skill Does

Handles automated testing workflows with proper error handling.

### What This Skill Does NOT

- Does not replace integration tests
- Does not run production deployments

## Workflow

1. Parse the input configuration
2. Validate all required fields
3. Execute the primary action
4. Return structured results

## Anti-Patterns

| Anti-Pattern | Correct Approach |
|-------------|-----------------|
| Skipping validation | Always validate before executing |
| Ignoring errors | Catch and handle all exceptions |

## Triggers

- "run test skill"
- "execute skill test"

## Examples

- Input: `{"action": "test"}`
- Output: `{"status": "ok"}`
"""

BAD_SKILL = (
    "---\n"
    "  bad yaml [\n"
    "---\n"
    "\n"
    "This really long line goes on and on without any breaks because the author clearly didn't understand markdown conventions at all and wrote the entire paragraph as a single run-on sentence that nobody could possibly read comfortably on any screen!!!\n"
    "\n"
    "Some random content with outdated references to Claude 2 and GPT-3.5-turbo and Python 3.6 which are long past their prime. Uses anthropic-sdk v0.3.0 and openai-python v0.28.0. Version: 0.1.0-beta.\n"
    "\n"
    "More random stuff. TODO: add actual structure. FIXME: rewrite entirely. No real content whatsoever in this document that was clearly written without any thought or effort put into it at all.\n"
)

MINIMAL_SKILL = """\
---
name: minimal
description: A minimal skill file
---

# Minimal

Basic content.
"""

EMPTY_SKILL = ""

MALFORMED_YAML_SKILL = """\
---
name: malformed
  bad indent: [
  - missing bracket
---

# Malformed

Some content.
"""

DEEP_NESTING_SKILL = """\
---
name: deep-nesting
description: Skill with excessive section nesting
---

# Deep Nesting

## Section

### Subsection

#### Deep

##### Too Deep

###### Way Too Deep

####### Unacceptable

###### Also Too Deep

## Another Section

### Another Sub

#### Another Deep

##### Another Too Deep

Some content that is fine but the nesting is terrible throughout this file and everywhere we look.
"""

LONG_LINES_SKILL = (
    "---\n"
    "name: long-lines\n"
    "description: This is an intentionally verbose description that serves no real purpose other than to make lines longer than should be acceptable in any documentation\n"
    "---\n"
    "\n"
    "# Long Lines\n"
    "\n"
    "This is an extremely long line of text that far exceeds any reasonable line length limit and makes the document very difficult to read on standard screens because it forces horizontal scrolling which is a terrible user experience that nobody should ever tolerate in any professional context whatsoever.\n"
    "\n"
    "Another paragraph with excessive length that no reasonable person would accept as good documentation practice in any professional software engineering environment anywhere at all really.\n"
    "\n"
    "More text that is deliberately written to ensure every single line surpasses one hundred characters in length because this is a test case designed to validate that the scoring system properly penalizes documents with overly long lines throughout the entire file.\n"
    "\n"
    "The final line of this section is also intentionally elongated to maintain consistency with the previous lines and ensure that the overall average line length metric exceeds the threshold that has been set as acceptable by the maintainability scoring system.\n"
)

DEEP_NESTING_SKILL = (
    "---\n"
    "name: deep-nesting\n"
    "description: Skill with excessive section nesting\n"
    "---\n"
    "\n"
    "## Level1\n"
    "\n"
    "### Level2\n"
    "\n"
    "#### Level3\n"
    "\n"
    "##### Level4\n"
    "\n"
    "###### Level5a\n"
    "\n"
    "###### Level5b\n"
    "\n"
    "###### Level5c\n"
    "\n"
    "###### Level5d\n"
    "\n"
    "Some content here that is completely irrelevant to the overall structure of this document which has way too many nested sections.\n"
)

TODO_LADEN_SKILL = """\
---
name: todo-skill
description: Skill full of TODOs
triggers:
  - "run todo skill"
---

# Todo Skill

## Workflow

1. Parse the TODO items from config
2. Execute pending actions
3. Skip unfinished steps — FIXME: need to handle errors
4. Output results — TODO: add logging

## Anti-Patterns

| Anti-Pattern | Correct Approach |
|-------------|-----------------|
| Leaving TODOs in production | Remove before committing |

## Notes

- TODO: refactor this section
- FIXME: error handling missing
- TODO: add tests
- TBD: decide on output format
"""

OUTDATED_SKILL = """\
---
name: outdated-skill
description: Skill with outdated references
triggers:
  - "run outdated skill"
---

# Outdated Skill

## Workflow

1. Install dependencies (requires Python 3.6+)
2. Configure the skill
3. Run with v1.0.0

## Configuration

Uses Claude 3 Opus and GPT-3.5-turbo models.
Version: 0.1.0-beta

## Dependencies

- anthropic-sdk v0.3.0
- openai-python v0.28.0
"""

FRESH_SKILL = """\
---
name: fresh-skill
description: Skill with current references
triggers:
  - "run fresh skill"
---

# Fresh Skill

Version: 2.0.0

## Workflow

1. Install latest dependencies
2. Configure the skill
3. Run with current versions

## Dependencies

- anthropic>=0.30.0
- openai>=1.50.0
- Python 3.11+
"""

MISSING_SECTIONS_SKILL = """\
---
name: incomplete
---

# Incomplete Skill

Just some text here.
"""


# ─── Test: readability_score ───────────────────────────────────────────────


class TestReadabilityScore:
    def test_good_readability(self):
        result = readability_score(GOOD_SKILL)
        assert result["avg_line_length"] < 100
        assert result["max_depth"] <= 3
        assert result["todo_count"] == 0
        assert result["score"] > 0.7

    def test_bad_readability_long_lines(self):
        result = readability_score(LONG_LINES_SKILL)
        assert result["avg_line_length"] >= 100
        assert result["length_score"] < 0.75

    def test_bad_readability_deep_nesting(self):
        result = readability_score(DEEP_NESTING_SKILL)
        assert result["max_depth"] > 3
        assert result["score"] < 0.7

    def test_todos_lower_readability(self):
        result = readability_score(TODO_LADEN_SKILL)
        assert result["todo_count"] >= 3
        assert result["score"] < 0.9

    def test_empty_file_readability(self):
        result = readability_score(EMPTY_SKILL)
        assert result["avg_line_length"] == 0
        assert result["max_depth"] == 0
        assert result["score"] == 1.0

    def test_no_todos_in_good_skill(self):
        result = readability_score(GOOD_SKILL)
        assert result["todo_count"] == 0


# ─── Test: readability_score refactoring characterization ─────────────────


class TestReadabilityRefactoring:
    """Characterization tests to ensure readability_score refactoring preserves exact behavior."""

    def test_length_score_formula(self):
        """length_score = max(0.0, 1.0 - max(0, avg-100)/100)"""
        # Content with all lines >100 chars → avg > 100 → score < 1.0
        long_lines = "\n".join(["x" * 150, "y" * 150, "z" * 150])
        result = readability_score(long_lines)
        assert result["avg_line_length"] == 150
        assert result["length_score"] == 0.5  # max(0, 1-(150-100)/100) = 0.5

        # Content with avg_line_length=200 → score=0.0
        very_long = "\n".join(["x" * 200, "y" * 200])
        result = readability_score(very_long)
        assert result["avg_line_length"] == 200
        assert result["length_score"] == 0.0

    def test_depth_score_formula(self):
        """depth_score = 1.0 if max_depth<=3 else max(0.0, 1.0-(max_depth-3)*0.5)"""
        r = readability_score("##### H5")
        assert r["max_depth"] == 4
        assert r["depth_score"] == 0.5

        r = readability_score("###### H6")
        assert r["max_depth"] == 5
        assert r["depth_score"] == 0.0

    def test_todo_score_formula(self):
        """todo_score = max(0.0, 1.0 - todo_count*0.15)"""
        content = "# Test\nTODO: one\nFIXME: two\nHACK: three\nXXX: four\nTBD: five"
        result = readability_score(content)
        assert result["todo_count"] == 5
        assert result["todo_score"] == 0.25

        # 7 TODOs → score capped at 0.0
        lots_of_todos = "# Test\n" + "\n".join(f"TODO: {i}" for i in range(7))
        result = readability_score(lots_of_todos)
        assert result["todo_count"] == 7
        assert result["todo_score"] == 0.0

    def test_combined_score_is_average(self):
        """combined = (length_score + depth_score + todo_score) / 3.0"""
        content = "# Test\nTODO: one"
        result = readability_score(content)
        expected = round(
            (result["length_score"] + result["depth_score"] + result["todo_score"]) / 3.0, 3
        )
        assert result["score"] == expected

    def test_depth_penalty_threshold(self):
        """max_depth<=3 gets depth_score=1.0, >3 gets penalized."""
        r = readability_score("#### H4")
        assert r["max_depth"] == 3
        assert r["depth_score"] == 1.0

    def test_mixed_scores(self):
        """Integration: verify all sub-scores computed and averaged."""
        content = "## H2\n### H3\n#### H4\n##### H5\n\nTODO: fix this\n" + "x" * 150
        result = readability_score(content)
        assert result["max_depth"] == 4
        assert result["depth_score"] == 0.5
        assert result["todo_score"] == 0.85
        expected = round(
            (result["length_score"] + result["depth_score"] + result["todo_score"]) / 3.0, 3
        )
        assert result["score"] == expected


# ─── Test: completeness_score ─────────────────────────────────────────────


class TestCompletenessScore:
    def test_good_completeness(self):
        result = completeness_score(GOOD_SKILL)
        assert result["has_name"] is True
        assert result["has_triggers"] is True
        assert result["has_workflow"] is True
        assert result["has_anti_patterns"] is True
        assert result["score"] >= 1.0

    def test_minimal_incomplete(self):
        result = completeness_score(MINIMAL_SKILL)
        assert result["has_name"] is True
        assert result["has_triggers"] is False
        assert result["has_workflow"] is False
        assert result["score"] < 1.0

    def test_missing_all_sections(self):
        result = completeness_score(MISSING_SECTIONS_SKILL)
        assert result["has_triggers"] is False
        assert result["has_workflow"] is False
        assert result["has_anti_patterns"] is False
        assert result["score"] <= 0.25

    def test_empty_file_completeness(self):
        result = completeness_score(EMPTY_SKILL)
        assert result["has_name"] is False
        assert result["has_triggers"] is False
        assert result["score"] == 0.0


# ─── Test: freshness_score ────────────────────────────────────────────────


class TestFreshnessScore:
    def test_fresh_references(self):
        result = freshness_score(FRESH_SKILL)
        assert result["outdated_refs"] == 0
        assert result["has_version"] is True
        assert result["score"] > 0.7

    def test_outdated_references(self):
        result = freshness_score(OUTDATED_SKILL)
        assert result["outdated_refs"] >= 2
        assert result["score"] < 0.5

    def test_no_freshness_issues_good_skill(self):
        result = freshness_score(GOOD_SKILL)
        assert result["score"] >= 1.0

    def test_empty_file_freshness(self):
        result = freshness_score(EMPTY_SKILL)
        assert result["score"] == 1.0


# ─── Test: score_skill_md (composite) ─────────────────────────────────────


class TestCompositeScore:
    def test_good_skill_scores_high(self):
        result = score_skill_md(GOOD_SKILL)
        assert isinstance(result, MaintainabilityResult)
        assert result.total_score > 80
        assert result.readability_score > 70
        assert result.completeness_score >= 100
        assert result.freshness_score > 70

    def test_bad_skill_scores_low(self):
        result = score_skill_md(BAD_SKILL)
        assert isinstance(result, MaintainabilityResult)
        assert result.total_score < 30

    def test_empty_file_score(self):
        result = score_skill_md(EMPTY_SKILL)
        assert isinstance(result, MaintainabilityResult)

    def test_malformed_yaml_score(self):
        result = score_skill_md(MALFORMED_YAML_SKILL)
        assert isinstance(result, MaintainabilityResult)

    def test_result_has_grade(self):
        result = score_skill_md(GOOD_SKILL)
        assert result.grade in ("A", "B", "C", "D", "F")

    def test_result_has_sub_scores(self):
        result = score_skill_md(GOOD_SKILL)
        assert hasattr(result, "readability_details")
        assert hasattr(result, "completeness_details")
        assert hasattr(result, "freshness_details")


# ─── Test: from-file scoring ─────────────────────────────────────────────


class TestFromFile:
    def test_score_from_file(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write(GOOD_SKILL)
            f.flush()
            result = MaintainabilityScorer().score_file(f.name)
            assert isinstance(result, MaintainabilityResult)
            assert result.total_score > 80

    def test_nonexistent_file_raises(self):
        scorer = MaintainabilityScorer()
        with pytest.raises(FileNotFoundError):
            scorer.score_file("/nonexistent/path/SKILL.md")


# ─── Test: MaintainabilityScorer class ────────────────────────────────────


class TestMaintainabilityScorer:
    def test_default_weights(self):
        scorer = MaintainabilityScorer()
        assert scorer.weights["readability"] == 30
        assert scorer.weights["completeness"] == 50
        assert scorer.weights["freshness"] == 20

    def test_custom_weights(self):
        scorer = MaintainabilityScorer(
            weights={"readability": 40, "completeness": 40, "freshness": 20}
        )
        assert scorer.weights["readability"] == 40

    def test_grade_calculation(self):
        result = score_skill_md(GOOD_SKILL)
        if result.total_score >= 90:
            assert result.grade == "A"
        elif result.total_score >= 80:
            assert result.grade in ("A", "B")

    def test_failing_grade(self):
        result = score_skill_md(BAD_SKILL)
        assert result.grade == "F"


# ─── Test: FreshnessFinding dataclass ─────────────────────────────────────


class TestFreshnessFinding:
    def test_finding_fields(self):
        f = FreshnessFinding(
            line_number=5, pattern_type="deprecated_api", severity="medium", description="test"
        )
        assert f.line_number == 5
        assert f.pattern_type == "deprecated_api"
        assert f.severity == "medium"
        assert f.description == "test"

    def test_finding_frozen(self):
        f = FreshnessFinding(line_number=1, pattern_type="test", severity="low", description="d")
        with pytest.raises(AttributeError):
            f.line_number = 2


# ─── Test: detect_deprecated_api ──────────────────────────────────────────


class TestDetectDeprecatedApi:
    def test_deprecated_decorator(self):
        content = "line1\n@deprecated\ndef old_func():\n    pass"
        findings = detect_deprecated_api(content)
        assert len(findings) == 1
        assert findings[0].line_number == 2
        assert findings[0].pattern_type == "deprecated_api"
        assert findings[0].severity == "high"

    def test_deprecated_with_reason(self):
        content = '@deprecated("use new_func instead")\ndef old_func():\n    pass'
        findings = detect_deprecated_api(content)
        assert len(findings) == 1
        assert findings[0].line_number == 1

    def test_no_deprecated(self):
        content = 'def new_func():\n    """This is current."""\n    pass'
        findings = detect_deprecated_api(content)
        assert findings == []

    def test_empty_content(self):
        assert detect_deprecated_api("") == []

    def test_multiple_deprecated(self):
        content = '@deprecated\ndef a():\n    pass\n\n@deprecated("old")\ndef b():\n    pass'
        findings = detect_deprecated_api(content)
        assert len(findings) == 2
        assert findings[0].line_number == 1
        assert findings[1].line_number == 5

    def test_deprecated_in_comment_not_detected(self):
        """The word 'deprecated' in a regular comment shouldn't trigger the decorator pattern."""
        content = "# This old deprecated function\nfunc():\n    pass"
        findings = detect_deprecated_api(content)
        assert findings == []


# ─── Test: detect_stale_todo ──────────────────────────────────────────────


class TestDetectStaleTodo:
    def test_no_git_marks_all_stale(self):
        content = "# Test\nTODO: fix this\nSome content\nFIXME: broken"
        findings = detect_stale_todo(content)
        assert len(findings) == 2
        assert findings[0].line_number == 2
        assert findings[0].pattern_type == "stale_todo"
        assert findings[1].line_number == 4

    def test_no_todos(self):
        content = "# Clean\nNo todos here.\nJust content."
        findings = detect_stale_todo(content)
        assert findings == []

    def test_empty_content(self):
        assert detect_stale_todo("") == []

    def test_hack_detected(self):
        content = "# Test\nHACK: temporary workaround"
        findings = detect_stale_todo(content)
        assert len(findings) == 1
        assert findings[0].line_number == 2

    @patch("engine.maintainability.time.time", return_value=1700000000)
    @patch("engine.maintainability.subprocess.run")
    def test_with_git_blame_stale(self, mock_run, mock_time):
        now = 1700000000
        old_time = now - 200 * 86400  # 200 days ago

        blame_output = (
            "a" * 40 + " 1 1 1\n"
            "author John\n"
            f"author-time {old_time}\n"
            "author-tz +0000\n"
            "\tTODO: fix this old thing\n"
        )
        mock_run.return_value = MagicMock(stdout=blame_output, returncode=0)

        content = "TODO: fix this old thing"
        findings = detect_stale_todo(content, file_path="/tmp/test.py")
        assert len(findings) == 1
        assert "200 days" in findings[0].description

    @patch("engine.maintainability.time.time", return_value=1700000000)
    @patch("engine.maintainability.subprocess.run")
    def test_with_git_blame_recent(self, mock_run, mock_time):
        now = 1700000000
        recent_time = now - 30 * 86400  # 30 days ago

        blame_output = (
            "b" * 40 + " 1 1 1\n"
            "author John\n"
            f"author-time {recent_time}\n"
            "author-tz +0000\n"
            "\tTODO: recently added\n"
        )
        mock_run.return_value = MagicMock(stdout=blame_output, returncode=0)

        content = "TODO: recently added"
        findings = detect_stale_todo(content, file_path="/tmp/test.py")
        assert findings == []

    @patch("engine.maintainability.subprocess.run", side_effect=subprocess.SubprocessError)
    def test_git_failure_fallback(self, mock_run):
        content = "# Test\nTODO: fix this"
        findings = detect_stale_todo(content, file_path="/tmp/test.py")
        assert len(findings) == 1


# ─── Test: detect_shadowed_builtins ───────────────────────────────────────


class TestDetectShadowedBuiltins:
    def test_import_shadow(self):
        content = "import os\nfrom mymodule import list\nx = 5"
        findings = detect_shadowed_builtins(content)
        assert len(findings) == 1
        assert findings[0].line_number == 2
        assert findings[0].pattern_type == "shadowed_builtin"
        assert findings[0].severity == "high"
        assert "list" in findings[0].description

    def test_assignment_shadow(self):
        content = 'list = [1, 2, 3]\nstr = "hello"'
        findings = detect_shadowed_builtins(content)
        assert len(findings) == 2
        assert findings[0].line_number == 1
        assert findings[1].line_number == 2

    def test_no_shadow(self):
        content = "my_list = [1, 2, 3]\nname = 'test'"
        findings = detect_shadowed_builtins(content)
        assert findings == []

    def test_empty_content(self):
        assert detect_shadowed_builtins("") == []

    def test_alias_shadow(self):
        content = "from module import foo as dict"
        findings = detect_shadowed_builtins(content)
        assert len(findings) == 1
        assert findings[0].line_number == 1
        assert "dict" in findings[0].description

    def test_non_builtin_import_no_shadow(self):
        content = "from module import foo, bar\nimport os"
        findings = detect_shadowed_builtins(content)
        assert findings == []

    def test_indented_assignment(self):
        content = "    list = [1, 2, 3]"
        findings = detect_shadowed_builtins(content)
        assert len(findings) == 1

    def test_double_equals_not_matched(self):
        content = "x == list"
        findings = detect_shadowed_builtins(content)
        assert findings == []

    def test_multiple_imports_one_shadow(self):
        content = "from module import foo, list, bar"
        findings = detect_shadowed_builtins(content)
        assert len(findings) == 1
        assert "list" in findings[0].description


# ─── Test: detect_catch_all_except ────────────────────────────────────────


class TestDetectCatchAllExcept:
    def test_bare_except(self):
        content = "try:\n    foo()\nexcept:\n    pass"
        findings = detect_catch_all_except(content)
        assert len(findings) == 1
        assert findings[0].line_number == 3
        assert findings[0].pattern_type == "catch_all_except"
        assert findings[0].severity == "high"

    def test_except_exception_without_handling(self):
        content = "try:\n    foo()\nexcept Exception:\n    x = 1"
        findings = detect_catch_all_except(content)
        assert len(findings) == 1
        assert findings[0].severity == "medium"

    def test_except_with_reraise_not_flagged(self):
        content = "try:\n    foo()\nexcept Exception:\n    raise"
        findings = detect_catch_all_except(content)
        assert findings == []

    def test_except_with_logging_not_flagged(self):
        content = "try:\n    foo()\nexcept Exception:\n    logger.error('oops')"
        findings = detect_catch_all_except(content)
        assert findings == []

    def test_specific_except_not_flagged(self):
        content = "try:\n    foo()\nexcept ValueError:\n    pass"
        findings = detect_catch_all_except(content)
        assert findings == []

    def test_empty_content(self):
        assert detect_catch_all_except("") == []

    def test_except_exception_with_raise_not_flagged(self):
        content = "try:\n    foo()\nexcept Exception:\n    raise ValueError('x')"
        findings = detect_catch_all_except(content)
        assert findings == []

    def test_bare_except_with_raise_not_flagged(self):
        content = "try:\n    foo()\nexcept:\n    raise"
        findings = detect_catch_all_except(content)
        assert findings == []

    def test_except_with_logging_call_not_flagged(self):
        content = "try:\n    foo()\nexcept Exception:\n    logging.warning('x')"
        findings = detect_catch_all_except(content)
        assert findings == []

    def test_multiple_except_blocks(self):
        content = (
            "try:\n    foo()\nexcept:\n    pass\n\ntry:\n    bar()\nexcept Exception:\n    x = 1"
        )
        findings = detect_catch_all_except(content)
        assert len(findings) == 2


# ─── Test: detect_hardcoded_credentials ───────────────────────────────────


class TestDetectHardcodedCredentials:
    def test_sk_prefix(self):
        content = 'key = "sk-abc123def456"'
        findings = detect_hardcoded_credentials(content)
        assert len(findings) == 1
        assert findings[0].line_number == 1
        assert findings[0].pattern_type == "hardcoded_credential"
        assert findings[0].severity == "critical"

    def test_api_key_assignment(self):
        content = "api_key = 'my-secret-key-123'"
        findings = detect_hardcoded_credentials(content)
        assert len(findings) == 1

    def test_secret_assignment(self):
        content = 'secret = "my_value"'
        findings = detect_hardcoded_credentials(content)
        assert len(findings) == 1

    def test_no_credentials(self):
        content = 'name = "test"\nvalue = 42'
        findings = detect_hardcoded_credentials(content)
        assert findings == []

    def test_empty_content(self):
        assert detect_hardcoded_credentials("") == []

    def test_test_file_skipped(self):
        content = 'key = "sk-abc123def456"'
        findings = detect_hardcoded_credentials(content, is_test_file=True)
        assert findings == []

    def test_sk_underscore_prefix(self):
        content = 'token = "sk_abc123"'
        findings = detect_hardcoded_credentials(content)
        assert len(findings) == 1

    def test_no_false_positive_without_quotes(self):
        content = "key = sk_abc123"
        findings = detect_hardcoded_credentials(content)
        assert findings == []

    def test_multiple_credentials(self):
        content = 'api_key = "sk-abc"\nsecret = "xyz"'
        findings = detect_hardcoded_credentials(content)
        assert len(findings) == 2


# ─── Test: detect_freshness_patterns (integration) ────────────────────────


class TestDetectFreshnessPatterns:
    def test_returns_all_findings(self):
        content = (
            "@deprecated\ndef old():\n    pass\n"
            "list = [1, 2, 3]\n"
            "try:\n    pass\nexcept:\n    pass\n"
            'key = "sk-abc123"'
        )
        findings = detect_freshness_patterns(content)
        types = {f.pattern_type for f in findings}
        assert "deprecated_api" in types
        assert "shadowed_builtin" in types
        assert "catch_all_except" in types
        assert "hardcoded_credential" in types

    def test_clean_content_no_findings(self):
        content = "def clean_function():\n    x = 42\n    return x"
        findings = detect_freshness_patterns(content)
        assert findings == []

    def test_empty_content(self):
        findings = detect_freshness_patterns("")
        assert findings == []

    def test_freshness_score_includes_patterns(self):
        content = '---\nname: test\n---\nkey = "sk-abc123"'
        result = freshness_score(content)
        assert "patterns" in result
        assert len(result["patterns"]) > 0
        assert result["patterns"][0]["pattern_type"] == "hardcoded_credential"

    def test_freshness_score_clean_no_patterns(self):
        result = freshness_score(GOOD_SKILL)
        assert "patterns" in result
        assert result["patterns"] == []

    def test_freshness_score_existing_outdated_refs_unchanged(self):
        """Ensure existing outdated_refs calculation is not affected by new detectors."""
        result = freshness_score(OUTDATED_SKILL)
        assert result["outdated_refs"] >= 2

    def test_freshness_score_existing_fields_unchanged(self):
        """Ensure existing return fields remain unchanged for backward compat."""
        result = freshness_score(FRESH_SKILL)
        assert "outdated_refs" in result
        assert "has_version" in result
        assert "score" in result


# ─── Test: Existing fixtures not affected by new detectors ────────────────


# ─── Test: analyze_description_quality ──────────────────────────────────────


class TestAnalyzeDescriptionQuality:
    """Test analyze_description_quality() — description quality scoring."""

    def test_good_description_full_score(self):
        """Full description with all quality signals scores high."""
        desc = (
            "Use this skill to evaluate AI skill definitions. "
            "Use when you need to check if a skill works correctly. "
            "Trigger on 'skill-cert', '/skill-cert', 'evaluate skill'. "
            "Not for general code review tasks. "
            "A dedicated tool for automated evaluation."
        )
        result = analyze_description_quality(desc)
        assert result.score >= 80.0
        assert result.has_what is True
        assert result.has_when is True
        assert result.has_trigger_words is True
        assert result.has_exclusion is True

    def test_empty_description_zero_score(self):
        """Empty description scores 0 and reports issue."""
        result = analyze_description_quality("")
        assert result.score == 0.0
        assert "Description is empty" in result.issues

    def test_minimal_description_partial_score(self):
        """Bare description with only 'what' gets partial score."""
        desc = "Run evaluation on SKILL.md files."
        result = analyze_description_quality(desc)
        assert result.score == 45.0  # has_what(25) + uses_third_person(20)
        assert result.has_what is True
        assert result.has_when is False
        assert result.has_exclusion is False

    def test_description_missing_when_reports_issue(self):
        """Description lacking 'when' adds appropriate issue."""
        desc = "Evaluate AI skills. Trigger on 'skill-cert'."
        result = analyze_description_quality(desc)
        issues_text = " ".join(result.issues)
        assert "WHEN" in issues_text or "when" in issues_text

    def test_first_person_lowers_score(self):
        """First-person description loses third-person points."""
        desc = "I will help you evaluate skills when you need testing."
        result = analyze_description_quality(desc)
        assert result.uses_third_person is False
        assert result.score < 100.0

    def test_trigger_word_count_tracked(self):
        """Description with multiple trigger indicators counts them."""
        desc = "Trigger on 'run'. This skill activates when invoked."
        result = analyze_description_quality(desc)
        assert result.trigger_word_count >= 2

    def test_description_none_trivially_empty(self):
        """None/empty descriptions should not crash."""
        result = analyze_description_quality("")
        assert result.score == 0.0


class TestNewDetectorsNoRegression:
    """Ensure existing test fixtures don't trigger false positives from new detectors."""

    def test_good_skill_no_new_patterns(self):
        findings = detect_freshness_patterns(GOOD_SKILL)
        pattern_types = {f.pattern_type for f in findings}
        assert "deprecated_api" not in pattern_types
        assert "shadowed_builtin" not in pattern_types
        assert "catch_all_except" not in pattern_types
        assert "hardcoded_credential" not in pattern_types

    def test_fresh_skill_no_new_patterns(self):
        findings = detect_freshness_patterns(FRESH_SKILL)
        assert findings == []

    def test_bad_skill_no_shadowed_builtins(self):
        findings = detect_shadowed_builtins(BAD_SKILL)
        assert findings == []

    def test_bad_skill_no_hardcoded_credentials(self):
        findings = detect_hardcoded_credentials(BAD_SKILL)
        assert findings == []

    def test_bad_skill_no_catch_all_except(self):
        findings = detect_catch_all_except(BAD_SKILL)
        assert findings == []

    def test_outdated_skill_no_new_code_patterns(self):
        findings = detect_deprecated_api(OUTDATED_SKILL)
        assert findings == []
        findings = detect_shadowed_builtins(OUTDATED_SKILL)
        assert findings == []
        findings = detect_catch_all_except(OUTDATED_SKILL)
        assert findings == []
        findings = detect_hardcoded_credentials(OUTDATED_SKILL)
        assert findings == []
