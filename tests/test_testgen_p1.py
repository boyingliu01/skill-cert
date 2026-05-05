"""TDD tests for P1: Deepen eval assertions — structural validation."""

import pytest
from engine.testgen import EvalGenerator


class TestMinimumEvalsHasDeepAssertions:
    """P1 requirement: minimum evals template must use structural assertions."""

    def setup_method(self):
        self.gen = EvalGenerator()

    def test_template_has_regex_assertions_for_trigger(self):
        """Trigger eval should check for structural patterns like PASS/FAIL, not keywords."""
        template = self.gen.minimum_evals_template
        for key in ["eval_cases", "evals", "cases"]:
            if key in template:
                cases = template[key]
                break
        else:
            pytest.skip("No eval cases in template")
        
        trigger_case = next((c for c in cases if c.get("category") == "trigger" and c.get("expected_triggers", False)), None)
        if trigger_case:
            assertion_types = {a.get("type") for a in trigger_case.get("assertions", [])}
            assert "regex" in assertion_types, f"Trigger eval should use regex assertion, got: {assertion_types}"

    def test_template_assertion_weights_are_meanful(self):
        """At least some assertions should have weight >= 2 (important/critical)."""
        template = self.gen.minimum_evals_template
        for key in ["eval_cases", "evals", "cases"]:
            if key in template:
                cases = template[key]
                break
        else:
            pytest.skip("No eval cases in template")
        
        max_weight = max(
            (a.get("weight", 0) for c in cases for a in c.get("assertions", [])),
            default=0
        )
        assert max_weight >= 2, f"No assertion with weight >= 2, max is {max_weight}"

    def test_template_has_multiple_assertions_per_case(self):
        """Each eval case should have at least 2 assertions for depth."""
        template = self.gen.minimum_evals_template
        for key in ["eval_cases", "evals", "cases"]:
            if key in template:
                cases = template[key]
                break
        else:
            pytest.skip("No eval cases in template")
        
        for case in cases:
            n = len(case.get("assertions", []))
            assert n >= 2, f"Case {case.get('name')} has only {n} assertions, need >= 2"


class TestInitialEvalPromptDeepening:
    """P1 requirement: generation prompt must guide deep assertions."""

    def setup_method(self):
        self.gen = EvalGenerator()

    def test_prompt_includes_structural_assertion_guidance(self):
        """Initial eval prompt should include examples of structural/regex assertions."""
        spec = {
            "name": "test-skill",
            "description": "A test skill",
            "triggers": ["test trigger"],
            "workflow_steps": ["step 1"],
            "anti_patterns": [],
            "output_format": [],
            "examples": []
        }
        prompt = self.gen._prepare_generation_prompt(spec)
        
        # Must mention regex as assertion type
        assert "regex" in prompt.lower()
        
        # Must mention structural patterns like PASS/FAIL verdict
        assert "PASS" in prompt or "verdict" in prompt.lower() or "PASS_WITH_CAVEATS" in prompt

    def test_prompt_includes_category_specific_assertion_templates(self):
        """Prompt should include separate assertion guidance for trigger vs normal."""
        spec = {
            "name": "test-skill",
            "description": "A test skill",
            "triggers": ["test trigger"],
            "workflow_steps": ["step 1"],
            "anti_patterns": [],
            "output_format": [],
            "examples": []
        }
        prompt = self.gen._prepare_generation_prompt(spec)
        
        # Must mention trigger assertion patterns
        assert "trigger" in prompt.lower()
