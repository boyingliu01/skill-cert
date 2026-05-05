"""TDD tests for P0 fix: _parse_evals_response, _parse_review_response, eval case normalization."""

import pytest
from engine.testgen import EvalGenerator


class TestParseEvalsResponseMarkdownFences:
    """Test that _parse_evals_response strips markdown JSON fences."""

    def setup_method(self):
        self.gen = EvalGenerator()

    def test_strips_markdown_json_fence(self):
        _response = """Here are the evals:
```json
{
  "eval_cases": [
    {
      "id": 1,
      "name": "test-eval",
      "category": "normal",
      "input": "test input",
      "assertions": [{"type": "contains", "value": "test", "weight": 1}]
    }
  ]
}
```
"""
        result = self.gen._parse_evals_response(_response)
        assert "eval_cases" in result or "evals" in result

    def test_strips_json_only_fence(self):
        _response = '''```json
{"eval_cases": [{"id": 1, "name": "t", "category": "n", "input": "x", "assertions": [{"type": "contains", "value": "x", "weight": 1}]}]}
```'''
        result = self.gen._parse_evals_response(_response)
        assert result is not None

    def test_handles_plain_json(self):
        _response = '{"evals": [{"id": 1, "name": "t", "category": "n", "input": "x", "assertions": [{"type": "contains", "value": "x", "weight": 1}]}]}'
        result = self.gen._parse_evals_response(_response)
        assert result is not None

    def test_handles_multiple_fences(self):
        """When response contains multiple fence blocks, extract first valid one."""
        _response = """First block:
```json
{"eval_cases": []}
```
Second block with data:
```json
{"eval_cases": [{"id": 1, "name": "t", "category": "n", "input": "x", "assertions": [{"type": "contains", "value": "x", "weight": 1}]}]}
```
"""
        result = self.gen._parse_evals_response(_response)
        assert result is not None


class TestParseEvalsResponseSchemaValidation:
    """Test that parsed eval cases have correct assertion structure."""

    def setup_method(self):
        self.gen = EvalGenerator()

    def test_rejects_malformed_assertion_type_flat_fields(self):
        _response = '{"eval_cases": [{"id": 1, "name": "t", "category": "n", "input": "x", "assertion_type": "contains", "assertion_value": "x"}]}'
        result = self.gen._parse_evals_response(_response)
        cases = result.get("eval_cases") or result.get("evals", [])
        case = cases[0]
        # Must have assertions array after normalization
        assert "assertions" in case
        assert isinstance(case["assertions"], list)

    def test_normalizes_flat_assertion_to_array(self):
        _response = '{"eval_cases": [{"id": 1, "name": "t", "category": "n", "input": "x", "assertion_type": "contains", "assertion_value": "x", "assertion_weight": 2}]}'
        result = self.gen._parse_evals_response(_response)
        cases = result.get("eval_cases") or result.get("evals", [])
        case = cases[0]
        assert len(case["assertions"]) == 1
        assert case["assertions"][0]["type"] == "contains"
        assert case["assertions"][0]["value"] == "x"
        assert case["assertions"][0]["weight"] == 2

    def test_passes_through_correct_assertions(self):
        _response = '{"eval_cases": [{"id": 1, "name": "t", "category": "n", "input": "x", "assertions": [{"type": "contains", "value": "x", "weight": 1}]}]}'
        result = self.gen._parse_evals_response(_response)
        cases = result.get("eval_cases") or result.get("evals", [])
        assert len(cases[0]["assertions"]) == 1

    def test_missing_input_fallback_to_prompt(self):
        _response = '{"eval_cases": [{"id": 1, "name": "t", "category": "n", "prompt": "test prompt", "assertions": []}]}'
        result = self.gen._parse_evals_response(_response)
        cases = result.get("eval_cases") or result.get("evals", [])
        assert cases[0].get("input") == "test prompt"


class TestParseReviewResponse:
    """Test that review response parsing handles malformed JSON."""

    def setup_method(self):
        self.gen = EvalGenerator()

    def test_strips_markdown_fence(self):
        _response = """Here's the review:
```json
{"coverage": 0.85, "gaps": ["missing step 3"], "needs_improvement": true}
```"""
        result = self.gen._parse_review_response(_response, 0.5)
        assert "gaps" in result
        assert "missing step 3" in result["gaps"]

    def test_handles_plain_json(self):
        _response = '{"coverage": 0.90, "gaps": [], "needs_improvement": false}'
        result = self.gen._parse_review_response(_response, 0.5)
        assert result["coverage"] == 0.90
        assert result["needs_improvement"] is False

    def test_fallback_on_invalid_json(self):
        _response = "This is not JSON at all"
        result = self.gen._parse_review_response(_response, 0.5)
        assert result["coverage"] == 0.5
        assert "Could not parse review response" in result["gaps"]
        assert result["needs_improvement"] is True

    def test_preserves_current_coverage_when_missing_field(self):
        _response = '{"gaps": ["something missing"]}'
        result = self.gen._parse_review_response(_response, 0.75)
        assert result["coverage"] == 0.75
