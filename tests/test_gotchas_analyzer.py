"""Tests for engine/gotchas_analyzer.py — gotchas density, verification strength, and exclusion scenarios."""

from engine.gotchas_analyzer import (
    GOTCHAS_DENSITY_TARGET,
    ExclusionResult,
    analyze_exclusion_scenarios,
    analyze_gotchas_density,
    analyze_verification_strength,
)


class TestAnalyzeGotchasDensity:
    def test_empty_content(self):
        result = analyze_gotchas_density("")
        assert result.total_lines == 0
        assert result.density == 0.0
        assert not result.above_target
        assert len(result.issues) > 0

    def test_whitespace_only(self):
        result = analyze_gotchas_density("   \n\n  \n")
        assert result.total_lines == 0
        assert result.density == 0.0

    def test_generic_steps_only_no_gotchas(self):
        content = """---
name: test-skill
description: A test skill
---

# Step 1: Analyze the problem

Identify the root cause of the issue.

# Step 2: Implement the fix

Write the code to fix the bug.

# Step 3: Verify

Run tests to confirm the fix works.
"""
        result = analyze_gotchas_density(content)
        assert result.total_lines > 0
        assert result.gotcha_lines == 0
        assert result.density == 0.0
        assert not result.above_target
        assert "Gotchas density is 0%" in result.issues[0]

    def test_high_gotchas_density(self):
        content = """---
name: test-skill
description: A test skill
---

# Code Review Skill

## Anti-Patterns

- **Don't** use as any — this hides type errors.
- **Never** suppress type errors with @ts-ignore.
- **Always** use strict TypeScript mode.

## Gotchas

- Our staging environment returns 200 but the payment_events table
  is append-only — you must look for the highest version.
- The API Gateway renames @request_id to trace_id — don't trust the header name.
- Production rate limits are 100 RPM, not the 1000 RPM in docs.
"""
        result = analyze_gotchas_density(content)
        assert result.gotcha_lines > 0
        assert result.density >= GOTCHAS_DENSITY_TARGET
        assert result.above_target
        assert len(result.top_gotchas) > 0

    def test_density_below_target(self):
        content = """---
name: test
description: test
---

# Overview

This skill helps with code review.

## Steps

1. Read the diff
2. Check for errors
3. Suggest improvements

## Note

Don't forget to check edge cases.
"""
        result = analyze_gotchas_density(content)
        assert result.gotcha_lines > 0  # "Don't" is a gotcha pattern
        assert not result.above_target  # But density is low
        assert len(result.issues) > 0

    def test_frontmatter_stripped(self):
        """Frontmatter lines should not count toward gotchas density."""
        content = """---
name: very-long-name-that-should-not-count
description: this is a very long description that also should not be counted
some_other_field: more stuff that should be excluded
---

# Always use strict mode

This is a team convention for all TypeScript projects.
"""
        result = analyze_gotchas_density(content)
        # The "Always" line is a gotcha pattern
        assert result.total_lines < 6  # frontmatter excluded

    def test_known_llm_capability_excluded(self):
        """Generic 'read the file' instructions should not count as gotchas."""
        content = """# Instructions

Read the file to understand the code.
Run the test to verify the fix.
Search for related code in the codebase.
Write the implementation.

## But

Actually, in production the cache TTL is only 30s.
"""
        result = analyze_gotchas_density(content)
        # The first 4 lines are filtered as known LLM capability
        # "Actually" line should count as gotcha
        assert result.gotcha_lines >= 1

    def test_verdict_property(self):
        result = analyze_gotchas_density("")
        assert result.verdict == "FAIL"

        content = "# Always use strict mode\n\nNever suppress type errors.\n"
        result = analyze_gotchas_density("---\nname: x\n---\n" + content)
        assert result.verdict in ("PASS", "FAIL")


class TestAnalyzeVerificationStrength:
    def test_empty_content(self):
        result = analyze_verification_strength("")
        assert result.score == 0.0
        assert not result.passed
        assert len(result.issues) > 0

    def test_no_verification_patterns(self):
        content = "# Just a skill\n\nDo the thing.\n"
        result = analyze_verification_strength(content)
        assert not result.has_programmatic_assertions
        assert not result.has_state_verification
        assert not result.has_visual_verification
        assert result.score < 50.0
        assert len(result.assertion_types_found) == 0

    def test_programmatic_assertions(self):
        content = "Assert that the response status code is 200."
        result = analyze_verification_strength(content)
        assert result.has_programmatic_assertions
        assert result.score >= 50.0
        assert result.passed

    def test_state_verification(self):
        content = "Check the database has the new record."
        result = analyze_verification_strength(content)
        assert result.has_state_verification
        assert result.score >= 30.0
        assert "state_verification" in result.assertion_types_found

    def test_visual_verification(self):
        content = "Compare the screenshot against the baseline image."
        result = analyze_verification_strength(content)
        assert result.has_visual_verification
        assert "visual_verification" in result.assertion_types_found

    def test_all_verification_types(self):
        content = """
Validate the response status code is 200.
Check the file exists on disk.
Compare screenshots for visual regression.
"""
        result = analyze_verification_strength(content)
        assert result.has_programmatic_assertions
        assert result.has_state_verification
        assert result.has_visual_verification
        assert result.score == 100.0
        assert result.passed


class TestAnalyzeExclusionScenarios:
    def test_empty_string(self):
        result = analyze_exclusion_scenarios("")
        assert result.has_exclusion is False
        assert result.exclusion_count == 0
        assert result.score == 0
        assert not result.passed
        assert len(result.exclusion_phrases) == 0

    def test_no_exclusion_keywords(self):
        content = "This skill helps with code review. It gives suggestions for improvements."
        result = analyze_exclusion_scenarios(content)
        assert result.has_exclusion is False
        assert result.exclusion_count == 0
        assert result.score == 0
        assert not result.passed

    def test_single_exclusion_english(self):
        content = "Do not trigger this skill when the user is already in a debugging session."
        result = analyze_exclusion_scenarios(content)
        assert result.has_exclusion is True
        assert result.exclusion_count == 1
        assert result.score == 40
        assert not result.passed  # 40 < 50
        assert "do not trigger" in [p.lower() for p in result.exclusion_phrases]

    def test_multiple_exclusions_pass_threshold(self):
        content = """
        Do not trigger this skill for production databases.
        Never activate this when running in CI mode.
        This skill is not intended for use with legacy codebases.
        """
        result = analyze_exclusion_scenarios(content)
        assert result.has_exclusion is True
        assert result.exclusion_count >= 2
        assert result.score >= 60  # 2+ matches → 60
        assert result.passed is True  # score >= 50
        assert len(result.exclusion_phrases) >= 2

    def test_case_insensitive_matching(self):
        content = "DO NOT USE this skill for trivial changes. NEVER TRIGGER this on weekends."
        result = analyze_exclusion_scenarios(content)
        assert result.has_exclusion is True
        assert result.exclusion_count >= 2

    def test_chinese_exclusion_keywords(self):
        content = "不触发此技能当用户已经处于调试模式。排除简单场景。不适用生产环境。"
        result = analyze_exclusion_scenarios(content)
        assert result.has_exclusion is True
        assert result.exclusion_count >= 2
        assert result.score >= 60
        assert result.passed is True

    def test_should_not_be_triggered(self):
        content = "This skill should not be triggered for administrative commands."
        result = analyze_exclusion_scenarios(content)
        assert result.has_exclusion is True
        assert result.exclusion_count >= 1

    def test_excluded_from(self):
        content = "This feature is excluded from the main workflow."
        result = analyze_exclusion_scenarios(content)
        assert result.has_exclusion is True
        assert result.exclusion_count >= 1

    def test_high_count_max_score(self):
        content = """
        Do not trigger for A. Never use for B. 不触发 C.
        Not intended for D. Excluded from E. 排除 F.
        """
        result = analyze_exclusion_scenarios(content)
        assert result.has_exclusion is True
        assert result.exclusion_count >= 5
        assert result.score == 100
        assert result.passed is True
        assert len(result.exclusion_phrases) >= 5

    def test_issues_populated_when_below_threshold(self):
        content = "Do not trigger this skill for simple cases."
        result = analyze_exclusion_scenarios(content)
        # score 40 < 50, so issues should be populated
        assert len(result.issues) > 0

    def test_no_issues_when_passing(self):
        content = """
        Do not trigger for production. Never use for admin commands.
        This is not intended for beginners.
        """
        result = analyze_exclusion_scenarios(content)
        # score >= 60, so issues should be empty
        assert result.passed is True
        assert len(result.issues) == 0

    def test_dont_contraction(self):
        content = "Don't trigger this skill if the file is less than 100 lines."
        result = analyze_exclusion_scenarios(content)
        assert result.has_exclusion is True
        assert result.score == 40
        assert "don't trigger" in [p.lower() for p in result.exclusion_phrases]

    def test_not_suitable_for(self):
        content = "This skill is not suitable for projects without tests."
        result = analyze_exclusion_scenarios(content)
        assert result.has_exclusion is True
        assert result.exclusion_count >= 1

    def test_result_dataclass_fields(self):
        result = ExclusionResult()
        assert result.has_exclusion is False
        assert result.exclusion_count == 0
        assert result.exclusion_phrases == []
        assert result.score == 0.0
        assert result.issues == []
        assert result.passed is False
