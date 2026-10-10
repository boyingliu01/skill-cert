"""Tests for the engine-wide tolerant JSON extraction chain (engine/json_extract.py)."""

from engine.json_extract import (
    balanced_brace_extract,
    extract_json,
    largest_first_extract,
    repair_json_trailing_commas,
    strip_markdown_fences,
)


class TestExtractJson:
    """4-level fallback JSON extraction."""

    def test_strategy1_clean_json(self):
        """Strategy 1: Clean JSON passes through directly."""
        result = extract_json('{"eval_cases": [{"id": 1}]}')
        assert result == {"eval_cases": [{"id": 1}]}

    def test_strategy1_markdown_fenced_json(self):
        """Strategy 1: JSON inside ```json fence."""
        response = '```json\n{"eval_cases": [{"id": 1}]}\n```'
        result = extract_json(response)
        assert result == {"eval_cases": [{"id": 1}]}

    def test_strategy1_json_with_prose_before(self):
        """Strategy 1: JSON with prose before it."""
        response = 'Here are the evals:\n{"eval_cases": [{"id": 1}]}'
        result = extract_json(response)
        assert result == {"eval_cases": [{"id": 1}]}

    def test_strategy2_balanced_brace_extraction(self):
        """Strategy 2: Extract outermost balanced braces when first{last} fails."""
        # Multiple JSON objects — first{ to last} would span across them
        response = '{"a": 1} some text {"b": 2}'
        result = extract_json(response)
        # Should extract the first valid JSON object
        assert isinstance(result, dict)
        assert "a" in result or "b" in result

    def test_strategy2_nested_braces(self):
        """Strategy 2: Handles nested braces correctly."""
        response = 'prefix {"eval_cases": [{"id": 1, "assertions": [{"type": "contains"}]}]} suffix'
        result = extract_json(response)
        assert result is not None
        assert result["eval_cases"][0]["id"] == 1

    def test_strategy3_largest_first(self):
        """Strategy 3: Try largest brace block first when smaller ones fail."""
        # Outer JSON is valid but contains inner fragments that could confuse simpler parsers
        response = 'noise {broken} {"eval_cases": [{"id": 1}]}'
        result = extract_json(response)
        assert isinstance(result, dict)
        assert "eval_cases" in result

    def test_strategy4_strict_false(self):
        """Strategy 4: json.loads with strict=False handles control chars."""
        response = '{"eval_cases": [{"id": 1, "name": "test\x01value"}]}'
        result = extract_json(response)
        assert isinstance(result, dict)

    def test_all_strategies_fail_returns_none(self):
        """When all strategies fail, returns None."""
        assert extract_json("no json here at all") is None

    def test_empty_string_returns_none(self):
        """Empty string returns None."""
        assert extract_json("") is None

    def test_strategy2_prose_with_multiple_brace_groups(self):
        """Strategy 2: Picks first valid balanced JSON from multiple groups."""
        response = 'text {invalid stuff} more text {"valid": true} end'
        result = extract_json(response)
        assert isinstance(result, dict)

    def test_json_with_array_at_top_level_not_extracted(self):
        """Non-object JSON (arrays) — should still extract if wrapped in object."""
        assert extract_json('{"eval_cases": [1, 2, 3]}') == {"eval_cases": [1, 2, 3]}

    def test_braces_inside_strings_are_not_boundaries(self):
        """A brace in a string value must not break brace counting."""
        response = 'noise {"note": "a } brace"} tail'
        assert extract_json(response) == {"note": "a } brace"}


class TestTrailingCommaRepair:
    def test_trailing_comma_repair_succeeds(self):
        """Trailing comma in JSON object is repaired transparently."""
        result = extract_json(
            '{\n  "eval_cases": [{"id": 1, "name": "test",},\n  {"id": 2, "name": "test2",}],\n}'
        )
        assert result is not None
        assert result["eval_cases"][0]["id"] == 1
        assert result["eval_cases"][1]["id"] == 2

    def test_trailing_comma_in_nested_json(self):
        """Trailing commas in nested JSON objects and arrays are repaired."""
        result = extract_json(
            '{"eval_cases": [{"id": 1, "assertions": [{"type": "contains", "value": "x",},],},]}'
        )
        assert result is not None
        assert result["eval_cases"][0]["id"] == 1
        assert len(result["eval_cases"][0]["assertions"]) == 1

    def test_repair_returns_none_for_unrepairable_text(self):
        assert repair_json_trailing_commas("not json at all") is None

    def test_repair_returns_the_repaired_document(self):
        assert repair_json_trailing_commas('{"a": 1,}') == '{"a": 1}'


class TestFenceStripping:
    def test_strip_markdown_fences_removes_json_and_plain_fences(self):
        text = 'preamble\n```json\n{"a": 1}\n```\nepilogue'
        stripped = strip_markdown_fences(text)
        assert stripped == 'preamble\n{"a": 1}\nepilogue'

    def test_balanced_brace_extract_skips_invalid_group(self):
        assert balanced_brace_extract('{broken} {"a": 1}') == {"a": 1}

    def test_largest_first_extract_prefers_the_biggest_valid_block(self):
        response = '{"a": 1} {"outer": {"inner": 2}}'
        assert largest_first_extract(response) == {"outer": {"inner": 2}}
