"""Tests for engine.classifier — score-based output type detection."""

from __future__ import annotations

from engine.classifier import classify_output_type


class TestClassifierReviewSkillReturnsNaturalLanguage:
    """Given: a review-style skill with workflow steps and flow language
    When: classify_output_type is called
    Then: strategy is natural_language with confidence >= 0.6"""

    def test_review_skill_returns_natural_language(self):
        skill_spec = {
            "name": "Code Review Skill",
            "description": "First review the code, then check for issues, finally provide feedback",
            "triggers": ["review", "code review", "check my code"],
            "workflow_steps": [
                {"name": "Read the diff", "type": "review"},
                {"name": "Check for patterns", "type": "review"},
                {"name": "Write comments", "type": "output"},
            ],
            "output_format": ["Markdown report with sections"],
        }
        result = classify_output_type(skill_spec)
        assert result.strategy == "natural_language"
        assert result.confidence >= 0.6
        assert len(result.signals) > 0


class TestClassifierStructuredSkillReturnsStructured:
    """Given: a skill that produces JSON/schema output
    When: classify_output_type is called
    Then: strategy is structured"""

    def test_structured_skill_returns_structured(self):
        skill_spec = {
            "name": "JSON Formatter",
            "description": "Formats data into valid JSON",
            "triggers": ["format json", "json output"],
            "workflow_steps": [{"name": "Parse input", "type": "parse"}],
            "output_format": ["json schema", "code block"],
        }
        result = classify_output_type(skill_spec)
        assert result.strategy == "structured"
        assert len(result.signals) > 0


class TestClassifierAmbiguousSkillThreshold:
    """Given: a skill with borderline signals
    When: classify_output_type is called
    Then: score threshold at 3.0 determines strategy"""

    def test_ambiguous_skill_threshold(self):
        # Exactly at threshold: 1 workflow step (0.5) + 1 flow pattern (0.75) + 2 triggers (0.5) = 1.75
        # Plus non-structured format (1.0) = 2.75 → structured
        skill_spec_minimal = {
            "name": "Minimal",
            "description": "First do this",
            "triggers": ["a", "b"],
            "workflow_steps": [{"name": "step", "type": "basic"}],
            "output_format": ["text report"],
        }
        result_minimal = classify_output_type(skill_spec_minimal)
        assert result_minimal.strategy == "structured"

        # Above threshold: more workflow steps + more flow patterns
        skill_spec_above = {
            "name": "Above Threshold",
            "description": "First do this, then do that, finally wrap up",
            "triggers": ["a", "b", "c"],
            "workflow_steps": [
                {"name": "s1", "type": "a"},
                {"name": "s2", "type": "b"},
            ],
            "output_format": ["text report"],
        }
        result_above = classify_output_type(skill_spec_above)
        assert result_above.strategy == "natural_language"


class TestClassifierMissingOutputFormat:
    """Given: a skill with no output_format field
    When: classify_output_type is called
    Then: classification still works based on other signals"""

    def test_missing_output_format(self):
        skill_spec = {
            "name": "No Format",
            "description": "A skill without output format",
            "triggers": ["test"],
            "workflow_steps": [],
        }
        result = classify_output_type(skill_spec)
        assert result.strategy in ("structured", "natural_language")
        assert 0.0 <= result.confidence <= 1.0


class TestClassifierEmptySpec:
    """Given: an empty skill spec
    When: classify_output_type is called
    Then: returns structured with confidence 0.5"""

    def test_empty_spec(self):
        result = classify_output_type({})
        assert result.strategy == "structured"
        assert result.confidence == 0.5
        assert "empty_spec" in result.signals

    def test_none_like_spec(self):
        result = classify_output_type({"name": "", "description": ""})
        assert result.strategy == "structured"


class TestClassifierFalsePositiveResilience:
    """Given: a structured skill with misleading flow language in description
    When: classify_output_type is called
    Then: structured output_format dominates the score"""

    def test_false_positive_resilience(self):
        skill_spec = {
            "name": "API Client Generator",
            "description": "First parse the schema, then generate the client code, finally validate it",
            "triggers": ["generate api client", "create api"],
            "workflow_steps": [
                {"name": "Parse OpenAPI", "type": "input"},
                {"name": "Generate code", "type": "output"},
            ],
            "output_format": ["json schema", "typescript code"],
        }
        result = classify_output_type(skill_spec)
        # Despite flow language in description, structured format dominates
        assert result.strategy == "structured"
