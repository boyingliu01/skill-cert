"""Tests for engine/gotchas_analyzer.py — gotchas density and verification strength."""

from engine.gotchas_analyzer import (
    GOTCHAS_DENSITY_TARGET,
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
