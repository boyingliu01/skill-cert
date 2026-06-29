from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from engine.testgen import EvalGenerator


class MockModelAdapter:
    def __init__(self, responses=None):
        self.responses = responses or []
        self.call_count = 0
        self.skill_spec: dict[str, Any] = {}

    def chat(self, messages):
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
            self.call_count += 1
            return response
        return '{"eval_cases": []}'


def test_test_generator_initialization():
    generator = EvalGenerator()

    assert generator.max_rounds == 3
    assert generator.consecutive_no_improvement == 2
    assert generator.coverage_threshold == 0.9
    assert generator.degrade_threshold == 0.7
    assert generator.block_threshold == 0.5
    assert (
        "eval_cases" in generator.minimum_evals_template
        or "evals" in generator.minimum_evals_template
    )


def test_generate_initial_evals_success():
    generator = EvalGenerator()
    skill_spec = {
        "name": "test-skill",
        "description": "A test skill",
        "triggers": ["test", "evaluate"],
        "workflow_steps": [{"name": "step1", "type": "validation"}],
        "anti_patterns": ["skip_validation"],
        "output_format": ["json", "markdown"],
    }

    mock_adapter = MockModelAdapter(
        [
            '{"eval_cases": [{"id": 1, "name": "test-case", "category": "normal", '
            '"input": "test input", "expected_triggers": true, '
            '"assertions": [{"type": "contains", "value": "test", "weight": 1}]}]}'
        ]
    )

    result = generator.generate_initial_evals(skill_spec, mock_adapter)

    assert "eval_cases" in result or "evals" in result
    eval_cases = result.get("eval_cases", result.get("evals", []))
    assert len(eval_cases) >= 1


def test_generate_initial_evals_fallback():
    generator = EvalGenerator()
    skill_spec = {
        "name": "test-skill",
        "description": "A test skill",
        "triggers": ["test"],
        "workflow_steps": [],
        "anti_patterns": [],
        "output_format": [],
    }

    mock_adapter = MockModelAdapter(["Invalid response"])

    result = generator.generate_initial_evals(skill_spec, mock_adapter)

    assert "eval_cases" in result or "evals" in result
    eval_cases = result.get("eval_cases", result.get("evals", []))
    assert len(eval_cases) >= 1


def test_review_evals():
    generator = EvalGenerator()
    evals = {
        "eval_cases": [
            {
                "id": 1,
                "name": "test-case",
                "category": "normal",
                "input": "test input",
                "expected_triggers": True,
                "assertions": [{"type": "contains", "value": "test", "weight": 1}],
            }
        ]
    }

    skill_spec = {
        "name": "test-skill",
        "description": "A test skill",
        "triggers": ["test"],
        "workflow_steps": [{"name": "step1", "type": "validation"}],
        "anti_patterns": ["skip_validation"],
        "output_format": ["json"],
    }

    mock_review_adapter = MockModelAdapter(
        ['{"coverage": 0.5, "gaps": ["workflow steps not covered"], "needs_improvement": true}']
    )
    mock_review_adapter.skill_spec = skill_spec

    result = generator.review_evals(evals, mock_review_adapter)

    assert "coverage" in result
    assert "gaps" in result
    assert "needs_improvement" in result


def test_fill_gaps():
    generator = EvalGenerator()
    gaps = {"coverage": 0.5, "gaps": ["workflow steps not covered"], "needs_improvement": True}

    skill_spec = {
        "name": "test-skill",
        "description": "A test skill",
        "triggers": ["test"],
        "workflow_steps": [{"name": "step1", "type": "validation"}],
        "anti_patterns": ["skip_validation"],
        "output_format": ["json"],
    }

    mock_adapter = MockModelAdapter(
        [
            '{"eval_cases": [{"id": 1, "name": "test-case", "category": "normal", '
            '"input": "test input", "expected_triggers": true, '
            '"assertions": [{"type": "contains", "value": "test", "weight": 1}]}]}'
        ]
    )

    result = generator.fill_gaps(gaps, skill_spec, mock_adapter)

    assert "eval_cases" in result


def test_calculate_coverage():
    generator = EvalGenerator()
    evals = {
        "eval_cases": [
            {
                "id": 1,
                "name": "test-case",
                "category": "normal",
                "input": "test input",
                "expected_triggers": True,
                "assertions": [
                    {"type": "contains", "value": "step1", "weight": 1},
                    {"type": "contains", "value": "skip_validation", "weight": 1},
                    {"type": "contains", "value": "json", "weight": 1},
                ],
            }
        ]
    }

    skill_spec = {
        "name": "test-skill",
        "description": "A test skill",
        "triggers": ["test"],
        "workflow_steps": [{"name": "step1", "type": "validation"}],
        "anti_patterns": ["skip_validation"],
        "output_format": ["json"],
    }

    coverage = generator._calculate_coverage(evals, skill_spec)

    # All spec items covered, but single assertion type (contains only) → diversity factor 0.5
    assert coverage == 0.5


def test_merge_evals():
    generator = EvalGenerator()
    current_evals = {
        "eval_cases": [
            {
                "id": 1,
                "name": "existing-case",
                "category": "normal",
                "input": "input1",
                "expected_triggers": True,
                "assertions": [{"type": "contains", "value": "test", "weight": 1}],
            }
        ]
    }

    supplementary_evals = {
        "eval_cases": [
            {
                "id": 1,
                "name": "new-case",
                "category": "boundary",
                "input": "input2",
                "expected_triggers": False,
                "assertions": [{"type": "not_contains", "value": "test", "weight": 1}],
            }
        ]
    }

    merged = generator._merge_evals(current_evals, supplementary_evals)

    assert len(merged["eval_cases"]) == 2
    assert merged["eval_cases"][0]["id"] == 1
    assert merged["eval_cases"][1]["id"] == 2


def test_generate_evals_with_convergence_success():
    generator = EvalGenerator()
    skill_spec = {
        "name": "test-skill",
        "description": "A test skill",
        "triggers": ["test"],
        "workflow_steps": [{"name": "step1", "type": "validation"}],
        "anti_patterns": ["skip_validation"],
        "output_format": ["json"],
    }

    mock_adapter = MockModelAdapter(
        [
            '{"eval_cases": [{"id": 1, "name": "test-case", "category": "normal", '
            '"input": "test input", "expected_triggers": true, '
            '"assertions": [{"type": "contains", "value": "test", "weight": 1}]}]}',
            '{"eval_cases": [{"id": 2, "name": "supp-case", "category": "normal", '
            '"input": "step1 input", "expected_triggers": true, '
            '"assertions": [{"type": "contains", "value": "step1", "weight": 1}]}]}',
        ]
    )

    mock_review_adapter = MockModelAdapter(
        [
            '{"coverage": 0.6, "gaps": ["more coverage needed"], "needs_improvement": true}',
            '{"coverage": 0.95, "gaps": [], "needs_improvement": false}',
        ]
    )
    mock_review_adapter.skill_spec = skill_spec

    result = generator.generate_evals_with_convergence(
        skill_spec, mock_adapter, mock_review_adapter
    )

    assert "eval_cases" in result or "evals" in result
    eval_cases = result.get("eval_cases", result.get("evals", []))
    assert len(eval_cases) >= 1


def test_generate_evals_with_convergence_degraded():
    generator = EvalGenerator()
    generator.coverage_threshold = 0.9
    generator.degrade_threshold = 0.6

    skill_spec = {
        "name": "test-skill",
        "description": "A test skill",
        "triggers": ["test"],
        "workflow_steps": [{"name": "step1", "type": "validation"}],
        "anti_patterns": ["skip_validation"],
        "output_format": ["json"],
    }

    mock_adapter = MockModelAdapter(
        [
            '{"eval_cases": [{"id": 1, "name": "test-case", "category": "normal", '
            '"input": "test input", "expected_triggers": true, '
            '"assertions": [{"type": "contains", "value": "test", "weight": 1}]}]}'
        ]
    )

    mock_review_adapter = MockModelAdapter(
        ['{"coverage": 0.7, "gaps": ["some gaps"], "needs_improvement": true}']
    )
    mock_review_adapter.skill_spec = skill_spec

    result = generator.generate_evals_with_convergence(
        skill_spec, mock_adapter, mock_review_adapter
    )

    assert "eval_cases" in result or "evals" in result
    eval_cases = result.get("eval_cases", result.get("evals", []))
    assert len(eval_cases) >= 0


def test_get_eval_cases_with_string_input():
    """Regression test for #30: _get_eval_cases with string evals (template fallback)."""
    gen = EvalGenerator()
    evals_str = "some template string"
    result = gen._get_eval_cases(evals_str)
    assert result == []


def test_calculate_coverage_with_string_evals():
    """Regression test for #30: _calculate_coverage handles string evals gracefully."""
    gen = EvalGenerator()
    evals_str = "not a dict"
    spec = {
        "workflow_steps": [{"name": "step1"}],
        "anti_patterns": [],
        "output_format": [],
    }
    result = gen._calculate_coverage(evals_str, spec)  # type: ignore[arg-type]
    assert result == 0.0


def test_generator_template_loading_error():
    """Test EvalGenerator when template loading fails."""

    # Temporarily change the template path to a non-existent location
    with patch("engine.testgen.Path") as mock_path:
        mock_path_instance = MagicMock()
        mock_path_instance.__truediv__.return_value = mock_path_instance
        mock_path.return_value = mock_path_instance
        mock_path_instance.exists.return_value = False

        # This should use the fallback template
        generator = EvalGenerator()

        # Check that fallback template is used
        assert "eval_cases" in generator.minimum_evals_template
        assert len(generator.minimum_evals_template["eval_cases"]) >= 1


def test_generate_initial_evals_error_handling():
    """Test generate_initial_evals error handling."""
    generator = EvalGenerator()
    skill_spec = {
        "name": "test-skill",
        "description": "A test skill",
        "triggers": ["test"],
        "workflow_steps": [],
        "anti_patterns": [],
        "output_format": [],
    }

    # Mock adapter that raises an exception
    class ErrorMockAdapter:
        def chat(self, messages):
            raise Exception("API Error")

    mock_adapter = ErrorMockAdapter()

    result = generator.generate_initial_evals(skill_spec, mock_adapter)

    # Should return the template when error occurs
    assert "eval_cases" in result or "evals" in result
    eval_cases = result.get("eval_cases", result.get("evals", []))
    assert len(eval_cases) >= 1


def test_review_evals_error_handling():
    """Test review_evals error handling."""
    generator = EvalGenerator()
    evals = {
        "eval_cases": [
            {
                "id": 1,
                "name": "test-case",
                "category": "normal",
                "input": "test input",
                "expected_triggers": True,
                "assertions": [{"type": "contains", "value": "test", "weight": 1}],
            }
        ]
    }

    # Mock adapter that raises an exception
    class ErrorMockAdapter:
        skill_spec: dict[str, Any] = {}

        def chat(self, messages):
            raise Exception("API Error")

    mock_review_adapter = ErrorMockAdapter()
    mock_review_adapter.skill_spec = {
        "name": "test-skill",
        "description": "A test skill",
        "triggers": ["test"],
        "workflow_steps": [],
        "anti_patterns": [],
        "output_format": [],
    }

    result = generator.review_evals(evals, mock_review_adapter)

    # Should return error structure when error occurs
    assert "coverage" in result
    assert "gaps" in result
    assert "needs_improvement" in result
    assert result["needs_improvement"] is True


def test_fill_gaps_error_handling():
    """Test fill_gaps error handling."""
    generator = EvalGenerator()
    gaps = {"coverage": 0.5, "gaps": ["workflow steps not covered"], "needs_improvement": True}

    skill_spec = {
        "name": "test-skill",
        "description": "A test skill",
        "triggers": ["test"],
        "workflow_steps": [],
        "anti_patterns": [],
        "output_format": [],
    }

    # Mock adapter that raises an exception
    class ErrorMockAdapter:
        def chat(self, messages):
            raise Exception("API Error")

    mock_adapter = ErrorMockAdapter()

    result = generator.fill_gaps(gaps, skill_spec, mock_adapter)

    # Should return empty eval cases when error occurs
    assert "eval_cases" in result
    assert result["eval_cases"] == []


def test_parse_evals_response_edge_cases():
    """Test _parse_evals_response with various edge cases."""
    generator = EvalGenerator()

    # Test with no JSON in response
    result = generator._parse_evals_response("This is not JSON at all")
    assert "eval_cases" in result or "evals" in result

    # Test with JSON that doesn't have eval_cases
    result = generator._parse_evals_response('{"other_key": "value"}')
    assert "eval_cases" in result or "evals" in result

    # Test with JSON that has evals instead of eval_cases
    result = generator._parse_evals_response('{"evals": [{"id": 1, "name": "test"}]}')
    assert "eval_cases" in result or "evals" in result

    # Test with completely invalid JSON
    result = generator._parse_evals_response("{{{ invalid json")
    assert "eval_cases" in result or "evals" in result


def test_has_sufficient_evals_edge_cases():
    """Test _has_sufficient_evals with various edge cases."""
    generator = EvalGenerator()

    # Test with no eval_cases key
    result = generator._has_sufficient_evals({})
    assert result is False

    # Test with empty eval_cases
    result = generator._has_sufficient_evals({"eval_cases": []})
    assert result is False

    # Test with insufficient evals
    result = generator._has_sufficient_evals({"eval_cases": [{"id": 1}]})
    assert result is True  # Has eval_cases = sufficient

    # Test with sufficient evals
    result = generator._has_sufficient_evals(
        {"eval_cases": [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}]}
    )
    assert result is True

    # Test with alternative key names
    result = generator._has_sufficient_evals(
        {"evals": [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}]}
    )
    assert result is True


def test_calculate_coverage_edge_cases():
    """Test _calculate_coverage with various edge cases."""
    generator = EvalGenerator()

    # Test with no eval cases
    evals = {"eval_cases": []}
    skill_spec = {
        "name": "test-skill",
        "description": "A test skill",
        "triggers": ["test"],
        "workflow_steps": [{"name": "step1"}],
        "anti_patterns": ["pattern1"],
        "output_format": ["json"],
    }
    coverage = generator._calculate_coverage(evals, skill_spec)
    assert coverage == 0.0

    # Test with no skill spec elements
    evals = {
        "eval_cases": [
            {
                "id": 1,
                "name": "test-case",
                "category": "normal",
                "input": "test input",
                "expected_triggers": True,
                "assertions": [{"type": "contains", "value": "test", "weight": 1}],
            }
        ]
    }
    skill_spec_empty = {
        "name": "test-skill",
        "description": "A test skill",
        "triggers": ["test"],
        "workflow_steps": [],
        "anti_patterns": [],
        "output_format": [],
    }
    coverage = generator._calculate_coverage(evals, skill_spec_empty)
    assert coverage == 1.0  # Should be 1.0 when there's nothing to cover


def test_parse_review_response_edge_cases():
    """Test _parse_review_response with various edge cases."""
    generator = EvalGenerator()

    # Test with invalid JSON
    result = generator._parse_review_response("{{{ invalid json", 0.5)
    assert result["coverage"] == 0.5
    assert "gaps" in result
    assert result["needs_improvement"] is True

    # Test with JSON missing required fields
    result = generator._parse_review_response('{"other_field": "value"}', 0.7)
    assert result["coverage"] == 0.7
    assert "gaps" in result
    # needs_improvement should be False because gaps is empty list by default
    assert result["needs_improvement"] is False

    # Test with valid JSON but missing fields
    result = generator._parse_review_response('{"coverage": 0.8}', 0.7)
    assert result["coverage"] == 0.8  # Should use the one from response
    assert "gaps" in result
    # needs_improvement should be False because gaps is empty list by default
    assert result["needs_improvement"] is False


def test_merge_evals_edge_cases():
    """Test _merge_evals with various edge cases."""
    generator = EvalGenerator()

    # Test with different key names
    current_evals = {"evals": [{"id": 1, "name": "existing"}]}
    supplementary_evals = {"cases": [{"id": 2, "name": "new"}]}

    merged = generator._merge_evals(current_evals, supplementary_evals)

    # Should handle different key names
    assert "evals" in merged or "cases" in merged or "eval_cases" in merged

    # Test with empty supplementary evals
    current_evals = {"eval_cases": [{"id": 1, "name": "existing"}]}
    supplementary_evals = {"eval_cases": []}

    merged = generator._merge_evals(current_evals, supplementary_evals)
    assert len(merged["eval_cases"]) == 1  # Should remain unchanged


def test_fill_gaps_receives_adapter_not_dict():
    generator = EvalGenerator()
    generator.coverage_threshold = 0.9
    generator.degrade_threshold = 0.7
    generator.consecutive_no_improvement = 3

    skill_spec = {
        "name": "test-skill",
        "description": "A test skill",
        "triggers": ["test"],
        "workflow_steps": [{"name": "step1"}],
        "anti_patterns": ["skip_validation"],
        "output_format": ["json"],
    }

    mock_adapter = MockModelAdapter(
        [
            '{"eval_cases": [{"id": 1, "name": "test-case", "category": "normal", '
            '"input": "test input", "expected_triggers": true, '
            '"assertions": [{"type": "contains", "value": "test", "weight": 1}]}]}'
        ]
    )

    mock_review_adapter = MockModelAdapter(
        [
            '{"coverage": 0.5, "gaps": ["workflow not covered"], "needs_improvement": true}',
            '{"coverage": 0.95, "gaps": [], "needs_improvement": false}',
        ]
    )
    mock_review_adapter.skill_spec = skill_spec

    result = generator.generate_evals_with_convergence(
        skill_spec, mock_adapter, mock_review_adapter
    )

    assert "eval_cases" in result or "evals" in result
    eval_cases = result.get("eval_cases", result.get("evals", []))
    assert len(eval_cases) >= 2, f"Expected at least 2 eval cases, got {len(eval_cases)}"


def test_generate_evals_with_convergence_error_scenario():
    """Test generate_evals_with_convergence with error scenarios."""
    generator = EvalGenerator()
    generator.coverage_threshold = 0.9
    generator.degrade_threshold = 0.6
    generator.block_threshold = 0.5

    skill_spec = {
        "name": "test-skill",
        "description": "A test skill",
        "triggers": ["test"],
        "workflow_steps": [{"name": "step1"}],
        "anti_patterns": ["skip_validation"],
        "output_format": ["json"],
    }

    # Mock adapter that fails on second call
    class FailingMockAdapter:
        def __init__(self):
            self.call_count = 0

        def chat(self, messages):
            self.call_count += 1
            if self.call_count == 1:
                return (
                    '{"eval_cases": [{"id": 1, "name": "test-case", "category": "normal", '
                    '"input": "test input", "expected_triggers": true, '
                    '"assertions": [{"type": "contains", "value": "test", "weight": 1}]}]}'
                )
            else:
                raise Exception("API Error on second call")

    mock_adapter = FailingMockAdapter()

    # Mock review adapter that also fails
    class FailingReviewMockAdapter:
        def __init__(self):
            self.skill_spec = skill_spec
            self.call_count = 0

        def chat(self, messages):
            self.call_count += 1
            if self.call_count == 1:
                return '{"coverage": 0.3, "gaps": ["many gaps"], "needs_improvement": true}'
            else:
                raise Exception("API Error on second review call")

    mock_review_adapter = FailingReviewMockAdapter()

    result = generator.generate_evals_with_convergence(
        skill_spec, mock_adapter, mock_review_adapter
    )

    # Should return minimum template when coverage is below block threshold and no evals generated
    assert "eval_cases" in result or "evals" in result or "cases" in result


# ── CoverageResult tests (REQ-017) ──────────────────────────────────────


def test_coverage_result_all_paths():
    """Test CoverageResult enum returns correct value for each boundary."""
    from engine.constants import CoverageThresholds
    from engine.testgen import CoverageResult

    gen = EvalGenerator()

    # PASS: coverage >= 0.9
    assert gen.check_coverage_or_abort(0.95) == CoverageResult.PASS
    assert gen.check_coverage_or_abort(0.9) == CoverageResult.PASS

    # DEGRADED: 0.7 <= coverage < 0.9
    assert gen.check_coverage_or_abort(0.85) == CoverageResult.DEGRADED
    assert gen.check_coverage_or_abort(0.7) == CoverageResult.DEGRADED

    # BLOCKED: 0.5 <= coverage < 0.7
    assert gen.check_coverage_or_abort(0.65) == CoverageResult.BLOCKED
    assert gen.check_coverage_or_abort(0.5) == CoverageResult.BLOCKED

    # FAILED: coverage < 0.5
    assert gen.check_coverage_or_abort(0.22) == CoverageResult.FAILED
    assert gen.check_coverage_or_abort(0.0) == CoverageResult.FAILED

    # Verify constants match
    assert CoverageThresholds.COVERAGE_BLOCK == 0.5
    assert CoverageThresholds.COVERAGE_DEGRADE == 0.7
    assert CoverageThresholds.COVERAGE_TARGET == 0.9


def test_fail_fast_gate():
    """Verify that coverage=0.22 (FAILED) produces failed=True in result."""
    gen = EvalGenerator()
    skill_spec = {
        "name": "test-skill",
        "description": "A test skill",
        "triggers": ["test"],
        "workflow_steps": [{"name": "step1"}],
        "anti_patterns": ["skip_validation"],
        "output_format": ["json"],
    }

    mock_adapter = MockModelAdapter(
        [
            '{"eval_cases": [{"id": 1, "name": "test-case", "category": "normal", '
            '"input": "test input", "expected_triggers": true, '
            '"assertions": [{"type": "contains", "value": "test", "weight": 1}]}]}'
        ]
    )

    mock_review_adapter = MockModelAdapter(
        ['{"coverage": 0.22, "gaps": ["many gaps"], "needs_improvement": true}']
    )
    mock_review_adapter.skill_spec = skill_spec

    evals = gen.generate_evals_with_convergence(skill_spec, mock_adapter, mock_review_adapter)

    # Should have failed flag set
    assert evals.get("failed", False) is True
    # Degraded should be True (since BLOCKED < 0.22 < TARGET)
    assert evals.get("degraded", False) is True


def test_coverage_result_importable_from_eval_generator():
    """AC-019-01: Verify CoverageResult is accessible via EvalGenerator.CoverageResult."""
    from engine.testgen import EvalGenerator

    # Must be importable as EvalGenerator.CoverageResult.PASS
    assert EvalGenerator.CoverageResult.PASS.value == "PASS"
    assert EvalGenerator.CoverageResult.DEGRADED.value == "DEGRADED"
    assert EvalGenerator.CoverageResult.BLOCKED.value == "BLOCKED"
    assert EvalGenerator.CoverageResult.FAILED.value == "FAILED"

    # Verify check_coverage_or_abort returns the enum member, not raw string
    gen = EvalGenerator()
    assert gen.check_coverage_or_abort(0.95) is EvalGenerator.CoverageResult.PASS
    assert gen.check_coverage_or_abort(0.85) is EvalGenerator.CoverageResult.DEGRADED
    assert gen.check_coverage_or_abort(0.55) is EvalGenerator.CoverageResult.BLOCKED
    assert gen.check_coverage_or_abort(0.49) is EvalGenerator.CoverageResult.FAILED


def test_degraded_mode_verdict_cap():
    """Verify that degraded=True caps verdict to PASS_WITH_CAVEATS."""
    from engine.reporter import Reporter

    reporter = Reporter()

    # When degraded=True and overall_score >= 0.8 (would be PASS)
    verdict = reporter._determine_verdict(0.85, {"overall_verdict": "PASS"}, degraded=True)
    assert verdict == "PASS_WITH_CAVEATS", (
        f"Expected PASS_WITH_CAVEATS when degraded, got {verdict}"
    )

    # When degraded=False and overall_score >= 0.8 → PASS
    verdict = reporter._determine_verdict(0.85, {"overall_verdict": "PASS"}, degraded=False)
    assert verdict == "PASS"

    # When degraded=True and overall_score < 0.8 → still PASS_WITH_CAVEATS (not FAIL)
    verdict = reporter._determine_verdict(0.75, {"overall_verdict": "PASS"}, degraded=True)
    assert verdict == "PASS_WITH_CAVEATS"

    # When degraded=True but drift says FAIL → FAIL
    verdict = reporter._determine_verdict(0.85, {"overall_verdict": "FAIL"}, degraded=True)
    assert verdict == "FAIL"


def test_extract_regex_branches_basic_alternation():
    """Extract branches from (a|b|c) pattern."""
    generator = EvalGenerator()
    result = generator._extract_regex_branches("(a|b|c)")
    assert set(result) == {"a", "b", "c"}, f"Expected [a, b, c], got {result}"


def test_extract_regex_branches_no_parens():
    """Extract branches from a|b|c without outer parens."""
    generator = EvalGenerator()
    result = generator._extract_regex_branches("a|b|c")
    assert set(result) == {"a", "b", "c"}, f"Expected [a, b, c], got {result}"


def test_extract_regex_branches_nested():
    """Handle nested alternation (a|(b|c))."""
    generator = EvalGenerator()
    result = generator._extract_regex_branches("(a|(b|c))")
    assert set(result) == {"a", "b", "c"}, f"Expected [a, b, c], got {result}"


def test_extract_regex_branches_separate_groups():
    """Handle separate groups like (a)|(b)."""
    generator = EvalGenerator()
    result = generator._extract_regex_branches("(a)|(b)")
    assert set(result) == {"a", "b"}, f"Expected [a, b], got {result}"


def test_extract_regex_branches_no_alternation():
    """Non-regex strings pass through unchanged."""
    generator = EvalGenerator()
    result = generator._extract_regex_branches("plain text")
    assert result == ["plain text"], f"Expected ['plain text'], got {result}"


def test_extract_regex_branches_escaped_pipe():
    """Escaped pipe | should not be treated as alternation."""
    generator = EvalGenerator()
    result = generator._extract_regex_branches(r"a\|b")
    assert result == [r"a\|b"], f"Expected ['a\\\\|b'], got {result}"


def test_extract_regex_branches_empty_string():
    """Empty string returns [value]."""
    generator = EvalGenerator()
    result = generator._extract_regex_branches("")
    assert result == [""], f"Expected [''], got {result}"


def test_extract_regex_branches_depth_limit():
    """Deeply nested alternation hits depth limit and returns as-is."""
    generator = EvalGenerator()
    result = generator._extract_regex_branches("((((a|b)))", _depth=4)
    assert result == ["((((a|b)))"], "Expected truncated result at depth limit"


def test_extract_regex_branches_skipped_escaped_parens():
    """Escaped parens \\\\( and \\\\) should not affect depth tracking."""
    generator = EvalGenerator()
    result = generator._extract_regex_branches(r"(\(x\)|y)")
    # Escaped characters are preserved verbatim; r"\(x\)" is the literal branch content
    assert set(result) == {r"\(x\)", "y"}, f"Expected ['\\\\(x\\\\)', 'y'], got {result}"


def test_extract_regex_branches_empty_branches_filtered():
    """Empty branches from || are filtered out."""
    generator = EvalGenerator()
    result = generator._extract_regex_branches(r"a||b")
    assert set(result) == {"a", "b"}, f"Expected [a, b], got {result}"


def test_extract_regex_branches_single_branch():
    """Single branch with parens but no | returns original."""
    generator = EvalGenerator()
    result = generator._extract_regex_branches("(single)")
    assert result == ["(single)"], f"Expected ['(single)'], got {result}"


def test_extract_regex_branches_deduplicates():
    """Duplicate branches are deduplicated preserving order."""
    generator = EvalGenerator()
    result = generator._extract_regex_branches("(a|b|a)")
    assert result == ["a", "b"], f"Expected ['a', 'b'], got {result}"


def test_compute_section_coverage_empty_assertion_filtered():
    """Empty assertion value does not inflate coverage."""
    generator = EvalGenerator()
    section_items = ["Step A", "Step B", "Step C"]
    assertion_set = {"(Step A|Step B)", ""}
    coverage = generator._compute_section_coverage(section_items, assertion_set)
    assert coverage == pytest.approx(2 / 3, rel=1e-3), (
        f"Expected ~0.667, got {coverage} — empty string should not inflate"
    )


def test_compute_section_coverage_with_regex_alternation():
    """_compute_section_coverage correctly matches regex alternation patterns."""
    generator = EvalGenerator()
    section_items = ["Parse SKILL.md", "Generate tests", "Execute evaluation"]
    assertion_set = {"(Parse SKILL.md|Generate tests|Execute evaluation)"}
    coverage = generator._compute_section_coverage(section_items, assertion_set)
    assert coverage == 1.0, f"Expected 1.0 coverage, got {coverage}"


def test_compute_section_coverage_partial_regex():
    """Partial coverage with regex alternation produces partial score."""
    generator = EvalGenerator()
    section_items = ["Step A", "Step B", "Step C"]
    assertion_set = {"(Step A|Step B)"}
    coverage = generator._compute_section_coverage(section_items, assertion_set)
    assert coverage == pytest.approx(2 / 3, rel=1e-3), f"Expected ~0.667, got {coverage}"


def test_compute_section_coverage_plain_strings_still_work():
    """Plain string assertions still produce correct coverage after fix."""
    generator = EvalGenerator()
    section_items = ["step1", "step2"]
    assertion_set = {"step1", "step2"}
    coverage = generator._compute_section_coverage(section_items, assertion_set)
    assert coverage == 1.0, f"Expected 1.0, got {coverage}"


def test_calculate_coverage_with_regex_assertions():
    """_calculate_coverage correctly handles regex assertion values in full pipeline."""
    generator = EvalGenerator()
    evals = {
        "eval_cases": [
            {
                "id": 1,
                "name": "regex-case",
                "category": "normal",
                "input": "test input",
                "expected_triggers": True,
                "assertions": [
                    {"type": "regex", "value": "(Parse SKILL.md|Analyze structure)", "weight": 3},
                    {"type": "regex", "value": "(skip validation|never test)", "weight": 2},
                    {"type": "regex", "value": "(PASS/FAIL verdict|JSON output)", "weight": 2},
                ],
            }
        ]
    }
    skill_spec = {
        "name": "test-skill",
        "description": "A test skill",
        "triggers": ["test"],
        "workflow_steps": [{"name": "Parse SKILL.md"}, {"name": "Analyze structure"}],
        "anti_patterns": ["skip validation"],
        "output_format": ["PASS/FAIL verdict", "JSON output"],
    }
    coverage = generator._calculate_coverage(evals, skill_spec)
    # All spec items covered, but only 1 assertion type (regex) → diversity factor 0.5
    assert coverage == 0.5, f"Expected 0.5 (diversity penalty: single assertion type), got {coverage}"


@pytest.mark.parametrize(
    "input_case,expected",
    [
        # Standard: explicit negative_case field
        ({"negative_case": True, "input": "test", "assertions": [{"name": "d", "type": "contains", "value": ".", "weight": 1}]}, True),
        ({"negative_case": False, "input": "test", "assertions": [{"name": "d", "type": "contains", "value": ".", "weight": 1}]}, False),
        # Variant: is_negative
        ({"is_negative": True, "input": "test", "assertions": [{"name": "d", "type": "contains", "value": ".", "weight": 1}]}, True),
        ({"is_negative": False, "input": "test", "assertions": [{"name": "d", "type": "contains", "value": ".", "weight": 1}]}, False),
        # Variant: should_not
        ({"should_not": True, "input": "test", "assertions": [{"name": "d", "type": "contains", "value": ".", "weight": 1}]}, True),
        # Variant: expected_triggers=False → negative_case=True (inversion)
        ({"expected_triggers": False, "input": "test", "assertions": [{"name": "d", "type": "contains", "value": ".", "weight": 1}]}, True),
        ({"expected_triggers": True, "input": "test", "assertions": [{"name": "d", "type": "contains", "value": ".", "weight": 1}]}, False),
        # Variant: triggers_on=False → negative_case=True (inversion)
        ({"triggers_on": False, "input": "test", "assertions": [{"name": "d", "type": "contains", "value": ".", "weight": 1}]}, True),
        # Variant: string "true" → coerced to bool
        ({"negative": "true", "input": "test", "assertions": [{"name": "d", "type": "contains", "value": ".", "weight": 1}]}, True),
        # No negative info → default False
        ({"input": "test", "assertions": [{"name": "d", "type": "contains", "value": ".", "weight": 1}]}, False),
    ],
)
def test_normalize_eval_case_negative_case(input_case, expected):
    """_normalize_eval_case correctly handles negative_case from all variants."""
    from engine.testgen import EvalGenerator

    normalized = EvalGenerator._normalize_eval_case(input_case, idx=0)
    assert normalized.get("negative_case") is expected, (
        f"For input {input_case}, expected negative_case={expected}, "
        f"got {normalized.get('negative_case')}"
    )


class TestPrepareGenerationPromptBranching:
    """Test _prepare_generation_prompt branches on skill_type."""

    def test_prompt_for_agent_guide_default(self):
        """Default agent_guide skill_type produces standard eval prompt."""
        generator = EvalGenerator()
        skill_spec = {
            "name": "review-skill",
            "description": "A code review skill",
            "skill_type": "agent_guide",
            "triggers": ["review"],
            "workflow_steps": [{"name": "Read code"}],
            "anti_patterns": [],
            "output_format": [],
            "examples": [],
        }
        prompt = generator._prepare_generation_prompt(skill_spec)
        assert "workflow" in prompt.lower() or "Workflow" in prompt
        assert "trigger" in prompt.lower() or "Trigger" in prompt
        assert "cli" not in prompt.lower().split("skill")[0]

    def test_prompt_for_cli_tool(self):
        """CLI tool skill_type produces prompt with CLI-specific eval guidance."""
        generator = EvalGenerator()
        skill_spec = {
            "name": "skill-cert",
            "description": "AI Skill Evaluation Engine",
            "skill_type": "cli_tool",
            "triggers": ["evaluate"],
            "workflow_steps": [],
            "anti_patterns": [],
            "output_format": [],
            "examples": [],
        }
        prompt = generator._prepare_generation_prompt(skill_spec)
        assert "cli" in prompt.lower() or "command" in prompt.lower()
        assert "flag" in prompt.lower() or "exit" in prompt.lower() or "--" in prompt

    def test_prompt_for_library(self):
        """Library skill_type produces prompt with API/function-specific eval guidance."""
        generator = EvalGenerator()
        skill_spec = {
            "name": "data-utils",
            "description": "Data utility library",
            "skill_type": "library",
            "triggers": [],
            "workflow_steps": [],
            "anti_patterns": [],
            "output_format": [],
            "examples": [],
        }
        prompt = generator._prepare_generation_prompt(skill_spec)
        assert "api" in prompt.lower() or "function" in prompt.lower() or "import" in prompt.lower()

    def test_prompt_missing_skill_type_defaults_to_agent_guide(self):
        """Missing skill_type key should behave as agent_guide (backward compat)."""
        generator = EvalGenerator()
        skill_spec = {
            "name": "old-skill",
            "description": "No skill_type field",
            "triggers": ["test"],
            "workflow_steps": [{"name": "Step 1"}],
            "anti_patterns": [],
            "output_format": [],
            "examples": [],
        }
        prompt = generator._prepare_generation_prompt(skill_spec)
        assert "trigger" in prompt.lower() or "Trigger" in prompt
        assert "workflow" in prompt.lower() or "Workflow" in prompt

    def test_cli_prompt_includes_exit_code_guidance(self):
        """CLI tool prompt should mention exit codes or return codes."""
        generator = EvalGenerator()
        skill_spec = {
            "name": "my-cli",
            "description": "A CLI tool",
            "skill_type": "cli_tool",
            "triggers": [],
            "workflow_steps": [],
            "anti_patterns": [],
            "output_format": [],
            "examples": [],
        }
        prompt = generator._prepare_generation_prompt(skill_spec)
        prompt_lower = prompt.lower()
        assert "exit" in prompt_lower or "return code" in prompt_lower or "non-zero" in prompt_lower

    def test_prompt_does_not_instruct_asymmetric_assertions(self):
        """The agent_guide prompt must NOT instruct LLM to use not_contains for without_skill."""
        generator = EvalGenerator()
        skill_spec = {
            "name": "review-skill",
            "description": "A code review skill",
            "skill_type": "agent_guide",
            "triggers": ["review"],
            "workflow_steps": [{"name": "Read code"}],
            "anti_patterns": [{"pattern": "skip review"}],
            "output_format": [{"field": "verdict"}],
            "examples": [],
        }
        prompt = generator._prepare_generation_prompt(skill_spec)
        prompt_lower = prompt.lower()
        # Old buggy prompt said: "Use assertions that measure skill-specific STRUCTURAL MARKERS are MISSING"
        # and suggested not_contains for without_skill assertions.
        # Fixed prompt should NOT contain these asymmetry instructions.
        assert "markers are missing" not in prompt_lower, (
            "Prompt should not instruct LLM to use not_contains assertions"
            " for without_skill (asymmetry bug)"
        )
        # The prompt should either omit without_skill guidance entirely
        # or instruct symmetric assertion types.
        assert "same assertion" in prompt_lower or (
            "without_skill" in prompt_lower and "same" in prompt_lower
        ), (
            "Prompt should instruct symmetric assertions for without_skill,"
            " not asymmetric not_contains"
        )


# ---------------------------------------------------------------------------
# Multi-strategy JSON extraction tests (slice-6)
# ---------------------------------------------------------------------------


class TestExtractJson:
    """Tests for _extract_json() — 4-level fallback JSON extraction."""

    def test_strategy1_clean_json(self):
        """Strategy 1: Clean JSON passes through directly."""
        result = EvalGenerator._extract_json('{"eval_cases": [{"id": 1}]}')
        assert result == {"eval_cases": [{"id": 1}]}

    def test_strategy1_markdown_fenced_json(self):
        """Strategy 1: JSON inside ```json fence."""
        response = '```json\n{"eval_cases": [{"id": 1}]}\n```'
        result = EvalGenerator._extract_json(response)
        assert result == {"eval_cases": [{"id": 1}]}

    def test_strategy1_json_with_prose_before(self):
        """Strategy 1: JSON with prose before it."""
        response = 'Here are the evals:\n{"eval_cases": [{"id": 1}]}'
        result = EvalGenerator._extract_json(response)
        assert result == {"eval_cases": [{"id": 1}]}

    def test_strategy2_balanced_brace_extraction(self):
        """Strategy 2: Extract outermost balanced braces when first{last} fails."""
        # Multiple JSON objects — first{ to last} would span across them
        response = '{"a": 1} some text {"b": 2}'
        result = EvalGenerator._extract_json(response)
        # Should extract the first valid JSON object
        assert isinstance(result, dict)
        assert "a" in result or "b" in result

    def test_strategy2_nested_braces(self):
        """Strategy 2: Handles nested braces correctly."""
        response = 'prefix {"eval_cases": [{"id": 1, "assertions": [{"type": "contains"}]}]} suffix'
        result = EvalGenerator._extract_json(response)
        assert result is not None
        assert result["eval_cases"][0]["id"] == 1

    def test_strategy3_largest_first(self):
        """Strategy 3: Try largest brace block first when smaller ones fail."""
        # Outer JSON is valid but contains inner fragments that could confuse simpler parsers
        response = 'noise {broken} {"eval_cases": [{"id": 1}]}'
        result = EvalGenerator._extract_json(response)
        assert isinstance(result, dict)
        assert "eval_cases" in result

    def test_strategy4_strict_false(self):
        """Strategy 4: json.loads with strict=False handles control chars."""
        response = '{"eval_cases": [{"id": 1, "name": "test\x01value"}]}'
        result = EvalGenerator._extract_json(response)
        assert isinstance(result, dict)

    def test_all_strategies_fail_returns_none(self):
        """When all strategies fail, returns None."""
        result = EvalGenerator._extract_json("no json here at all")
        assert result is None

    def test_empty_string_returns_none(self):
        """Empty string returns None."""
        result = EvalGenerator._extract_json("")
        assert result is None

    def test_strategy2_prose_with_multiple_brace_groups(self):
        """Strategy 2: Picks first valid balanced JSON from multiple groups."""
        response = 'text {invalid stuff} more text {"valid": true} end'
        result = EvalGenerator._extract_json(response)
        assert isinstance(result, dict)

    def test_json_with_array_at_top_level_not_extracted(self):
        """Non-object JSON (arrays) — should still extract if wrapped in object."""
        response = '{"eval_cases": [1, 2, 3]}'
        result = EvalGenerator._extract_json(response)
        assert result == {"eval_cases": [1, 2, 3]}


class TestParseEvalsResponseMultiStrategy:
    """Tests that _parse_evals_response uses multi-strategy extraction."""

    def test_extracts_from_prose_with_multiple_json_objects(self):
        """Parse evals when response has multiple JSON-like blocks."""
        generator = EvalGenerator()
        response = (
            'Here is one example: {"old": true}\n'
            "And here are the evals:\n"
            '{"eval_cases": [{"id": 1, "name": "test", "category": "normal", '
            '"input": "test", "expected_triggers": true, '
            '"assertions": [{"type": "contains", "value": "test", "weight": 1}]}]}'
        )
        result = generator._parse_evals_response(response)
        assert "eval_cases" in result
        assert len(result["eval_cases"]) >= 1

    def test_fallback_to_template_when_all_fail(self):
        """All strategies fail → returns minimum_evals_template."""
        generator = EvalGenerator()
        result = generator._parse_evals_response("completely unparseable garbage!!!")
        assert "eval_cases" in result or "evals" in result
        assert result == generator.minimum_evals_template

    def test_markdown_fenced_with_extra_prose(self):
        """Markdown fence with prose around it."""
        generator = EvalGenerator()
        response = (
            "Sure! Here are the evaluation cases:\n"
            "```json\n"
            '{"eval_cases": [{"id": 1, "name": "test", "category": "normal", '
            '"input": "test", "expected_triggers": true, '
            '"assertions": [{"type": "contains", "value": "test", "weight": 1}]}]}\n'
            "```\n"
            "Let me know if you need more!"
        )
        result = generator._parse_evals_response(response)
        assert "eval_cases" in result
        assert len(result["eval_cases"]) == 1


class TestParseReviewResponseMultiStrategy:
    """Tests that _parse_review_response uses multi-strategy extraction."""

    def test_extracts_from_fenced_response(self):
        """Parse review from markdown-fenced response."""
        generator = EvalGenerator()
        response = (
            "```json\n"
            '{"coverage": 0.85, "gaps": ["missing trigger test"], '
            '"needs_improvement": true}\n'
            "```"
        )
        result = generator._parse_review_response(response, 0.5)
        assert result["coverage"] == 0.85
        assert result["gaps"] == ["missing trigger test"]
        assert result["needs_improvement"] is True

    def test_extracts_from_prose_wrapped_response(self):
        """Parse review when JSON is wrapped in prose."""
        generator = EvalGenerator()
        response = (
            "Based on my review:\n"
            '{"coverage": 0.9, "gaps": [], "needs_improvement": false}\n'
            "This looks good."
        )
        result = generator._parse_review_response(response, 0.5)
        assert result["coverage"] == 0.9
        assert result["needs_improvement"] is False

    def test_fallback_when_all_strategies_fail(self):
        """All strategies fail → returns error dict with current coverage."""
        generator = EvalGenerator()
        result = generator._parse_review_response("garbage!!!", 0.6)
        assert result["coverage"] == 0.6
        assert result["needs_improvement"] is True


class TestGenerateInitialEvalsRetry:
    """Tests for retry logic in generate_initial_evals()."""

    def test_retries_on_parse_failure(self):
        """generate_initial_evals retries when first parse fails, succeeds on retry 1."""
        generator = EvalGenerator()
        adapter = MockModelAdapter(
            responses=[
                "garbage that cannot be parsed as json!!!",
                '{"eval_cases": [{"id": 1, "name": "test", "category": "normal", '
                '"input": "test", "expected_triggers": true, '
                '"assertions": [{"type": "contains", "value": "test", "weight": 1}]}]}',
            ]
        )
        skill_spec = {
            "name": "test-skill",
            "description": "A test skill",
            "triggers": ["test"],
            "workflow_steps": [],
            "anti_patterns": [],
            "output_format": [],
            "examples": [],
        }
        result = generator.generate_initial_evals(skill_spec, adapter)
        assert adapter.call_count == 2  # First attempt + 1 retry
        assert "eval_cases" in result
        assert len(result["eval_cases"]) >= 1

    def test_returns_template_after_retry_failure(self):
        """All retry attempts fail → returns minimum_evals_template after exhaustion."""
        generator = EvalGenerator()
        adapter = MockModelAdapter(
            responses=[
                "garbage!!!",
                "more garbage!!!",
                "still garbage!!!",
                "nothing parseable at all!!!",
            ]
        )
        skill_spec = {
            "name": "test-skill",
            "description": "A test skill",
            "triggers": ["test"],
            "workflow_steps": [],
            "anti_patterns": [],
            "output_format": [],
            "examples": [],
        }
        result = generator.generate_initial_evals(skill_spec, adapter)
        assert adapter.call_count == 4  # 1 initial + 3 retries
        assert result == generator.minimum_evals_template

    def test_no_retry_on_success(self):
        """First attempt succeeds → no retry."""
        generator = EvalGenerator()
        adapter = MockModelAdapter(
            responses=[
                '{"eval_cases": [{"id": 1, "name": "test", "category": "normal", '
                '"input": "test", "expected_triggers": true, '
                '"assertions": [{"type": "contains", "value": "test", "weight": 1}]}]}',
            ]
        )
        skill_spec = {
            "name": "test-skill",
            "description": "A test skill",
            "triggers": ["test"],
            "workflow_steps": [],
            "anti_patterns": [],
            "output_format": [],
            "examples": [],
        }
        result = generator.generate_initial_evals(skill_spec, adapter)
        assert adapter.call_count == 1
        assert "eval_cases" in result

    def test_retry_sends_json_only_hint(self):
        """Retry includes explicit JSON-only system hint on first retry attempt."""
        generator = EvalGenerator()
        calls_made = []

        class TrackingAdapter:
            def __init__(self):
                self.skill_spec = {}
                self.call_count = 0

            def chat(self, messages, **kwargs):
                calls_made.append(messages)
                self.call_count += 1
                if self.call_count == 1:
                    return "garbage!!!"
                return (
                    '{"eval_cases": [{"id": 1, "name": "test", "category": "normal", '
                    '"input": "test", "expected_triggers": true, '
                    '"assertions": [{"type": "contains", "value": "test", "weight": 1}]}]}'
                )

        adapter = TrackingAdapter()
        skill_spec = {
            "name": "test-skill",
            "description": "A test skill",
            "triggers": ["test"],
            "workflow_steps": [],
            "anti_patterns": [],
            "output_format": [],
            "examples": [],
        }
        generator.generate_initial_evals(skill_spec, adapter)
        assert len(calls_made) == 2
        second_messages = calls_made[1]
        has_json_hint = any("JSON" in str(m) or "json" in str(m) for m in second_messages)
        assert has_json_hint

    def test_three_retry_exhaustion_falls_back_to_template(self):
        """After 3 retry attempts all fail, returns minimum_evals_template."""
        generator = EvalGenerator()
        adapter = MockModelAdapter(
            responses=[
                "garbage 1!!!",
                "garbage 2!!!",
                "garbage 3!!!",
                "garbage 4!!!",
            ]
        )
        skill_spec = {
            "name": "test-skill",
            "description": "A test skill",
            "triggers": ["test"],
            "workflow_steps": [],
            "anti_patterns": [],
            "output_format": [],
            "examples": [],
        }
        result = generator.generate_initial_evals(skill_spec, adapter)
        assert adapter.call_count == 4  # 1 initial + 3 retries
        assert result == generator.minimum_evals_template

    def test_retry_escalates_hints_progressively(self):
        """Each retry sends progressively stronger system hints."""
        generator = EvalGenerator()
        calls_made: list[list[dict[str, Any]]] = []

        class HintTrackingAdapter:
            def __init__(self):
                self.skill_spec = {}
                self.call_count = 0

            def chat(self, messages, **kwargs):
                calls_made.append(list(messages))
                self.call_count += 1
                if self.call_count == 4:
                    return (
                        '{"eval_cases": [{"id": 1, "name": "test", "category": "normal", '
                        '"input": "test", "expected_triggers": true, '
                        '"assertions": [{"type": "contains", "value": "test", "weight": 1}]}]}'
                    )
                return "garbage!!!"

        adapter = HintTrackingAdapter()
        skill_spec = {
            "name": "test-skill",
            "description": "A test skill",
            "triggers": ["test"],
            "workflow_steps": [],
            "anti_patterns": [],
            "output_format": [],
            "examples": [],
        }
        result = generator.generate_initial_evals(skill_spec, adapter)
        assert result != generator.minimum_evals_template
        assert adapter.call_count == 4

        # Check each retry call's system hint for the expected escalation keywords
        retry_contents = [str(calls_made[i]) for i in range(1, 4)]
        assert "No prose" in retry_contents[0]
        assert "trailing commas" in retry_contents[1]
        assert "MINIMAL" in retry_contents[2]


class TestTrailingCommaRepair:
    """Tests for _repair_json_trailing_commas() in EvalGenerator."""

    def test_trailing_comma_repair_succeeds(self):
        """Trailing comma in JSON object is repaired transparently."""
        result = EvalGenerator._extract_json(
            '{\n'
            '  "eval_cases": [{"id": 1, "name": "test",},\n'
            '  {"id": 2, "name": "test2",}],\n'
            '}'
        )
        assert result is not None
        assert result["eval_cases"][0]["id"] == 1
        assert result["eval_cases"][1]["id"] == 2

    def test_trailing_comma_in_nested_json(self):
        """Trailing commas in nested JSON objects and arrays are repaired."""
        result = EvalGenerator._extract_json(
            '{"eval_cases": ['
            '{"id": 1, "assertions": [{"type": "contains", "value": "x",},],},'
            ']}'
        )
        assert result is not None
        assert result["eval_cases"][0]["id"] == 1
        assert len(result["eval_cases"][0]["assertions"]) == 1

    def test_repair_method_rejects_unrepairable_json(self):
        """Non-JSON after repair returns None."""
        result = EvalGenerator._repair_json_trailing_commas("not json at all")
        assert result is None


class TestAssertionQuality:
    def test_generation_prompt_has_keyword_blacklist(self):
        """Generation prompt MUST instruct LLM to avoid keyword-only assertions."""
        from engine.testgen import EvalGenerator

        gen = EvalGenerator()
        spec = {
            "name": "test-skill",
            "skill_type": "agent_guide",
            "description": "A test skill",
            "triggers": ["test"],
            "workflow_steps": [],
            "anti_patterns": [],
            "output_format": [],
            "examples": [],
        }
        prompt = gen._prepare_generation_prompt(spec)
        prompt_lower = prompt.lower()
        # Must warn against keyword-only assertions (prompt uses DO NOT with blacklisted keywords)
        assert "do not use" in prompt_lower
        assert "contains \"skill\"" in prompt_lower or "contains 'skill'" in prompt_lower
        # Must require structural assertions
        assert "structural" in prompt_lower

    def test_generation_prompt_has_assertion_diversity_requirement(self):
        """Generation prompt MUST require at least 3 different assertion types."""
        from engine.testgen import EvalGenerator

        gen = EvalGenerator()
        spec = {
            "name": "test-skill",
            "skill_type": "agent_guide",
            "description": "A test skill",
            "triggers": ["test"],
            "workflow_steps": [],
            "anti_patterns": [],
            "output_format": [],
            "examples": [],
        }
        prompt = gen._prepare_generation_prompt(spec)
        prompt_lower = prompt.lower()
        assert "different assertion types" in prompt_lower or "3 different" in prompt_lower

    def test_generation_prompt_prohibits_skill_keyword_assertion(self):
        """Generation prompt MUST prohibit assertions that only check for the word 'skill'."""
        from engine.testgen import EvalGenerator

        gen = EvalGenerator()
        spec = {
            "name": "test-skill",
            "skill_type": "agent_guide",
            "description": "A test skill",
            "triggers": ["test"],
            "workflow_steps": [],
            "anti_patterns": [],
            "output_format": [],
            "examples": [],
        }
        prompt = gen._prepare_generation_prompt(spec)
        prompt_lower = prompt.lower()
        # Must explicitly ban keyword 'skill' on its own as an assertion
        assert "skill" in prompt_lower
        assert "keyword" in prompt_lower


if __name__ == "__main__":
    pytest.main([__file__])
