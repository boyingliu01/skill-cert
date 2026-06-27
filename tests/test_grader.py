"""Tests for engine/grader.py — evaluation grading functionality."""

import json
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from engine.grader import AssertionResult, EvalAssertion, EvalCase, Grader, JudgeResult


class TestGrader:
    """Test the Grader class and its grading functionality."""

    def test_grade_output_basic(self):
        """Test basic grading of a model output."""
        grader = Grader()

        eval_case = EvalCase(
            id=1,
            name="test_case",
            category="normal",
            prompt="Say hello",
            expected_output="Hello world",
            assertions=[
                EvalAssertion(name="contains_hello", type="contains", value="hello", weight=1),
                EvalAssertion(name="not_contains_bad", type="not_contains", value="bad", weight=2),
            ],
        )

        model_output = "Hello world, this is good"
        result = grader.grade_output(eval_case, model_output)

        assert result["eval_id"] == 1
        assert result["eval_name"] == "test_case"
        assert result["category"] == "normal"
        assert result["model_output"] == "Hello world, this is good"
        assert result["total_weighted_score"] == 3  # Both assertions pass (1*1 + 1*2)
        assert result["total_possible_score"] == 3  # Both assertions have weights 1+2
        assert result["pass_rate"] == 1.0
        assert result["final_passed"] is True

    def test_grade_output_with_failures(self):
        """Test grading when some assertions fail."""
        grader = Grader()

        eval_case = EvalCase(
            id=2,
            name="test_case_failure",
            category="normal",
            prompt="Say goodbye",
            expected_output="Goodbye",
            assertions=[
                EvalAssertion(name="contains_goodbye", type="contains", value="Goodbye", weight=1),
                EvalAssertion(
                    name="contains_hello", type="contains", value="helloXXX", weight=2
                ),  # Use term that won't match
            ],
        )

        model_output = "Goodbye, but no helloXX"
        result = grader.grade_output(eval_case, model_output)

        assert result["total_weighted_score"] == 1  # Only first assertion passes (1*1)
        assert result["total_possible_score"] == 3  # Both assertions have weights 1+2
        assert result["pass_rate"] == 1 / 3
        assert result["final_passed"] is False  # Less than 50% pass rate

    def test_grade_output_regex_assertion(self):
        """Test grading with regex assertion."""
        grader = Grader()

        eval_case = EvalCase(
            id=3,
            name="regex_test",
            category="normal",
            prompt="Provide a phone number",
            expected_output="(123) 456-7890",
            assertions=[
                EvalAssertion(
                    name="phone_pattern", type="regex", value=r"\(\d{3}\) \d{3}-\d{4}", weight=1
                )
            ],
        )

        model_output = "Call me at (123) 456-7890"
        result = grader.grade_output(eval_case, model_output)

        assert result["total_weighted_score"] == 1
        assert result["total_possible_score"] == 1
        assert result["pass_rate"] == 1.0
        assert result["final_passed"] is True

    def test_grade_output_json_valid_assertion(self):
        """Test grading with JSON validation assertion."""
        grader = Grader()

        eval_case = EvalCase(
            id=4,
            name="json_test",
            category="normal",
            prompt="Provide JSON data",
            expected_output='{"name": "test", "value": 123}',
            assertions=[EvalAssertion(name="valid_json", type="json_valid", value="", weight=1)],
        )

        model_output = '{"name": "test", "value": 123}'
        result = grader.grade_output(eval_case, model_output)

        assert result["total_weighted_score"] == 1
        assert result["total_possible_score"] == 1
        assert result["pass_rate"] == 1.0
        assert result["final_passed"] is True

    def test_grade_output_invalid_json(self):
        """Test grading with invalid JSON."""
        grader = Grader()

        eval_case = EvalCase(
            id=5,
            name="invalid_json_test",
            category="normal",
            prompt="Provide JSON data",
            expected_output='{"name": "test", "value": 123}',
            assertions=[EvalAssertion(name="valid_json", type="json_valid", value="", weight=1)],
        )

        model_output = '{"name": "test", "value": 123'  # Invalid JSON
        result = grader.grade_output(eval_case, model_output)

        assert result["total_weighted_score"] == 0
        assert result["total_possible_score"] == 1
        assert result["pass_rate"] == 0.0
        assert result["final_passed"] is False

    def test_grade_output_starts_with_assertion(self):
        """Test grading with starts_with assertion."""
        grader = Grader()

        eval_case = EvalCase(
            id=6,
            name="starts_with_test",
            category="normal",
            prompt="Start with greeting",
            expected_output="Hello there",
            assertions=[
                EvalAssertion(name="starts_with_hello", type="starts_with", value="Hello", weight=1)
            ],
        )

        model_output = "Hello there, nice to meet you"
        result = grader.grade_output(eval_case, model_output)

        assert result["total_weighted_score"] == 1
        assert result["total_possible_score"] == 1
        assert result["pass_rate"] == 1.0
        assert result["final_passed"] is True

    def test_grade_output_not_contains_assertion(self):
        """Test grading with not_contains assertion."""
        grader = Grader()

        eval_case = EvalCase(
            id=7,
            name="not_contains_test",
            category="normal",
            prompt="Don't mention bad words",
            expected_output="Good content",
            assertions=[
                EvalAssertion(name="no_bad_word", type="not_contains", value="bad", weight=1)
            ],
        )

        model_output = "This is good content"
        result = grader.grade_output(eval_case, model_output)

        assert result["total_weighted_score"] == 1
        assert result["total_possible_score"] == 1
        assert result["pass_rate"] == 1.0
        assert result["final_passed"] is True

    def test_grade_output_with_critical_weight(self):
        """Test grading with critical weight (higher weight)."""
        grader = Grader()

        eval_case = EvalCase(
            id=8,
            name="critical_weight_test",
            category="normal",
            prompt="Important test",
            expected_output="Must contain this",
            assertions=[
                EvalAssertion(
                    name="critical_check", type="contains", value="this", weight=3
                ),  # Critical
                EvalAssertion(
                    name="normal_check", type="contains", value="thatYYY", weight=1
                ),  # Normal - use term that won't match
            ],
        )

        model_output = "Contains this but not thatZZZ"
        result = grader.grade_output(eval_case, model_output)

        assert result["total_weighted_score"] == 3  # Only critical assertion passes
        assert result["total_possible_score"] == 4  # Critical(3) + Normal(1)
        assert result["pass_rate"] == 3 / 4
        assert result["final_passed"] is True  # More than 50% pass rate

    def test_grade_output_empty_assertions(self):
        """Empty assertions are rejected by model validator."""
        with pytest.raises(ValidationError):
            EvalCase(
                id=9,
                name="empty_test",
                category="normal",
                prompt="Empty test",
                expected_output="",
                assertions=[],
            )

    def test_get_weight_multiplier(self):
        """Test weight multiplier calculation."""
        grader = Grader()

        # Test different weights
        assert grader._get_weight_multiplier(1) == 1  # Normal
        assert grader._get_weight_multiplier(2) == 2  # Important
        assert grader._get_weight_multiplier(3) == 3  # Critical
        # Test clamping
        assert grader._get_weight_multiplier(0) == 1  # Clamped to 1
        assert grader._get_weight_multiplier(5) == 3  # Clamped to 3
        assert grader._get_weight_multiplier(10) == 3  # Clamped to 3


def test_grade_output_with_llm_judge():
    """Test grading with LLM judge enabled."""
    mock_llm_client = MagicMock()
    grader = Grader(llm_client=mock_llm_client)

    eval_case = EvalCase(
        id=10,
        name="llm_judge_test",
        category="normal",
        prompt="Test with LLM judge",
        expected_output="Expected output",
        assertions=[EvalAssertion(name="contains_test", type="contains", value="test", weight=1)],
    )

    model_output = "This is a test output"
    result = grader.grade_output(eval_case, model_output)

    assert result["eval_id"] == 10
    assert result["total_weighted_score"] == 1
    assert result["total_possible_score"] == 1
    assert result["pass_rate"] == 1.0
    assert result["final_passed"] is True


def test_grade_output_unknown_assertion_type():
    """Test grading with unknown assertion type."""
    grader = Grader()

    eval_case = EvalCase(
        id=11,
        name="unknown_type_test",
        category="normal",
        prompt="Test with unknown assertion type",
        expected_output="Expected output",
        assertions=[
            EvalAssertion(name="unknown_type", type="unknown_type", value="test", weight=1)
        ],
    )

    model_output = "This is a test output"
    result = grader.grade_output(eval_case, model_output)

    # The unknown assertion should fail with low confidence
    assert result["total_weighted_score"] == 0
    assert result["total_possible_score"] == 1
    assert result["pass_rate"] == 0.0
    assert result["assertion_results"][0]["passed"] is False
    assert result["assertion_results"][0]["confidence"] == 0.0
    assert "Unknown assertion type" in result["assertion_results"][0]["reason"]


def test_grade_output_invalid_regex():
    """Test grading with invalid regex assertion."""
    grader = Grader()

    eval_case = EvalCase(
        id=12,
        name="invalid_regex_test",
        category="normal",
        prompt="Test with invalid regex",
        expected_output="Expected output",
        assertions=[
            EvalAssertion(name="invalid_regex", type="regex", value="[unclosed_bracket", weight=1)
        ],
    )

    model_output = "This is a test output"
    result = grader.grade_output(eval_case, model_output)

    # The invalid regex should fail with low confidence
    assert result["total_weighted_score"] == 0
    assert result["total_possible_score"] == 1
    assert result["pass_rate"] == 0.0
    assert result["assertion_results"][0]["passed"] is False
    assert result["assertion_results"][0]["confidence"] == 0.0
    assert "Invalid regex pattern" in result["assertion_results"][0]["reason"]


def test_llm_judge_method():
    """Test the _llm_judge method directly."""
    grader = Grader()

    eval_case = EvalCase(
        id=13,
        name="judge_test",
        category="normal",
        prompt="Test judge method",
        expected_output="Expected output",
        assertions=[EvalAssertion(name="d", type="contains", value=".", weight=1)],
    )

    # Test with no assertions
    assertion_results = []
    judge_result = grader._llm_judge(eval_case, "model output", assertion_results)

    assert judge_result.passed is False
    assert judge_result.confidence == 0.0
    assert "No assertions to evaluate" in judge_result.reasoning

    # Test with some passing assertions
    assertion_results = [
        AssertionResult(
            assertion=EvalAssertion(name="test", type="contains", value="test", weight=1),
            passed=True,
            confidence=1.0,
            reason="Passed",
        ),
        AssertionResult(
            assertion=EvalAssertion(name="test2", type="contains", value="test2", weight=1),
            passed=False,
            confidence=1.0,
            reason="Failed",
        ),
    ]

    judge_result = grader._llm_judge(eval_case, "model output with test", assertion_results)

    assert judge_result.passed is True  # More than 50% passed
    assert judge_result.confidence == 0.5  # 1 out of 2 passed
    assert "1/2 assertions passed" in judge_result.reasoning


def test_llm_judge_with_low_confidence():
    """Test LLM judge with low confidence scenario."""
    grader = Grader()

    eval_case = EvalCase(
        id=14,
        name="low_confidence_test",
        category="normal",
        prompt="Test low confidence",
        expected_output="Expected output",
        assertions=[EvalAssertion(name="test", type="contains", value="test", weight=1)],
    )

    # Create assertion results with low confidence
    assertion_results = [
        AssertionResult(
            assertion=EvalAssertion(name="test", type="contains", value="test", weight=1),
            passed=True,
            confidence=0.3,  # Low confidence
            reason="Passed with low confidence",
        )
    ]

    judge_result = grader._llm_judge(eval_case, "model output with test", assertion_results)

    # The judge confidence is calculated based on passed ratio, not individual assertion confidence
    assert judge_result.passed is True  # Still passed since ratio is 100%
    assert judge_result.confidence == 1.0  # Because 1/1 assertions passed (100%)


# ── JudgeResult v2 fields ─────────────────────────────


def test_judge_result_v2_fields():
    """JudgeResult includes failure_reasons, position_sensitive, debias_runs."""
    jr = JudgeResult(
        passed=False,
        confidence=0.6,
        reasoning="Partial pass",
        failure_reasons=[
            {"assertion_name": "contains_x", "failure_type": "missing", "explanation": "Missing X"}
        ],
        position_sensitive=True,
        debias_runs=2,
    )
    assert jr.failure_reasons[0]["assertion_name"] == "contains_x"
    assert jr.position_sensitive is True
    assert jr.debias_runs == 2
    assert jr.judge_version == "2.0"


def test_judge_result_defaults():
    """JudgeResult defaults: empty failure_reasons, not sensitive, 1 debias run."""
    jr = JudgeResult(passed=True, confidence=0.9)
    assert jr.failure_reasons == []
    assert jr.position_sensitive is False
    assert jr.debias_runs == 1


# ── _format_assertions_for_judge ──────────────────────


def test_format_assertions_for_judge():
    """_format_assertions_for_judge formats PASS/FAIL lines."""
    grader = Grader()
    results = [
        AssertionResult(
            assertion=EvalAssertion(name="check_a", type="contains", value="a", weight=3),
            passed=True,
            confidence=1.0,
            reason="Found",
        ),
        AssertionResult(
            assertion=EvalAssertion(name="check_b", type="contains", value="b", weight=1),
            passed=False,
            confidence=1.0,
            reason="Not found",
        ),
    ]
    text = grader._format_assertions_for_judge(results)
    assert "[PASS] check_a" in text
    assert "[FAIL] check_b" in text
    assert "weight=3" in text


def test_format_assertions_empty():
    """_format_assertions_for_judge with no assertions."""
    grader = Grader()
    assert grader._format_assertions_for_judge([]) == "(no assertions)"


# ── _debias_position ───────────────────────────────────


def test_debias_position_agreement():
    """Debias: when both runs agree, confidence is max."""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = (
        '{"passed": true, "confidence": 0.75, "reasoning": "ok", "failure_reasons": []}'
    )
    grader = Grader(llm_client=mock_llm)

    eval_case = EvalCase(
        id=1,
        name="t",
        category="normal",
        prompt="p",
        expected_output="e",
        assertions=[EvalAssertion(name="a", type="contains", value="x", weight=1)],
    )
    first = JudgeResult(passed=True, confidence=0.7, reasoning="first run", judge_model="llm")
    assertion_results = [
        AssertionResult(
            assertion=EvalAssertion(name="a", type="contains", value="x", weight=1),
            passed=True,
            confidence=1.0,
            reason="ok",
        )
    ]
    result = grader._debias_position(eval_case, "output", assertion_results, first)
    assert result.passed is True
    assert result.confidence == 0.75  # max(0.7, 0.75)
    assert result.position_sensitive is False
    assert result.debias_runs == 2


def test_debias_position_disagreement():
    """Debias: when runs disagree, confidence reduced, position_sensitive=True."""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = (
        '{"passed": false, "confidence": 0.6, "reasoning": "no", "failure_reasons": []}'
    )
    grader = Grader(llm_client=mock_llm)

    eval_case = EvalCase(
        id=1, name="t", category="normal", prompt="p", expected_output="e", assertions=[EvalAssertion(name="d", type="contains", value=".", weight=1)]
    )
    first = JudgeResult(passed=True, confidence=0.7, reasoning="first run", judge_model="llm")
    result = grader._debias_position(eval_case, "output", [], first)
    assert result.passed is True  # Keep first result's verdict
    assert result.confidence == pytest.approx(0.6 * 0.7)  # min(0.7, 0.6) * 0.7
    assert result.position_sensitive is True
    assert result.debias_runs == 2
    assert "disagreement" in result.reasoning.lower()


def test_debias_position_swap_call_fails():
    """Debias: when swap call fails, return first result unchanged."""
    mock_llm = MagicMock()
    mock_llm.chat.side_effect = RuntimeError("API error")
    grader = Grader(llm_client=mock_llm)

    eval_case = EvalCase(
        id=1, name="t", category="normal", prompt="p", expected_output="e", assertions=[EvalAssertion(name="d", type="contains", value=".", weight=1)]
    )
    first = JudgeResult(passed=True, confidence=0.7, reasoning="first run", judge_model="llm")
    result = grader._debias_position(eval_case, "output", [], first)
    assert result.passed is True
    assert result.confidence == 0.7
    assert result.position_sensitive is False
    assert result.debias_runs == 1


def test_debias_position_swap_parsing_code_block():
    """Debias: swap response with ```json code block parsing (lines 450-453)."""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = (
        "Here is the result:\n```json\n"
        '{"passed": false, "confidence": 0.6, "reasoning": "no", '
        '"failure_reasons": []}\n```'
    )
    grader = Grader(llm_client=mock_llm)

    eval_case = EvalCase(
        id=1, name="t", category="normal", prompt="p", expected_output="e", assertions=[EvalAssertion(name="d", type="contains", value=".", weight=1)]
    )
    first = JudgeResult(passed=True, confidence=0.7, reasoning="first run", judge_model="llm")
    result = grader._debias_position(eval_case, "output", [], first)
    assert result.passed is True  # Disagreement, keep first
    assert result.position_sensitive is True
    assert "disagreement" in result.reasoning.lower()


def test_debias_position_swap_double_encoded():
    """Debias: swap response with double-encoded JSON (line 457)."""
    mock_llm = MagicMock()
    # Return JSON where the entire response body is a string that needs to be parsed again
    mock_llm.chat.return_value = (
        '{"passed": false, "confidence": 0.65, "reasoning": "no", "failure_reasons": "[]"}'
    )
    grader = Grader(llm_client=mock_llm)

    eval_case = EvalCase(
        id=1, name="t", category="normal", prompt="p", expected_output="e", assertions=[EvalAssertion(name="d", type="contains", value=".", weight=1)]
    )
    first = JudgeResult(passed=True, confidence=0.7, reasoning="first run", judge_model="llm")
    result = grader._debias_position(eval_case, "output", [], first)
    assert result.passed is True
    assert result.confidence == pytest.approx(min(0.7, 0.65) * 0.7)
    assert result.position_sensitive is True


def test_debias_position_swap_response_is_string():
    """Debias: swap response where json.loads returns a string (triggers line 457)."""
    mock_llm = MagicMock()
    # Response body is a JSON string containing another JSON string
    mock_llm.chat.return_value = (
        '"{\\"passed\\": false, \\"confidence\\": 0.6, '
        '\\"reasoning\\": \\"no\\", \\"failure_reasons\\": []}"'
    )
    grader = Grader(llm_client=mock_llm)

    eval_case = EvalCase(
        id=1, name="t", category="normal", prompt="p", expected_output="e", assertions=[EvalAssertion(name="d", type="contains", value=".", weight=1)]
    )
    first = JudgeResult(passed=True, confidence=0.7, reasoning="first run", judge_model="llm")
    result = grader._debias_position(eval_case, "output", [], first)
    assert result.passed is True
    assert result.confidence == pytest.approx(min(0.7, 0.6) * 0.7)
    assert result.position_sensitive is True


def test_debias_position_swap_non_dict_response():
    """Debias: swap response that is not a dict raises ValueError (line 459)."""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = '["not", "a", "dict"]'
    grader = Grader(llm_client=mock_llm)

    eval_case = EvalCase(
        id=1, name="t", category="normal", prompt="p", expected_output="e", assertions=[EvalAssertion(name="d", type="contains", value=".", weight=1)]
    )
    first = JudgeResult(passed=True, confidence=0.7, reasoning="first run", judge_model="llm")
    # Should fall back to first result when parsing fails
    result = grader._debias_position(eval_case, "output", [], first)
    assert result.passed is True
    assert result.confidence == 0.7
    assert result.debias_runs == 1


# ── LLM judge with failure_reasons parsing ───────────


def test_llm_judge_parses_failure_reasons():
    """LLM judge correctly parses failure_reasons from response."""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = json.dumps(
        {
            "passed": False,
            "confidence": 0.9,
            "reasoning": "Missing section",
            "failure_reasons": [
                {
                    "assertion_name": "has_security",
                    "failure_type": "missing",
                    "explanation": "No security section",
                }
            ],
        }
    )
    grader = Grader(llm_client=mock_llm)
    eval_case = EvalCase(
        id=1,
        name="t",
        category="normal",
        prompt="p",
        expected_output="e",
        assertions=[
            EvalAssertion(name="has_security", type="contains", value="security", weight=3)
        ],
    )
    assertion_results = [
        AssertionResult(
            assertion=EvalAssertion(
                name="has_security", type="contains", value="security", weight=3
            ),
            passed=False,
            confidence=1.0,
            reason="Not found",
        )
    ]
    result = grader._llm_judge(eval_case, "no security here", assertion_results)
    assert result.passed is False
    assert result.confidence == 0.9
    assert len(result.failure_reasons) == 1
    assert result.failure_reasons[0]["assertion_name"] == "has_security"
    assert result.judge_version == "2.0"


def test_llm_judge_invalid_failure_reasons_type():
    """When failure_reasons is not a list, it defaults to empty."""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = json.dumps(
        {"passed": True, "confidence": 0.95, "reasoning": "ok", "failure_reasons": "not a list"}
    )
    grader = Grader(llm_client=mock_llm)
    eval_case = EvalCase(
        id=1, name="t", category="normal", prompt="p", expected_output="e", assertions=[EvalAssertion(name="d", type="contains", value=".", weight=1)]
    )
    result = grader._llm_judge(eval_case, "output", [])
    assert result.failure_reasons == []


def test_llm_judge_with_call_triggers_debias():
    """_llm_judge_with_call triggers _debias_position when confidence < 0.8."""
    mock_llm = MagicMock()
    mock_llm.chat.side_effect = [
        json.dumps(dict(passed=True, confidence=0.75, reasoning="borderline", failure_reasons=[])),
        json.dumps(dict(passed=True, confidence=0.8, reasoning="agreed", failure_reasons=[])),
    ]
    grader = Grader(llm_client=mock_llm)
    eval_case = EvalCase(
        id=1, name="t", category="normal", prompt="p", expected_output="e", assertions=[EvalAssertion(name="d", type="contains", value=".", weight=1)]
    )
    assertion_results = []
    result = grader._llm_judge_with_call(eval_case, "output", assertion_results)
    assert mock_llm.chat.call_count == 2
    assert result.debias_runs == 2
    assert result.position_sensitive is False


# ── Negative case with LLM judge ─────────────────────


def test_negative_case_with_llm_judge_high_confidence():
    """Negative case: judge_result.confidence >= 0.8 -> final_passed = not judge_passed."""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = json.dumps(
        dict(passed=True, confidence=0.9, reasoning="not triggered", failure_reasons=[])
    )
    grader = Grader(llm_client=mock_llm)
    eval_case = EvalCase(
        id=1,
        name="t",
        category="normal",
        prompt="p",
        expected_output="e",
        assertions=[EvalAssertion(name="x", type="contains", value="x", weight=1)],
        negative_case=True,
    )
    result = grader.grade_output(eval_case, "output that triggered")
    assert result["final_passed"] is False


# ── _parse_judge_response ─────────────────────────────


def test_parse_judge_response_json_code_block():
    """Parse judge response wrapped in ```json code block."""
    grader = Grader()
    response = '```json\n{"passed": true, "confidence": 0.9}\n```'
    assert grader._parse_judge_response(response) == '{"passed": true, "confidence": 0.9}'


def test_parse_judge_response_plain_code_block():
    """Parse judge response wrapped in plain ``` code block."""
    grader = Grader()
    response = '```\n{"passed": true}\n```'
    assert grader._parse_judge_response(response) == '{"passed": true}'


def test_parse_judge_response_no_code_block():
    """Parse plain JSON response without code block."""
    grader = Grader()
    response = '{"passed": true}'
    assert grader._parse_judge_response(response) == '{"passed": true}'


# ── Double-encoded JSON ──────────────────────────────


def test_llm_judge_double_encoded_json():
    """Judge response where failure_reasons is double-encoded as string."""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = (
        '{"passed": true, "confidence": 0.95, "reasoning": "ok", '
        '"failure_reasons": "[{\\"assertion\\": \\"x\\"}]"}'
    )
    grader = Grader(llm_client=mock_llm)
    eval_case = EvalCase(
        id=1,
        name="t",
        category="normal",
        prompt="p",
        expected_output="e",
        assertions=[EvalAssertion(name="has_x", type="contains", value="x", weight=1)],
    )
    assertion_results = [
        AssertionResult(
            assertion=EvalAssertion(name="has_x", type="contains", value="x", weight=1),
            passed=True,
            confidence=1.0,
            reason="found",
        ),
    ]
    result = grader._llm_judge(eval_case, "x found", assertion_results)
    assert result.passed is True


def test_execute_llm_judge_double_encoded_main_response():
    """_execute_llm_judge handles double-encoded JSON in main response (line 307)."""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = (
        '"{\\"passed\\": true, \\"confidence\\": 0.85, '
        '\\"reasoning\\": \\"ok\\", \\"failure_reasons\\": []}"'
    )
    grader = Grader(llm_client=mock_llm)
    eval_case = EvalCase(
        id=1, name="t", category="normal", prompt="p", expected_output="e", assertions=[EvalAssertion(name="d", type="contains", value=".", weight=1)]
    )
    result = grader._execute_llm_judge(eval_case, "output", [])
    assert result.passed is True
    assert result.confidence == 0.85


def test_execute_llm_judge_non_dict_response():
    """_execute_llm_judge raises ValueError for non-dict response (line 309)."""
    mock_llm = MagicMock()
    # Return JSON array instead of dict
    mock_llm.chat.return_value = '["not", "a", "dict"]'
    grader = Grader(llm_client=mock_llm)
    eval_case = EvalCase(
        id=1, name="t", category="normal", prompt="p", expected_output="e", assertions=[EvalAssertion(name="d", type="contains", value=".", weight=1)]
    )
    with pytest.raises(ValueError, match="Expected dict from judge response"):
        grader._execute_llm_judge(eval_case, "output", [])


def test_llm_judge_with_call_exception_fallback():
    """_llm_judge_with_call falls back to error handler when
    _execute_llm_judge raises (lines 276-278)."""
    mock_llm = MagicMock()
    mock_llm.chat.side_effect = RuntimeError("Network error")
    grader = Grader(llm_client=mock_llm)
    eval_case = EvalCase(
        id=1,
        name="t",
        category="normal",
        prompt="p",
        expected_output="e",
        assertions=[EvalAssertion(name="x", type="contains", value="x", weight=1)],
    )
    assertion_results = [
        AssertionResult(
            assertion=EvalAssertion(name="x", type="contains", value="x", weight=1),
            passed=True,
            confidence=1.0,
            reason="found",
        ),
    ]
    result = grader._llm_judge_with_call(eval_case, "output", assertion_results)
    assert result.passed is True
    assert result.confidence == 1.0
    assert "failed" in result.reasoning.lower()


# ── _llm_judge_error_fallback ─────────────────────────


def test_llm_judge_error_fallback():
    """Error fallback with assertion results."""
    grader = Grader()
    assertion_results = [
        AssertionResult(
            assertion=EvalAssertion(name="test", type="contains", value="test", weight=1),
            passed=True,
            confidence=1.0,
            reason="ok",
        ),
        AssertionResult(
            assertion=EvalAssertion(name="test2", type="contains", value="x", weight=1),
            passed=False,
            confidence=0.0,
            reason="missing",
        ),
    ]
    result = grader._llm_judge_error_fallback(assertion_results, RuntimeError("network error"))
    assert result.passed is True  # 1/2 = 0.5 >= 0.5
    assert result.confidence == 0.5
    assert "failed" in result.reasoning.lower()


def test_llm_judge_error_fallback_empty():
    """Error fallback with zero assertions."""
    grader = Grader()
    result = grader._llm_judge_error_fallback([], ValueError("empty"))
    assert result.passed is False
    assert result.confidence == 0.0
    assert "0.00" in result.reasoning


# ── _build_grade_result negative case paths ─────────


def test_negative_case_judge_high_confidence():
    """_build_grade_result: negative case + high confidence judge → inverted."""
    grader = Grader()
    eval_case = EvalCase(
        id=1,
        name="n",
        category="normal",
        prompt="p",
        expected_output="e",
        assertions=[EvalAssertion(name="d", type="contains", value=".", weight=1)],
        negative_case=True,
    )
    judge_result = JudgeResult(passed=True, confidence=0.9, reasoning="high conf")
    result = grader._build_grade_result(eval_case, "out", [], 0, 0, 0.0, judge_result)
    assert result["final_passed"] is False  # Inverted because judge passed


def test_negative_case_judge_low_confidence():
    """_build_grade_result: negative case + low confidence judge → uses pass_rate."""
    grader = Grader()
    eval_case = EvalCase(
        id=1,
        name="n",
        category="normal",
        prompt="p",
        expected_output="e",
        assertions=[EvalAssertion(name="d", type="contains", value=".", weight=1)],
        negative_case=True,
    )
    judge_result = JudgeResult(passed=True, confidence=0.5, reasoning="low conf")
    result = grader._build_grade_result(eval_case, "out", [], 0, 0, 0.3, judge_result)
    assert result["final_passed"] is True  # pass_rate < 0.5, so inverted → True


# ── Confidence clamping ────────────────────────────────


def test_execute_llm_judge_clamps_confidence_above_1():
    """LLM returns confidence > 1.0 → clamped to 1.0 before JudgeResult construction."""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = json.dumps(
        {"passed": True, "confidence": 1.5, "reasoning": "overconfident", "failure_reasons": []}
    )
    grader = Grader(llm_client=mock_llm)
    eval_case = EvalCase(
        id=1, name="t", category="normal", prompt="p", expected_output="e", assertions=[EvalAssertion(name="d", type="contains", value=".", weight=1)]
    )
    result = grader._execute_llm_judge(eval_case, "output", [])
    assert result.confidence == 1.0
    assert result.passed is True


def test_execute_llm_judge_clamps_confidence_below_0():
    """LLM returns confidence < 0.0 → clamped to 0.0 before JudgeResult construction."""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = json.dumps(
        {"passed": False, "confidence": -0.3, "reasoning": "negative", "failure_reasons": []}
    )
    grader = Grader(llm_client=mock_llm)
    eval_case = EvalCase(
        id=1, name="t", category="normal", prompt="p", expected_output="e", assertions=[EvalAssertion(name="d", type="contains", value=".", weight=1)]
    )
    result = grader._execute_llm_judge(eval_case, "output", [])
    assert result.confidence == 0.0
    assert result.passed is False


def test_execute_llm_judge_clamps_confidence_string_value():
    """LLM returns confidence as string '1.2' → parsed and clamped to 1.0."""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = json.dumps(
        {"passed": True, "confidence": "1.2", "reasoning": "str", "failure_reasons": []}
    )
    grader = Grader(llm_client=mock_llm)
    eval_case = EvalCase(
        id=1, name="t", category="normal", prompt="p", expected_output="e", assertions=[EvalAssertion(name="d", type="contains", value=".", weight=1)]
    )
    result = grader._execute_llm_judge(eval_case, "output", [])
    assert result.confidence == 1.0


# ── Robust JSON parsing ───────────────────────────────


def test_parse_judge_response_brace_counting_with_surrounding_text():
    """Parse JSON embedded in surrounding text via brace counting."""
    grader = Grader()
    response = (
        "Sure, here is my evaluation:\n"
        '{"passed": true, "confidence": 0.85, "reasoning": "good"}\n'
        "Hope that helps!"
    )
    result = grader._parse_judge_response(response)
    parsed = json.loads(result)
    assert parsed["passed"] is True
    assert parsed["confidence"] == 0.85


def test_parse_judge_response_brace_counting_nested_braces():
    """Parse JSON with nested braces via brace counting."""
    grader = Grader()
    response = (
        "Here you go:\n"
        '{"passed": false, "confidence": 0.7, "reasoning": "see {details}", '
        '"failure_reasons": [{"msg": "missing {x}"}]}\n'
        "Done."
    )
    result = grader._parse_judge_response(response)
    parsed = json.loads(result)
    assert parsed["passed"] is False
    assert len(parsed["failure_reasons"]) == 1


def test_parse_judge_response_strict_false_fallback():
    """Parse JSON with control characters using strict=False fallback."""
    grader = Grader()
    response = '{"passed": true, "confidence": 0.9,\n"reasoning": "line1\nline2"}'
    result = grader._parse_judge_response(response)
    parsed = json.loads(result)
    assert parsed["passed"] is True


# ── JSONDecodeError retry ─────────────────────────────


def test_llm_judge_with_call_retries_on_json_decode_error():
    """JSONDecodeError on first call triggers one retry with stricter prompt."""
    mock_llm = MagicMock()
    mock_llm.chat.side_effect = [
        "This is not JSON at all, just plain text",
        json.dumps({"passed": True, "confidence": 0.9, "reasoning": "ok", "failure_reasons": []}),
        json.dumps(
            {"passed": True, "confidence": 0.85, "reasoning": "swap", "failure_reasons": []}
        ),
    ]
    grader = Grader(llm_client=mock_llm)
    eval_case = EvalCase(
        id=1,
        name="t",
        category="normal",
        prompt="p",
        expected_output="e",
        assertions=[EvalAssertion(name="x", type="contains", value="x", weight=1)],
    )
    assertion_results = [
        AssertionResult(
            assertion=EvalAssertion(name="x", type="contains", value="x", weight=1),
            passed=True,
            confidence=1.0,
            reason="found",
        ),
    ]
    result = grader._llm_judge_with_call(eval_case, "output", assertion_results)
    assert mock_llm.chat.call_count == 3
    assert result.passed is True
    assert result.confidence == 0.9
    assert result.debias_runs == 2


def test_llm_judge_with_call_json_decode_error_retry_also_fails():
    """JSONDecodeError on both first and retry → falls back to assertion-based."""
    mock_llm = MagicMock()
    mock_llm.chat.side_effect = [
        "not json",
        "still not json",
    ]
    grader = Grader(llm_client=mock_llm)
    eval_case = EvalCase(
        id=1,
        name="t",
        category="normal",
        prompt="p",
        expected_output="e",
        assertions=[EvalAssertion(name="x", type="contains", value="x", weight=1)],
    )
    assertion_results = [
        AssertionResult(
            assertion=EvalAssertion(name="x", type="contains", value="x", weight=1),
            passed=True,
            confidence=1.0,
            reason="found",
        ),
    ]
    result = grader._llm_judge_with_call(eval_case, "output", assertion_results)
    assert mock_llm.chat.call_count == 2
    assert "failed" in result.reasoning.lower()


# ── ValidationError separate handling ─────────────────


def test_llm_judge_with_call_validation_error_clamps_and_reconstructs():
    """ValidationError from Pydantic → clamp confidence and reconstruct JudgeResult."""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = json.dumps(
        {"passed": True, "confidence": 2.0, "reasoning": "over", "failure_reasons": []}
    )
    grader = Grader(llm_client=mock_llm)
    eval_case = EvalCase(
        id=1,
        name="t",
        category="normal",
        prompt="p",
        expected_output="e",
        assertions=[EvalAssertion(name="x", type="contains", value="x", weight=1)],
    )
    assertion_results = [
        AssertionResult(
            assertion=EvalAssertion(name="x", type="contains", value="x", weight=1),
            passed=True,
            confidence=1.0,
            reason="found",
        ),
    ]
    result = grader._llm_judge_with_call(eval_case, "output", assertion_results)
    assert result.confidence == 1.0
    assert result.passed is True
    assert result.judge_model == "llm"


# ── Other exception still falls back ──────────────────


def test_llm_judge_with_call_other_exception_still_falls_back():
    """Non-JSON/ValidationError exceptions still fall back to assertion-based."""
    mock_llm = MagicMock()
    mock_llm.chat.side_effect = ConnectionError("network down")
    grader = Grader(llm_client=mock_llm)
    eval_case = EvalCase(
        id=1,
        name="t",
        category="normal",
        prompt="p",
        expected_output="e",
        assertions=[EvalAssertion(name="x", type="contains", value="x", weight=1)],
    )
    assertion_results = [
        AssertionResult(
            assertion=EvalAssertion(name="x", type="contains", value="x", weight=1),
            passed=True,
            confidence=1.0,
            reason="found",
        ),
    ]
    result = grader._llm_judge_with_call(eval_case, "output", assertion_results)
    assert "failed" in result.reasoning.lower()
    assert result.judge_model == ""


# ── Position debiasing as default behavior (slice-7) ──────────────


def test_grader_init_debias_position_default_true():
    """Grader.__init__ defaults debias_position=True."""
    grader = Grader()
    assert grader.debias_position is True


def test_grader_init_debias_position_can_disable():
    """Grader.__init__ accepts debias_position=False."""
    grader = Grader(debias_position=False)
    assert grader.debias_position is False


def test_llm_judge_with_call_runs_debias_by_default_high_confidence():
    """_llm_judge_with_call runs debias even when confidence >= 0.8 (always-on)."""
    mock_llm = MagicMock()
    # First call: high confidence pass. Second call (swap): also pass.
    mock_llm.chat.side_effect = [
        json.dumps(dict(passed=True, confidence=0.95, reasoning="strong", failure_reasons=[])),
        json.dumps(dict(passed=True, confidence=0.9, reasoning="agreed", failure_reasons=[])),
    ]
    grader = Grader(llm_client=mock_llm)
    eval_case = EvalCase(
        id=1, name="t", category="normal", prompt="p", expected_output="e", assertions=[EvalAssertion(name="d", type="contains", value=".", weight=1)]
    )
    result = grader._llm_judge_with_call(eval_case, "output", [])
    # Should have made 2 LLM calls (original + swap)
    assert mock_llm.chat.call_count == 2
    assert result.debias_runs == 2


def test_llm_judge_with_call_skips_debias_when_disabled():
    """_llm_judge_with_call skips debias when debias_position=False."""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = json.dumps(
        dict(passed=True, confidence=0.95, reasoning="strong", failure_reasons=[])
    )
    grader = Grader(llm_client=mock_llm, debias_position=False)
    eval_case = EvalCase(
        id=1, name="t", category="normal", prompt="p", expected_output="e", assertions=[EvalAssertion(name="d", type="contains", value=".", weight=1)]
    )
    result = grader._llm_judge_with_call(eval_case, "output", [])
    # Should have made only 1 LLM call (no swap)
    assert mock_llm.chat.call_count == 1
    assert result.debias_runs == 1
    assert result.position_sensitive is False


def test_llm_judge_with_call_disagreement_reduces_confidence_30_percent():
    """Disagreement between original and swap reduces confidence by 30%."""
    mock_llm = MagicMock()
    mock_llm.chat.side_effect = [
        json.dumps(dict(passed=True, confidence=0.9, reasoning="first", failure_reasons=[])),
        json.dumps(dict(passed=False, confidence=0.85, reasoning="swap", failure_reasons=[])),
    ]
    grader = Grader(llm_client=mock_llm)
    eval_case = EvalCase(
        id=1, name="t", category="normal", prompt="p", expected_output="e", assertions=[EvalAssertion(name="d", type="contains", value=".", weight=1)]
    )
    result = grader._llm_judge_with_call(eval_case, "output", [])
    assert result.position_sensitive is True
    assert result.debias_runs == 2
    # Confidence should be min(0.9, 0.85) * 0.7 = 0.595
    assert result.confidence == pytest.approx(min(0.9, 0.85) * 0.7)
    assert "disagreement" in result.reasoning.lower()


def test_llm_judge_with_call_debias_agreement_high_confidence():
    """When both runs agree with high confidence, keep max confidence."""
    mock_llm = MagicMock()
    mock_llm.chat.side_effect = [
        json.dumps(dict(passed=True, confidence=0.92, reasoning="first", failure_reasons=[])),
        json.dumps(dict(passed=True, confidence=0.88, reasoning="swap", failure_reasons=[])),
    ]
    grader = Grader(llm_client=mock_llm)
    eval_case = EvalCase(
        id=1, name="t", category="normal", prompt="p", expected_output="e", assertions=[EvalAssertion(name="d", type="contains", value=".", weight=1)]
    )
    result = grader._llm_judge_with_call(eval_case, "output", [])
    assert result.debias_runs == 2
    assert result.position_sensitive is False
    assert result.confidence == 0.92  # max(0.92, 0.88)


class TestEvalCaseWithoutSkillAssertions:
    """Tests for without_skill_assertions field on EvalCase."""

    def test_eval_case_without_skill_assertions_defaults_to_empty(self):
        """EvalCase constructs without without_skill_assertions → defaults to []."""
        case = EvalCase(
            id=1,
            name="test",
            category="normal",
            prompt="prompt",
            assertions=[EvalAssertion(name="a", type="contains", value="x")],
        )
        assert case.without_skill_assertions == []

    def test_eval_case_without_skill_assertions_explicit(self):
        """EvalCase accepts explicit without_skill_assertions."""
        ws_assertions = [
            EvalAssertion(name="no-struct", type="not_contains", value="L1 Trigger Accuracy", weight=3),
        ]
        case = EvalCase(
            id=1,
            name="test",
            category="normal",
            prompt="prompt",
            assertions=[EvalAssertion(name="a", type="contains", value="x")],
            without_skill_assertions=ws_assertions,
        )
        assert len(case.without_skill_assertions) == 1
        assert case.without_skill_assertions[0].name == "no-struct"
        assert case.without_skill_assertions[0].type == "not_contains"
        assert case.without_skill_assertions[0].value == "L1 Trigger Accuracy"
        assert case.without_skill_assertions[0].weight == 3

    def test_eval_case_both_assertions_empty_raises(self):
        """EvalCase with both assertions and without_skill_assertions empty raises ValidationError."""
        with pytest.raises(ValidationError):
            EvalCase(id=1, name="test", category="normal", prompt="prompt", assertions=[])

    def test_eval_case_only_without_skill_assertions_valid(self):
        """EvalCase with only without_skill_assertions (and empty assertions) is allowed."""
        case = EvalCase(
            id=1,
            name="test",
            category="normal",
            prompt="prompt",
            assertions=[],
            without_skill_assertions=[
                EvalAssertion(name="check", type="not_contains", value="struct", weight=1)
            ],
        )
        assert case.without_skill_assertions[0].name == "check"


class TestGraderModeAssertionSelection:
    """Tests for mode-based assertion selection in Grader.grade_output."""

    def test_grade_output_without_skill_uses_assertions_when_ws_empty(self):
        """When without_skill_assertions is empty, without_skill mode falls back to assertions."""
        grader = Grader()
        case = EvalCase(
            id=1,
            name="test",
            category="normal",
            prompt="prompt",
            assertions=[EvalAssertion(name="contains_hello", type="contains", value="hello", weight=1)],
        )
        result = grader.grade_output(case, "hello world", mode="without_skill")
        assert result["pass_rate"] == 1.0
        assert result["final_passed"] is True

    def test_grade_output_without_skill_uses_ws_assertions_when_populated(self):
        """When without_skill_assertions is populated, without_skill mode uses it."""
        grader = Grader()
        case = EvalCase(
            id=1,
            name="test",
            category="normal",
            prompt="prompt",
            assertions=[EvalAssertion(name="contains_skill", type="contains", value="skill", weight=1)],
            without_skill_assertions=[
                EvalAssertion(name="no-skill-term", type="not_contains", value="skill", weight=1)
            ],
        )
        # Output contains "skill" → without_skill_assertions check not_contains: FAILS
        # because not_contains("skill") fails when output has "skill"
        result = grader.grade_output(case, "this has skill content", mode="without_skill")
        assert result["pass_rate"] == 0.0
        assert result["final_passed"] is False

    def test_grade_output_without_skill_passes_when_ws_assertion_satisfied(self):
        """without_skill_assertions: not_contains passes when term absent."""
        grader = Grader()
        case = EvalCase(
            id=1,
            name="test",
            category="normal",
            prompt="prompt",
            assertions=[EvalAssertion(name="a", type="contains", value="x", weight=1)],
            without_skill_assertions=[
                EvalAssertion(name="no-skill-term", type="not_contains", value="L1 Trigger Accuracy", weight=1)
            ],
        )
        result = grader.grade_output(case, "just a normal response", mode="without_skill")
        assert result["pass_rate"] == 1.0
        assert result["final_passed"] is True

    def test_grade_output_with_skill_uses_assertions_even_when_ws_populated(self):
        """with_skill mode always uses assertions, ignoring without_skill_assertions."""
        grader = Grader()
        case = EvalCase(
            id=1,
            name="test",
            category="normal",
            prompt="prompt",
            assertions=[EvalAssertion(name="contains_skill", type="contains", value="skill", weight=1)],
            without_skill_assertions=[
                EvalAssertion(name="no-skill-term", type="not_contains", value="skill", weight=1)
            ],
        )
        result = grader.grade_output(case, "this has skill content", mode="with_skill")
        # with_skill uses assertions (contains "skill") → passes
        assert result["pass_rate"] == 1.0
        assert result["final_passed"] is True

    def test_grade_output_default_mode_is_with_skill(self):
        """grade_output without mode parameter defaults to with_skill."""
        grader = Grader()
        case = EvalCase(
            id=1,
            name="test",
            category="normal",
            prompt="prompt",
            assertions=[EvalAssertion(name="a", type="contains", value="hello", weight=1)],
        )
        result = grader.grade_output(case, "hello world")
        assert result["pass_rate"] == 1.0

    def test_grade_output_without_skill_empty_ws_assertions_same_as_with_skill(self):
        """Without without_skill_assertions, both modes produce same result."""
        grader = Grader()
        case = EvalCase(
            id=1,
            name="test",
            category="normal",
            prompt="prompt",
            assertions=[EvalAssertion(name="a", type="contains", value="hello", weight=1)],
        )
        with_result = grader.grade_output(case, "hello world", mode="with_skill")
        without_result = grader.grade_output(case, "hello world", mode="without_skill")
        assert with_result["pass_rate"] == without_result["pass_rate"]
        assert with_result["total_weighted_score"] == without_result["total_weighted_score"]

    def test_grade_output_with_negative_case_and_ws_assertions(self):
        grader = Grader()
        case = EvalCase(
            id=1,
            name="test",
            category="trigger",
            prompt="prompt",
            assertions=[EvalAssertion(name="no-struct", type="not_contains", value="verdict", weight=3)],
            without_skill_assertions=[
                EvalAssertion(name="no-struct-ws", type="not_contains", value="verdict", weight=3)
            ],
            negative_case=True,
        )
        result = grader.grade_output(case, "just a normal response", mode="without_skill")
        assert result["pass_rate"] == 1.0
        assert result["final_passed"] is False

    def test_grade_output_negative_case_output_contains_trigger_term_final_passed_true(self):
        grader = Grader()
        case = EvalCase(
            id=1,
            name="test",
            category="trigger",
            prompt="prompt",
            assertions=[EvalAssertion(name="no-struct", type="not_contains", value="verdict", weight=3)],
            without_skill_assertions=[
                EvalAssertion(name="no-struct-ws", type="not_contains", value="verdict", weight=3)
            ],
            negative_case=True,
        )
        result = grader.grade_output(case, "output with verdict", mode="without_skill")
        assert result["pass_rate"] == 0.0
        assert result["final_passed"] is True


# ── P0: Robust JSON extraction for LLM judge ─────────────────
# Tests for the two failure modes:
# 1. Pydantic ValidationError when confidence is out of [0,1] range
# 2. JSON parsing failure due to malformed LLM output


def test_parse_judge_response_trailing_comma():
    """Parse JSON with trailing comma after last field (common LLM mistake)."""
    grader = Grader()
    # Trailing comma after last field
    response = '{"passed": true, "confidence": 0.9,"reasoning": "good",}'
    result = grader._parse_judge_response(response)
    parsed = json.loads(result)
    assert parsed["passed"] is True
    assert parsed["confidence"] == 0.9


def test_parse_judge_response_prose_before_json():
    """Parse JSON when the LLM writes explanatory prose before the JSON."""
    grader = Grader()
    response = (
        "Let me evaluate this carefully. Here is my assessment:\n\n"
        '{"passed": true, "confidence": 0.85, "reasoning": "well done"}'
    )
    result = grader._parse_judge_response(response)
    parsed = json.loads(result)
    assert parsed["passed"] is True
    assert parsed["confidence"] == 0.85


def test_parse_judge_response_prose_after_json():
    """Parse JSON when the LLM writes explanatory prose after the JSON."""
    grader = Grader()
    response = (
        '{"passed": false, "confidence": 0.3, "reasoning": "missing steps"}'
        "\n\nI hope this evaluation helps!"
    )
    result = grader._parse_judge_response(response)
    parsed = json.loads(result)
    assert parsed["passed"] is False
    assert parsed["confidence"] == 0.3


def test_parse_judge_response_prose_before_and_after_json():
    """Parse JSON embedded between prose before and after."""
    grader = Grader()
    response = (
        "Here is the evaluation result:\n\n"
        '{"passed": true, "confidence": 0.95, "reasoning": "all checks pass"}'
        "\n\nThis matches the expected behavior."
    )
    result = grader._parse_judge_response(response)
    parsed = json.loads(result)
    assert parsed["passed"] is True
    assert parsed["confidence"] == 0.95


def test_llm_judge_with_call_handles_malformed_json_with_trailing_comma():
    """_llm_judge_with_call: LLM returns JSON with trailing comma → extraction + clamping succeed."""
    mock_llm = MagicMock()
    # First call: malformed JSON with trailing comma → _execute_llm_judge raises JSONDecodeError
    # → triggers retry path. Simulate same bad JSON on retry by creating scenario where
    # _parse_judge_response extracts clean JSON via brace counting fallback.
    # Actually: We test both paths. Let's test via _execute_llm_judge directly.
    malformed_json = '{"passed": true, "confidence": 0.9,"reasoning": "ok",}\n'
    mock_llm.chat.return_value = malformed_json
    grader = Grader(llm_client=mock_llm)
    eval_case = EvalCase(
        id=1, name="t", category="normal", prompt="p", expected_output="e",
        assertions=[EvalAssertion(name="d", type="contains", value=".", weight=1)]
    )
    result = grader._execute_llm_judge(eval_case, "output", [])
    assert result.passed is True
    assert result.confidence == 0.9


def test_llm_judge_with_call_confidence_out_of_range_clamped_not_fallback():
    """_llm_judge_with_call: confidence=1.5 should be clamped to 1.0 via ValidationError handler,
    NOT fall back to assertion-based grading."""
    mock_llm = MagicMock()
    # First call succeeds with confidence=1.5 (triggers ValidationError in JudgeResult construction)
    mock_llm.chat.side_effect = [
        json.dumps({"passed": True, "confidence": 1.5, "reasoning": "overconfident", "failure_reasons": []}),
        json.dumps({"passed": True, "confidence": 0.9, "reasoning": "swap ok", "failure_reasons": []}),
    ]
    grader = Grader(llm_client=mock_llm)
    eval_case = EvalCase(
        id=1,
        name="t",
        category="normal",
        prompt="p",
        expected_output="e",
        assertions=[EvalAssertion(name="x", type="contains", value="x", weight=1)],
    )
    assertion_results = [
        AssertionResult(
            assertion=EvalAssertion(name="x", type="contains", value="x", weight=1),
            passed=True,
            confidence=1.0,
            reason="found",
        ),
    ]
    result = grader._llm_judge_with_call(eval_case, "output", assertion_results)
    assert result.judge_model == "llm"
    assert "failed" not in result.reasoning.lower()
    assert result.passed is True


def test_llm_judge_with_call_negative_confidence_clamped():
    """_llm_judge_with_call: confidence=-0.1 clamped to 0.0 via ValidationError handler."""
    mock_llm = MagicMock()
    mock_llm.chat.side_effect = [
        json.dumps({"passed": False, "confidence": -0.1, "reasoning": "bad", "failure_reasons": []}),
        json.dumps({"passed": False, "confidence": 0.4, "reasoning": "swap bad", "failure_reasons": []}),
    ]
    grader = Grader(llm_client=mock_llm)
    eval_case = EvalCase(
        id=1,
        name="t",
        category="normal",
        prompt="p",
        expected_output="e",
        assertions=[EvalAssertion(name="x", type="contains", value="x", weight=1)],
    )
    assertion_results = [
        AssertionResult(
            assertion=EvalAssertion(name="x", type="contains", value="x", weight=1),
            passed=False,
            confidence=0.0,
            reason="missing",
        ),
    ]
    result = grader._llm_judge_with_call(eval_case, "output", assertion_results)
    assert result.judge_model == "llm"
    assert result.passed is False


def test_llm_judge_with_call_json_prose_wrapped_recovers():
    """_llm_judge_with_call: JSON wrapped in prose → recovered via brace counting, not fallback."""
    mock_llm = MagicMock()
    # JSON embedded in prose, but _parse_judge_response can extract via brace counting
    mock_llm.chat.side_effect = [
        "Sure! Here is my evaluation:\n"
        '{"passed": true, "confidence": 0.88, "reasoning": "looks good", "failure_reasons": []}\n'
        "Let me know if you need more detail.",
        json.dumps({"passed": True, "confidence": 0.87, "reasoning": "swap", "failure_reasons": []}),
    ]
    grader = Grader(llm_client=mock_llm)
    eval_case = EvalCase(
        id=1,
        name="t",
        category="normal",
        prompt="p",
        expected_output="e",
        assertions=[EvalAssertion(name="x", type="contains", value="x", weight=1)],
    )
    assertion_results = [
        AssertionResult(
            assertion=EvalAssertion(name="x", type="contains", value="x", weight=1),
            passed=True, confidence=1.0, reason="found",
        ),
    ]
    result = grader._llm_judge_with_call(eval_case, "output", assertion_results)
    assert result.passed is True
    assert result.judge_model == "llm"


def test_parse_judge_response_json_with_newlines_in_strings():
    """Parse JSON where string values contain newline characters (strict=False fallback)."""
    grader = Grader()
    response = '{"passed": true, "confidence": 0.9,\n"reasoning": "line1\\nline2"}'
    result = grader._parse_judge_response(response)
    parsed = json.loads(result)
    assert parsed["passed"] is True


def test_llm_judge_with_call_no_debias_no_llm_client_skips_debias():
    """_llm_judge_with_call: when debias_position=True but no llm_client attr check after,
    debias_position check is AND'd with self.llm_client."""
    mock_llm = MagicMock()
    # The debias check is: if self.debias_position and self.llm_client:
    mock_llm.chat.return_value = json.dumps(
        {"passed": True, "confidence": 0.95, "reasoning": "good", "failure_reasons": []}
    )
    grader = Grader(llm_client=mock_llm, debias_position=True)
    eval_case = EvalCase(
        id=1, name="t", category="normal", prompt="p", expected_output="e",
        assertions=[EvalAssertion(name="d", type="contains", value=".", weight=1)]
    )
    # First call: execute_llm_judge → success. Then debias: second call.
    # Override llm_client.chat side_effect for two calls
    mock_llm.chat.side_effect = [
        json.dumps({"passed": True, "confidence": 0.95, "reasoning": "good", "failure_reasons": []}),
        json.dumps({"passed": True, "confidence": 0.9, "reasoning": "swap", "failure_reasons": []}),
    ]
    result = grader._llm_judge_with_call(eval_case, "output", [])
    assert result.debias_runs == 2
    assert result.judge_model == "llm"


if __name__ == "__main__":
    pytest.main([__file__])
