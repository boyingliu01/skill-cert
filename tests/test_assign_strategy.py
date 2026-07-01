from engine.testgen import EvalGenerator


class TestAssignStrategy:
    def test_trigger_category_without_structured_output(self):
        result = EvalGenerator._assign_strategy("trigger", [])
        assert result == "mixed"

    def test_trigger_category_with_structured_output(self):
        result = EvalGenerator._assign_strategy("trigger", ["json", "verdict"])
        assert result == "deterministic"

    def test_workflow_step_category_llm_judge(self):
        result = EvalGenerator._assign_strategy("workflow_step", [])
        assert result == "llm_judge"

    def test_anti_pattern_category_mixed(self):
        result = EvalGenerator._assign_strategy("anti_pattern", [])
        assert result == "mixed"

    def test_boundary_category_mixed(self):
        result = EvalGenerator._assign_strategy("boundary", [])
        assert result == "mixed"

    def test_output_format_json_deterministic(self):
        result = EvalGenerator._assign_strategy(
            "output_format", ["json", "structured"]
        )
        assert result == "deterministic"

    def test_output_format_code_deterministic(self):
        result = EvalGenerator._assign_strategy(
            "output_format", ["code_block", "json_schema"]
        )
        assert result == "deterministic"

    def test_output_format_markdown_llm_judge(self):
        result = EvalGenerator._assign_strategy(
            "output_format", ["markdown", "text"]
        )
        assert result == "llm_judge"

    def test_output_format_empty_llm_judge(self):
        result = EvalGenerator._assign_strategy("output_format", [])
        assert result == "llm_judge"

    def test_unknown_category_defaults_deterministic(self):
        result = EvalGenerator._assign_strategy("unknown_category", [])
        assert result == "deterministic"

    def test_failure_category_deterministic(self):
        result = EvalGenerator._assign_strategy("failure", [])
        assert result == "deterministic"

    def test_normal_category_deterministic(self):
        result = EvalGenerator._assign_strategy("normal", [])
        assert result == "deterministic"


class TestNormalizeEvalCaseStrategy:
    @staticmethod
    def _make_gen():
        return EvalGenerator()

    def test_strategy_propagated_to_normalized(self):
        gen = self._make_gen()
        case = {
            "id": 1,
            "name": "test",
            "category": "workflow_step",
            "input": "...",
            "assertions": [
                {"type": "contains", "value": "x", "weight": 1}
            ],
        }
        normalized = gen._normalize_eval_case(case, 0)
        assert normalized["assertion_strategy"] == "llm_judge"

    def test_output_format_passthrough_strategy(self):
        gen = self._make_gen()
        case = {
            "id": 2,
            "name": "test2",
            "category": "output_format",
            "input": "...",
            "output_format_fields": ["json", "code"],
            "assertions": [
                {"type": "contains", "value": "x", "weight": 1}
            ],
        }
        normalized = gen._normalize_eval_case(case, 1)
        assert normalized["assertion_strategy"] == "deterministic"

    def test_existing_strategy_preserved(self):
        gen = self._make_gen()
        case = {
            "id": 3,
            "name": "test3",
            "category": "normal",
            "input": "...",
            "assertion_strategy": "mixed",
            "assertions": [
                {"type": "contains", "value": "x", "weight": 1}
            ],
        }
        normalized = gen._normalize_eval_case(case, 2)
        assert normalized["assertion_strategy"] == "mixed"
