"""Tests for engine.testgen — assertion strategy routing via classifier."""

from __future__ import annotations

from engine.testgen import EvalGenerator


class TestTestgenRoutesNaturalLanguageToLlmJudge:
    """Given: a natural language skill spec
    When: _apply_classifier_routing is called
    Then: all eval cases get assertion_strategy='llm_judge'"""

    def test_natural_language_routed_to_llm_judge(self):
        gen = EvalGenerator()
        skill_spec = {
            "name": "Review Skill",
            "description": "First review the code, then check for issues, finally provide feedback",
            "triggers": ["review", "code review", "check my code"],
            "workflow_steps": [
                {"name": "Read the diff", "type": "review"},
                {"name": "Check for patterns", "type": "review"},
                {"name": "Write comments", "type": "output"},
            ],
            "output_format": ["Markdown report with sections"],
        }
        evals = {
            "eval_cases": [
                {"id": 1, "name": "test1", "category": "normal",
                 "assertions": [{"type": "contains", "value": "review"}],
                 "assertion_strategy": "deterministic"},
                {"id": 2, "name": "test2", "category": "workflow_step",
                 "assertions": [{"type": "contains", "value": "diff"}],
                 "assertion_strategy": "deterministic"},
            ]
        }
        result = gen._apply_classifier_routing(evals, skill_spec)
        for case in result["eval_cases"]:
            assert case["assertion_strategy"] == "llm_judge"
            assert case["judge_dimensions"] == [
                "output_quality", "trigger_accuracy", "workflow_quality"
            ]


class TestTestgenStructuredUnchanged:
    """Given: a structured skill spec
    When: _apply_classifier_routing is called
    Then: assertion_strategy remains unchanged"""

    def test_structured_unchanged(self):
        gen = EvalGenerator()
        skill_spec = {
            "name": "JSON Formatter",
            "description": "Formats data into valid JSON",
            "triggers": ["format json"],
            "workflow_steps": [{"name": "Parse input", "type": "parse"}],
            "output_format": ["json schema", "code block"],
        }
        evals = {
            "eval_cases": [
                {"id": 1, "name": "test1", "category": "normal",
                 "assertions": [{"type": "json_valid", "value": "{}"}],
                 "assertion_strategy": "deterministic"},
            ]
        }
        result = gen._apply_classifier_routing(evals, skill_spec)
        for case in result["eval_cases"]:
            assert case["assertion_strategy"] == "deterministic"


class TestTestgenPromptNoLongerHardcodesLlmJudge:
    """Given: EvalGenerator._prepare_agent_guide_prompt
    When: the prompt is generated
    Then: it does NOT contain 'MUST use assertion_strategy=llm_judge'"""

    def test_prompt_no_hardcoded_llm_judge(self):
        gen = EvalGenerator()
        skill_spec = {
            "name": "Test",
            "workflow_steps": [{"name": "step1", "type": "a"}],
        }
        prompt = gen._prepare_agent_guide_prompt(skill_spec)
        # The old prompt had "Each case MUST use assertion_strategy=llm_judge"
        # The new prompt should not have this hardcoded instruction
        assert "MUST use assertion_strategy=llm_judge" not in prompt
        # But should still mention assertion_strategy as an option
        assert "assertion_strategy" in prompt.lower() or "assertion_strategy" in prompt
