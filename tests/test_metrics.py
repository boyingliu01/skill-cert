"""Tests for engine/metrics.py — L1-L4 metrics calculation."""

import pytest
from engine.metrics import MetricsCalculator


class TestMetricsCalculator:
    """Test the MetricsCalculator class and its L1-L4 calculations."""
    
    def test_calculate_metrics_empty_results(self):
        """Test metrics calculation with empty results."""
        calculator = MetricsCalculator()
        results = []
        
        metrics = calculator.calculate_metrics(results)
        
        assert metrics["overall_score"] == 0.0
        assert metrics["l1_trigger_accuracy"] == 0.0
        assert metrics["l2_with_without_skill_delta"] == 0.0
        assert metrics["l3_step_adherence"] == 0.0
        assert metrics["l4_execution_stability"] == 1.0  # Perfect stability with no data
        
        # Check that breakdowns exist
        assert "l1_details" in metrics["metrics_breakdown"]
        assert "l2_details" in metrics["metrics_breakdown"]
        assert "l3_details" in metrics["metrics_breakdown"]
        assert "l4_details" in metrics["metrics_breakdown"]
    
    def test_calculate_l1_trigger_accuracy(self):
        """Test L1 trigger accuracy calculation."""
        calculator = MetricsCalculator()
        
        # Create eval results with trigger category
        eval_results = [
            {"category": "trigger", "final_passed": True},
            {"category": "trigger", "final_passed": True},
            {"category": "trigger", "final_passed": False},
            {"category": "normal", "final_passed": True},  # Should be ignored
        ]
        
        l1_score = calculator._calculate_l1_trigger_accuracy(eval_results)
        
        assert l1_score == 2/3  # 2 out of 3 trigger evaluations passed
    
    def test_calculate_l1_trigger_accuracy_no_triggers(self):
        """Test L1 calculation when there are no trigger evaluations."""
        calculator = MetricsCalculator()
        
        eval_results = [
            {"category": "normal", "final_passed": True},
            {"category": "boundary", "final_passed": False},
        ]
        
        l1_score = calculator._calculate_l1_trigger_accuracy(eval_results)
        
        assert l1_score == 0.0  # No trigger evaluations
    
    def test_calculate_l2_with_without_skill_delta(self):
        """Test L2 with/without skill delta calculation."""
        calculator = MetricsCalculator()
        
        eval_results = [
            {"skill_used": True, "pass_rate": 0.8},
            {"skill_used": True, "pass_rate": 0.9},
            {"skill_used": False, "pass_rate": 0.6},
            {"skill_used": False, "pass_rate": 0.7},
        ]
        
        l2_score = calculator._calculate_l2_with_without_skill_delta(eval_results)
        
        # With skill avg: (0.8 + 0.9) / 2 = 0.85
        # Without skill avg: (0.6 + 0.7) / 2 = 0.65
        # Delta: 0.85 - 0.65 = 0.2
        # Normalized: min(1.0, 0.2) = 0.2 (but this is simplified in the implementation)
        # The implementation returns the absolute delta normalized to 0-1 range
        assert 0.0 <= l2_score <= 1.0
    
    def test_calculate_l2_no_skill_comparison(self):
        """Test L2 calculation when there's no skill comparison data."""
        calculator = MetricsCalculator()
        
        eval_results = [
            {"skill_used": True, "pass_rate": 0.8},
            {"skill_used": True, "pass_rate": 0.9},
            # No "without skill" results
        ]
        
        l2_score = calculator._calculate_l2_with_without_skill_delta(eval_results)
        
        # Should return average of all results when one type is missing
        expected_avg = (0.8 + 0.9) / 2
        assert l2_score == expected_avg
    
    # ── L2 Regression tests ──────────────────────────────────────
    
    def test_l2_with_greater_than_without_exact_delta(self):
        """L2 regression: with > without produces exact positive delta."""
        calculator = MetricsCalculator()
        
        eval_results = [
            {"skill_used": True, "pass_rate": 0.85},
            {"skill_used": True, "pass_rate": 0.95},
            {"skill_used": False, "pass_rate": 0.50},
            {"skill_used": False, "pass_rate": 0.60},
        ]
        
        l2_score = calculator._calculate_l2_with_without_skill_delta(eval_results)
        
        # With avg: (0.85 + 0.95) / 2 = 0.90
        # Without avg: (0.50 + 0.60) / 2 = 0.55
        # Delta: 0.90 - 0.55 = 0.35
        assert l2_score == pytest.approx(0.35)
    
    def test_l2_with_equal_to_without_delta_zero(self):
        """L2 regression: with == without produces delta of 0."""
        calculator = MetricsCalculator()
        
        eval_results = [
            {"skill_used": True, "pass_rate": 0.70},
            {"skill_used": True, "pass_rate": 0.70},
            {"skill_used": False, "pass_rate": 0.70},
            {"skill_used": False, "pass_rate": 0.70},
        ]
        
        l2_score = calculator._calculate_l2_with_without_skill_delta(eval_results)
        
        # Both avgs are 0.70, delta = 0.0
        assert l2_score == pytest.approx(0.0)
    
    def test_l2_with_less_than_without_returns_abs(self):
        """L2 regression: with < without returns abs(delta) (magnitude, not negative)."""
        calculator = MetricsCalculator()
        
        eval_results = [
            {"skill_used": True, "pass_rate": 0.40},
            {"skill_used": True, "pass_rate": 0.50},
            {"skill_used": False, "pass_rate": 0.80},
            {"skill_used": False, "pass_rate": 0.90},
        ]
        
        l2_score = calculator._calculate_l2_with_without_skill_delta(eval_results)
        
        # With avg: (0.40 + 0.50) / 2 = 0.45
        # Without avg: (0.80 + 0.90) / 2 = 0.85
        # Delta: 0.45 - 0.85 = -0.40 → abs(-0.40) → min(1.0, 0.40) → max(0.0, 0.40) = 0.40
        assert l2_score == pytest.approx(0.40)
    
    def test_l2_empty_results_returns_zero(self):
        """L2 regression: empty results list returns 0.0."""
        calculator = MetricsCalculator()
        
        l2_score = calculator._calculate_l2_with_without_skill_delta([])
        
        assert l2_score == pytest.approx(0.0)
    
    def test_l2_missing_pass_rate_defaults_zero(self):
        """L2 regression: results without pass_rate default to 0.0."""
        calculator = MetricsCalculator()
        
        eval_results = [
            {"skill_used": True},  # no pass_rate → defaults to 0.0
            {"skill_used": True, "pass_rate": 0.8},
            {"skill_used": False, "pass_rate": 0.5},
            {"skill_used": False, "pass_rate": 0.5},
        ]
        
        l2_score = calculator._calculate_l2_with_without_skill_delta(eval_results)
        
        # With avg: (0.0 + 0.8) / 2 = 0.40
        # Without avg: (0.5 + 0.5) / 2 = 0.50
        # Delta: 0.40 - 0.50 = -0.10 → abs = 0.10
        assert l2_score == pytest.approx(0.10)
    
    def test_calculate_l3_step_adherence(self):
        """Test L3 step adherence calculation."""
        calculator = MetricsCalculator()
        
        eval_results = [
            {"final_passed": True, "pass_rate": 0.8},
            {"final_passed": True, "pass_rate": 0.9},
            {"final_passed": False, "pass_rate": 0.3},
        ]
        
        l3_score = calculator._calculate_l3_step_adherence(eval_results)
        
        # Implementation returns average pass rate of passing evaluations
        # Passing evals: [0.8, 0.9] -> avg = 0.85
        assert 0.0 <= l3_score <= 1.0
    
    def test_calculate_l3_step_adherence_with_workflow_step(self):
        """Test L3 step adherence with real workflow_step coverage (no spec)."""
        calculator = MetricsCalculator()

        eval_results = [
            {"final_passed": True, "pass_rate": 0.9, "workflow_step": "Parse input"},
            {"final_passed": True, "pass_rate": 0.8, "workflow_step": "Validate schema"},
            {"final_passed": False, "pass_rate": 0.3, "workflow_step": "Execute"},
        ]

        # workflow_step present but NO workflow_steps spec → fall back to pass_rate proxy
        l3_score = calculator._calculate_l3_step_adherence(eval_results)
        # Passing evals: [0.9, 0.8] → avg = 0.85
        assert l3_score == pytest.approx(0.85)

    def test_calculate_l3_step_adherence_with_coverage(self):
        """Test L3 step adherence with both workflow_step and spec workflow_steps."""
        calculator = MetricsCalculator()

        eval_results = [
            {"final_passed": True, "pass_rate": 0.9, "workflow_step": "Parse input"},
            {"final_passed": True, "pass_rate": 0.8, "workflow_step": "Validate schema"},
            {"final_passed": False, "pass_rate": 0.3, "workflow_step": "Execute"},
            {"final_passed": True, "pass_rate": 1.0, "workflow_step": "Parse input"},
        ]

        workflow_steps = ["Parse input", "Validate schema", "Execute", "Generate output"]

        l3_score = calculator._calculate_l3_step_adherence(eval_results, workflow_steps)

        # Covered: {Parse input, Validate schema} — 2 unique steps covered
        # Total: 4 steps → 2/4 = 0.5
        assert l3_score == 0.5

    def test_calculate_l3_step_adherence_full_coverage(self):
        """Test L3 step adherence when all workflow steps are covered."""
        calculator = MetricsCalculator()

        eval_results = [
            {"final_passed": True, "pass_rate": 0.7, "workflow_step": "Step 1"},
            {"final_passed": True, "pass_rate": 0.6, "workflow_step": "Step 2"},
            {"final_passed": True, "pass_rate": 0.9, "workflow_step": "Step 3"},
        ]

        workflow_steps = ["Step 1", "Step 2", "Step 3"]

        l3_score = calculator._calculate_l3_step_adherence(eval_results, workflow_steps)

        assert l3_score == 1.0

    def test_calculate_l3_step_adherence_no_passing(self):
        """Test L3 step adherence when no evals pass — returns 0.0."""
        calculator = MetricsCalculator()

        eval_results = [
            {"final_passed": False, "pass_rate": 0.0, "workflow_step": "Step 1"},
            {"final_passed": False, "pass_rate": 0.0, "workflow_step": "Step 2"},
        ]

        workflow_steps = ["Step 1", "Step 2"]

        l3_score = calculator._calculate_l3_step_adherence(eval_results, workflow_steps)
        assert l3_score == 0.0

    def test_calculate_l3_step_adherence_empty_workflow_steps(self):
        """Test L3 step adherence when spec has no workflow steps."""
        calculator = MetricsCalculator()

        eval_results = [
            {"final_passed": True, "pass_rate": 0.8, "workflow_step": "Step 1"},
        ]

        l3_score = calculator._calculate_l3_step_adherence(eval_results, [])

        # Has workflow_step info but empty spec → should return 0.0
        assert l3_score == 0.0

    def test_calculate_l4_execution_stability(self):
        """Test L4 execution stability calculation."""
        calculator = MetricsCalculator()
        
        # Create results with deterministic assertions (confidence = 1.0)
        eval_results = [
            {
                "assertion_results": [
                    {"confidence": 1.0, "passed": True},
                    {"confidence": 1.0, "passed": True},
                    {"confidence": 0.8, "passed": True},  # Non-deterministic, should be ignored
                ]
            },
            {
                "assertion_results": [
                    {"confidence": 1.0, "passed": True},
                    {"confidence": 1.0, "passed": False},
                ]
            },
            {
                "assertion_results": [
                    {"confidence": 1.0, "passed": True},
                    {"confidence": 1.0, "passed": True},
                ]
            }
        ]
        
        l4_score = calculator._calculate_l4_execution_stability(eval_results)
        
        # First result: 2/2 deterministic assertions passed = 1.0
        # Second result: 1/2 deterministic assertions passed = 0.5
        # Third result: 2/2 deterministic assertions passed = 1.0
        # Std dev of [1.0, 0.5, 1.0] should affect stability score
        assert 0.0 <= l4_score <= 1.0
    
    def test_calculate_l4_single_result(self):
        """Test L4 calculation with only one result."""
        calculator = MetricsCalculator()
        
        eval_results = [
            {
                "assertion_results": [
                    {"confidence": 1.0, "passed": True},
                    {"confidence": 1.0, "passed": True},
                ]
            }
        ]
        
        l4_score = calculator._calculate_l4_execution_stability(eval_results)
        
        # With only one data point, should return perfect stability
        assert l4_score == 1.0
    
    def test_calculate_l4_no_deterministic_results(self):
        """Test L4 calculation with no deterministic results."""
        calculator = MetricsCalculator()
        
        eval_results = [
            {
                "assertion_results": [
                    {"confidence": 0.8, "passed": True},  # Non-deterministic
                    {"confidence": 0.5, "passed": False},  # Non-deterministic
                ]
            }
        ]
        
        l4_score = calculator._calculate_l4_execution_stability(eval_results)
        
        # With no deterministic results, should return 0.0 if no results, or 1.0 if one result
        assert l4_score in [0.0, 1.0]  # Depends on implementation logic
    
    def test_get_l1_details(self):
        """Test getting L1 details."""
        calculator = MetricsCalculator()
        
        eval_results = [
            {"category": "trigger", "final_passed": True},
            {"category": "trigger", "final_passed": False},
            {"category": "normal", "final_passed": True},
        ]
        
        details = calculator._get_l1_details(eval_results)
        
        assert details["total_trigger_evals"] == 2
        assert details["passed_trigger_evals"] == 1
        assert details["trigger_accuracy"] == 0.5
    
    def test_get_l2_details(self):
        """Test getting L2 details."""
        calculator = MetricsCalculator()
        
        eval_results = [
            {"skill_used": True, "pass_rate": 0.8},
            {"skill_used": True, "pass_rate": 0.9},
            {"skill_used": False, "pass_rate": 0.6},
            {"skill_used": False, "pass_rate": 0.7},
        ]
        
        details = calculator._get_l2_details(eval_results)
        
        assert details["with_skill_avg_pass_rate"] == pytest.approx(0.85)  # (0.8 + 0.9) / 2
        assert details["without_skill_avg_pass_rate"] == pytest.approx(0.65)  # (0.6 + 0.7) / 2
        assert details["delta"] == pytest.approx(0.2)  # 0.85 - 0.65
        assert details["improvement_percentage"] == pytest.approx(30.77, abs=0.01)  # (0.2 / 0.65) * 100
    
    def test_get_l3_details(self):
        """Test getting L3 details."""
        calculator = MetricsCalculator()
        
        eval_results = [
            {"final_passed": True},
            {"final_passed": True},
            {"final_passed": False},
            {"final_passed": True},
        ]
        
        details = calculator._get_l3_details(eval_results)
        
        assert details["total_evaluations"] == 4
        assert details["passing_evaluations"] == 3
        assert details["step_coverage_ratio"] == 0.75  # 3/4
    
    def test_get_l4_details(self):
        """Test getting L4 details."""
        calculator = MetricsCalculator()
        
        eval_results = [
            {
                "assertion_results": [
                    {"confidence": 1.0, "passed": True},
                    {"confidence": 1.0, "passed": True},
                ]
            },
            {
                "assertion_results": [
                    {"confidence": 1.0, "passed": True},
                    {"confidence": 1.0, "passed": False},
                ]
            }
        ]
        
        details = calculator._get_l4_details(eval_results)
        
        assert details["deterministic_evals_count"] == 2
        assert details["avg_deterministic_pass_rate"] == 0.75  # (1.0 + 0.5) / 2
        assert details["execution_stability"] >= 0.0  # Should be calculated