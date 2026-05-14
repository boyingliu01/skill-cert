"""Tests for engine/maintainability.py — SKILL.md maintainability scorer."""

import pytest
import tempfile

from engine.maintainability import (
    MaintainabilityScorer,
    MaintainabilityResult,
    readability_score,
    completeness_score,
    freshness_score,
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

BAD_SKILL = """\
---
  bad yaml [
---

This really long line goes on and on without any breaks because the author clearly didn't understand markdown conventions at all and wrote the entire paragraph as a single run-on sentence that nobody could possibly read comfortably on any screen!!!

Some random content with outdated references to Claude 2 and GPT-3.5-turbo and Python 3.6 which are long past their prime. Uses anthropic-sdk v0.3.0 and openai-python v0.28.0. Version: 0.1.0-beta.

More random stuff. TODO: add actual structure. FIXME: rewrite entirely. No real content whatsoever in this document that was clearly written without any thought or effort put into it at all.
"""

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

LONG_LINES_SKILL = """\
---
name: long-lines
description: This is an intentionally verbose description that serves no real purpose other than to make lines longer than should be acceptable in any documentation
---

# Long Lines

This is an extremely long line of text that far exceeds any reasonable line length limit and makes the document very difficult to read on standard screens because it forces horizontal scrolling which is a terrible user experience that nobody should ever tolerate in any professional context whatsoever.

Another paragraph with excessive length that no reasonable person would accept as good documentation practice in any professional software engineering environment anywhere at all really.

More text that is deliberately written to ensure every single line surpasses one hundred characters in length because this is a test case designed to validate that the scoring system properly penalizes documents with overly long lines throughout the entire file.

The final line of this section is also intentionally elongated to maintain consistency with the previous lines and ensure that the overall average line length metric exceeds the threshold that has been set as acceptable by the maintainability scoring system.
"""

DEEP_NESTING_SKILL = """\
---
name: deep-nesting
description: Skill with excessive section nesting
---

## Level1

### Level2

#### Level3

##### Level4

###### Level5

###### Level5a

###### Level5b

###### Level5c

###### Level5d

Some content here that is completely irrelevant to the overall structure of this document which has way too many nested sections.
"""

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
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md",
                                          delete=False, encoding="utf-8") as f:
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
