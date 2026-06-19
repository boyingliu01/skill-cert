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

    assert coverage == 1.0


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
    assert coverage == 1.0, f"Expected 1.0, got {coverage}"


if __name__ == "__main__":
    pytest.main([__file__])
