"""Integration test for metrics pipeline — verifies grader → metrics → reporter end-to-end flow."""

import sys
import json
import pytest
sys.path.insert(0, '.')

from engine.grader import Grader, EvalCase, EvalAssertion
from engine.metrics import MetricsCalculator
from engine.reporter import Reporter


class TestMetricsPipelineEndToEnd:
    """Verify end-to-end metric flow with valid assertions."""
    
    def test_grader_metrics_reporter_pipeline(self):
        # 1. Create a valid eval case with assertions
        assertions = [
            EvalAssertion(name="contains_hello", type="contains", value="hello", weight=3),
            EvalAssertion(name="contains_world", type="contains", value="world", weight=2),
            EvalAssertion(name="not_contains_foo", type="not_contains", value="foo", weight=1),
        ]
        eval_case = EvalCase(
            id=1, name="test_case", category="trigger", 
            prompt="Say hello", assertions=assertions
        )
        
        # 2. Grade a passing output
        grader = Grader()
        passing_output = "hello world"
        passing_grade = grader.grade_output(eval_case, passing_output)
        
        assert passing_grade["pass_rate"] == 1.0
        assert passing_grade["final_passed"] is True
        assert passing_grade["category"] == "trigger"
        assert len(passing_grade["assertion_results"]) == 3
        
        # 3. Grade a failing output
        failing_output = "foo bar"
        failing_grade = grader.grade_output(eval_case, failing_output)
        
        assert failing_grade["pass_rate"] < 1.0
        assert failing_grade["final_passed"] is False
        
        # 4. Calculate metrics
        eval_results = [passing_grade, failing_grade]
        calc = MetricsCalculator()
        metrics = calc.calculate_metrics(eval_results)
        
        assert metrics["overall_score"] > 0.0
        assert metrics["l1_trigger_accuracy"] > 0.0
        assert "metrics_breakdown" in metrics
        assert metrics["metrics_breakdown"]["l1_details"]["total_trigger_evals"] == 2
        assert metrics["metrics_breakdown"]["l1_details"]["passed_trigger_evals"] == 1
        
        # 5. Generate report
        reporter = Reporter()
        md_report, json_report = reporter.generate_report(
            metrics, 
            {"overall_drift": "none", "overall_verdict": "PASS"},
            {"total_evaluations": 2, "avg_pass_rate": 0.5, 
             "critical_passed": 1, "critical_total": 1, 
             "important_passed": 0, "important_total": 0, 
             "normal_passed": 0, "normal_total": 0}
        )
        
        # Verify Markdown contains correct scores
        assert "Trigger Accuracy" in md_report
        assert "100.00%" in md_report or "50.00%" in md_report  # Should show actual scores, not 0%
        
        # Verify JSON contains correct metrics
        assert json_report["metrics"]["l1_trigger_accuracy"] > 0.0
        assert json_report["overall_score"] > 0.0

    def test_empty_assertions_logging(self, caplog):
        """Verify grader logs warning when no assertions are provided."""
        import logging
        caplog.set_level(logging.WARNING)
        
        eval_case = EvalCase(
            id=2, name="empty_case", category="normal", 
            prompt="test", assertions=[]
        )
        grader = Grader()
        grade = grader.grade_output(eval_case, "output")
        
        assert "No assertions" in caplog.text
        assert grade["pass_rate"] == 0.0
