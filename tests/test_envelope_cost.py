"""Tests for engine/envelope.py cost budget checking."""

from engine.envelope import EnvelopeChecker


class TestEnvelopeCostBudget:

    def test_cost_budget_default_not_exceeded(self):
        """When cost is within budget, result should pass."""
        checker = EnvelopeChecker()
        trace = type('Trace', (), {
            "steps": 5,
            "tool_calls": 3,
            "tokens": 10000,
            "time_ms": 5000,
            "cost": 0.50,
        })()
        result = checker.check(trace)
        assert result.passed is True

    def test_cost_budget_exceeded(self):
        """When cost exceeds budget, result should fail with violation."""
        checker = EnvelopeChecker(cost_budget=1.0)
        trace = type('Trace', (), {
            "steps": 5,
            "tool_calls": 3,
            "tokens": 10000,
            "time_ms": 5000,
            "cost": 1.50,
        })()
        result = checker.check(trace)
        assert result.passed is False
        violations = [v for v in result.violations if "cost_budget" in v]
        assert len(violations) > 0

    def test_cost_budget_at_limit(self):
        """When cost equals budget, should pass (not exceeded)."""
        checker = EnvelopeChecker(cost_budget=1.0)
        trace = type('Trace', (), {
            "steps": 5,
            "tool_calls": 3,
            "tokens": 10000,
            "time_ms": 5000,
            "cost": 1.0,
        })()
        result = checker.check(trace)
        assert result.passed is True

    def test_cost_field_in_details(self):
        """Result details should include cost value."""
        checker = EnvelopeChecker()
        trace = type('Trace', (), {
            "steps": 5,
            "tool_calls": 3,
            "tokens": 10000,
            "time_ms": 5000,
            "cost": 0.25,
        })()
        result = checker.check(trace)
        assert result.details.get("cost") == 0.25

    def test_no_cost_field_backward_compat(self):
        """When trace has no cost field, should not crash."""
        checker = EnvelopeChecker()
        trace = type('Trace', (), {
            "steps": 5,
            "tool_calls": 3,
            "tokens": 10000,
            "time_ms": 5000,
        })()
        result = checker.check(trace)
        assert result.passed is True
        assert result.details.get("cost") == 0.0
