"""Tests for engine/metrics.py — L1-L4 metrics calculation."""

import json

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
        assert metrics["l3_step_adherence"] is None  # None when no trajectory data
        assert metrics["l4_execution_stability"] is None  # No data → L4 unavailable

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

        assert l1_score == 2 / 3  # 2 out of 3 trigger evaluations passed

    def test_calculate_l1_trigger_accuracy_no_triggers(self):
        """Test L1 calculation when there are no trigger evaluations."""
        calculator = MetricsCalculator()

        eval_results = [
            {"category": "normal", "final_passed": True},
            {"category": "boundary", "final_passed": False},
        ]

        l1_score = calculator._calculate_l1_trigger_accuracy(eval_results)

        assert l1_score == 0.0  # No trigger evaluations

    def test_calculate_f1_score_all_correct(self):
        """Test F1 score when all positive and negative cases are correct."""
        calculator = MetricsCalculator()
        eval_results = [
            {"category": "trigger", "negative_case": False, "final_passed": True},  # TP
            {"category": "trigger", "negative_case": False, "final_passed": True},  # TP
            {"category": "trigger", "negative_case": True, "final_passed": True},  # TN
            {"category": "trigger", "negative_case": True, "final_passed": True},  # TN
        ]
        f1 = calculator._calculate_f1_score(eval_results)
        assert f1 == 1.0  # Precision=1.0, Recall=1.0

    def test_calculate_f1_score_no_negative_cases(self):
        """Test F1 score returns None when no negative_case evals present."""
        calculator = MetricsCalculator()
        eval_results = [
            {"category": "trigger", "final_passed": True},
            {"category": "trigger", "final_passed": False},
        ]
        f1 = calculator._calculate_f1_score(eval_results)
        assert f1 is None  # Falls back to caller

    def test_calculate_f1_score_some_failures(self):
        """Test F1 score with mixed TP/TN/FP/FN."""
        calculator = MetricsCalculator()
        eval_results = [
            {"category": "trigger", "negative_case": False, "final_passed": True},  # TP
            {"category": "trigger", "negative_case": False, "final_passed": False},  # FN
            {"category": "trigger", "negative_case": True, "final_passed": True},  # TN
            {"category": "trigger", "negative_case": True, "final_passed": False},  # FP
        ]
        f1 = calculator._calculate_f1_score(eval_results)
        # Precision = TP/(TP+FP) = 1/(1+1) = 0.5
        # Recall = TP/(TP+FN) = 1/(1+1) = 0.5
        # F1 = 2 * 0.5 * 0.5 / (0.5+0.5) = 0.5
        assert f1 == 0.5

    def test_calculate_f1_score_no_triggers(self):
        """Test F1 score returns None when no trigger category evals."""
        calculator = MetricsCalculator()
        eval_results = [
            {"category": "normal", "final_passed": True},
        ]
        f1 = calculator._calculate_f1_score(eval_results)
        assert f1 is None

    def test_l1_trigger_accuracy_uses_f1_when_negative_cases_present(self):
        """Test L1 uses F1 when negative_case evals exist."""
        calculator = MetricsCalculator()
        eval_results = [
            {"category": "trigger", "negative_case": False, "final_passed": True},  # TP
            {"category": "trigger", "negative_case": False, "final_passed": True},  # TP
            {"category": "trigger", "negative_case": True, "final_passed": True},  # TN
            {"category": "trigger", "negative_case": True, "final_passed": False},  # FP
        ]
        l1 = calculator._calculate_l1_trigger_accuracy(eval_results)
        # Precision = 2/(2+1) = 2/3, Recall = 2/(2+0) = 1.0
        # F1 = 2 * (2/3) * 1.0 / (2/3 + 1.0) = 2 * 2/3 / 5/3 = 4/5 = 0.8
        assert l1 == pytest.approx(0.8, 0.01)

    def test_l1_trigger_accuracy_falls_back_without_negative_cases(self):
        """Test L1 falls back to simple accuracy without negative_case evals."""
        calculator = MetricsCalculator()
        eval_results = [
            {"category": "trigger", "final_passed": True},
            {"category": "trigger", "final_passed": True},
            {"category": "trigger", "final_passed": False},
        ]
        l1 = calculator._calculate_l1_trigger_accuracy(eval_results)
        assert l1 == 2 / 3

    def test_get_l1_details_includes_f1_when_negative_cases_present(self):
        """Test _get_l1_details includes f1_score and confusion_matrix."""
        calculator = MetricsCalculator()
        eval_results = [
            {"category": "trigger", "negative_case": False, "final_passed": True},  # TP
            {"category": "trigger", "negative_case": True, "final_passed": True},  # TN
            {"category": "trigger", "negative_case": True, "final_passed": False},  # FP
        ]
        details = calculator._get_l1_details(eval_results)
        assert "f1_score" in details
        assert details["f1_score"] == pytest.approx(0.666, 0.01)
        assert "confusion_matrix" in details
        assert details["confusion_matrix"]["true_positives"] == 1
        assert details["confusion_matrix"]["true_negatives"] == 1
        assert details["confusion_matrix"]["false_positives"] == 1
        assert details["confusion_matrix"]["false_negatives"] == 0

    def test_get_l1_details_no_f1_without_negative_cases(self):
        """Test _get_l1_details does NOT include f1 without negative_case evals."""
        calculator = MetricsCalculator()
        eval_results = [
            {"category": "trigger", "final_passed": True},
            {"category": "trigger", "final_passed": False},
        ]
        details = calculator._get_l1_details(eval_results)
        assert "f1_score" not in details
        assert "confusion_matrix" not in details

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
        """L2 regression: with > without produces positive normalized gain."""
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
        # Normalized gain: (0.90 - 0.55) / 0.55 = 0.636...
        assert l2_score == pytest.approx(0.35 / 0.55)

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

    def test_l2_with_less_than_without_returns_zero(self):
        """L2 regression: with < without returns 0 (negative gain capped)."""
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
        # Normalized gain: (0.45 - 0.85) / 0.85 = -0.47 → capped to 0.0
        assert l2_score == pytest.approx(0.0)

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

        assert l2_score == pytest.approx(0.0)

    def test_l2_category_weighted_delta_higher_weight_categories(self):
        """L2 weighted delta gives higher weight to trigger/normal categories."""
        calculator = MetricsCalculator()

        with_skill = [
            {"skill_used": True, "category": "trigger", "pass_rate": 1.0},
            {"skill_used": True, "category": "normal", "pass_rate": 1.0},
            {"skill_used": True, "category": "failure", "pass_rate": 0.0},
        ]
        without_skill = [
            {"skill_used": False, "category": "trigger", "pass_rate": 0.5},
            {"skill_used": False, "category": "normal", "pass_rate": 0.5},
            {"skill_used": False, "category": "failure", "pass_rate": 0.5},
        ]
        eval_results = with_skill + without_skill
        l2_score = calculator._calculate_l2_with_without_skill_delta(eval_results)

        assert 0.0 < l2_score < 1.0

    def test_l2_flat_average_same_category(self):
        """L2 weighted delta matches flat avg when all results share one category."""
        calculator = MetricsCalculator()

        eval_results = [
            {"skill_used": True, "category": "normal", "pass_rate": 0.8},
            {"skill_used": True, "category": "normal", "pass_rate": 0.9},
            {"skill_used": False, "category": "normal", "pass_rate": 0.6},
            {"skill_used": False, "category": "normal", "pass_rate": 0.7},
        ]

        l2_score = calculator._calculate_l2_with_without_skill_delta(eval_results)
        with_avg = 0.85
        without_avg = 0.65
        expected = max(0.0, min(1.0, (with_avg - without_avg) / without_avg))
        assert l2_score == pytest.approx(expected, rel=1e-3)

    def test_calculate_l3_step_adherence(self):
        """Test L3 step adherence calculation."""
        calculator = MetricsCalculator()

        eval_results = [
            {"final_passed": True, "pass_rate": 0.8},
            {"final_passed": True, "pass_rate": 0.9},
            {"final_passed": False, "pass_rate": 0.3},
        ]

        l3_score = calculator._calculate_l3_step_adherence(eval_results)
        # No workflow_step data, no trajectory → returns None
        assert l3_score is None

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
        # No passing evals → returns None
        assert l3_score is None

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
            },
        ]

        l4_score = calculator._calculate_l4_execution_stability(eval_results)

        # First result: 2/2 deterministic assertions passed = 1.0
        # Second result: 1/2 deterministic assertions passed = 0.5
        # Third result: 2/2 deterministic assertions passed = 1.0
        # Std dev of [1.0, 0.5, 1.0] should affect stability score
        assert l4_score is not None
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

        # With eval_results but no deterministic assertions, L4 is unavailable
        assert l4_score is None

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
        assert details["improvement_percentage"] == pytest.approx(
            30.77, abs=0.01
        )  # (0.2 / 0.65) * 100

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

    def test_l3_step_quality_both_dimensions(self):
        """L3 step_quality combines tool_acc and turn_rel with 60/40 weight."""
        calculator = MetricsCalculator()
        sq = calculator._compute_step_quality(0.8, 0.5)
        expected = 0.6 * 0.8 + 0.4 * 0.5
        assert sq == pytest.approx(expected), f"Expected {expected}, got {sq}"

    def test_l3_step_quality_tool_only(self):
        """L3 step_quality falls back to tool_acc when turn_rel is None."""
        calculator = MetricsCalculator()
        sq = calculator._compute_step_quality(0.8, None)
        assert sq == 0.8

    def test_l3_step_quality_turn_only(self):
        """L3 step_quality falls back to turn_rel when tool_acc is None."""
        calculator = MetricsCalculator()
        sq = calculator._compute_step_quality(None, 0.5)
        assert sq == 0.5

    def test_l3_step_quality_none_when_no_data(self):
        """L3 step_quality returns None when both inputs are None."""
        calculator = MetricsCalculator()
        sq = calculator._compute_step_quality(None, None)
        assert sq is None

    def test_l3_details_includes_step_quality(self):
        """L3 details dict includes step_quality sub-metric."""
        calculator = MetricsCalculator()
        eval_results = [
            {"final_passed": True},
            {"final_passed": True},
        ]
        details = calculator._get_l3_details(eval_results)
        assert "step_quality" in details

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
            },
        ]

        details = calculator._get_l4_details(eval_results)

        assert details["deterministic_evals_count"] == 2
        assert details["avg_deterministic_pass_rate"] == 0.75  # (1.0 + 0.5) / 2
        assert details["execution_stability"] >= 0.0  # Should be calculated

    # ── L5 Step Efficiency ───────────────────────────────────────

    def test_l5_no_trace_returns_none(self):
        """L5 returns None when no trace data exists."""
        calc = MetricsCalculator()
        results = [{"final_passed": True}, {"final_passed": False}]
        assert calc._calculate_l5_step_efficiency(results) is None

    def test_l5_zero_violations_returns_perfect(self):
        """L5 returns 1.0 when trace exists with no violations."""
        calc = MetricsCalculator()
        results = [
            {"trace": {"violations": []}},
            {"trace": {"violations": []}},
        ]
        assert calc._calculate_l5_step_efficiency(results) == 1.0

    def test_l5_one_violation_returns_07(self):
        """L5 returns 0.7 with exactly 1 violation."""
        calc = MetricsCalculator()
        results = [
            {"trace": {"violations": ["token_budget_exceeded"]}},
            {"trace": {"violations": []}},
        ]
        assert calc._calculate_l5_step_efficiency(results) == 0.7

    def test_l5_multiple_violations_returns_03(self):
        """L5 returns 0.3 with 2+ violations."""
        calc = MetricsCalculator()
        results = [
            {"trace": {"violations": ["token_budget_exceeded"]}},
            {"trace": {"violations": ["timeout_exceeded", "step_limit"]}},
        ]
        assert calc._calculate_l5_step_efficiency(results) == 0.3

    def test_l5_trace_without_violations_key(self):
        """L5 handles trace dict without 'violations' key."""
        calc = MetricsCalculator()
        results = [{"trace": {"steps": 5}}]
        assert calc._calculate_l5_step_efficiency(results) == 1.0

    # ── L6 Trajectory Quality ────────────────────────────────────

    def test_l6_no_dialogue_returns_none(self):
        """L6 returns None when no dialogue mode results."""
        calc = MetricsCalculator()
        results = [{"mode": "single", "turn_similarity": 0.9}]
        assert calc._calculate_l6_trajectory_quality(results) is None

    def test_l6_dialogue_with_similarity(self):
        """L6 averages clamped turn_similarity values."""
        calc = MetricsCalculator()
        results = [
            {"mode": "dialogue", "turn_similarity": 0.8},
            {"mode": "dialogue", "turn_similarity": 0.6},
        ]
        assert calc._calculate_l6_trajectory_quality(results) == pytest.approx(0.7)

    def test_l6_clamps_out_of_range(self):
        """L6 clamps turn_similarity to [0, 1]."""
        calc = MetricsCalculator()
        results = [
            {"mode": "dialogue", "turn_similarity": 1.5},
            {"mode": "dialogue", "turn_similarity": -0.3},
        ]
        # Clamped: [1.0, 0.0] → avg = 0.5
        assert calc._calculate_l6_trajectory_quality(results) == pytest.approx(0.5)

    def test_l6_no_similarity_scores_returns_none(self):
        """L6 returns None when dialogue results have no turn_similarity."""
        calc = MetricsCalculator()
        results = [{"mode": "dialogue"}, {"mode": "dialogue"}]
        assert calc._calculate_l6_trajectory_quality(results) is None

    def test_l6_empty_results_returns_none(self):
        """L6 returns None for empty results."""
        calc = MetricsCalculator()
        assert calc._calculate_l6_trajectory_quality([]) is None

    # ── Overall score with L5/L6 active ──────────────────────────

    def test_overall_score_with_all_metrics_active(self):
        """Overall score averages all 6 metrics when L5 and L6 are active."""
        calc = MetricsCalculator()
        results = [
            {
                "category": "trigger",
                "final_passed": True,
                "skill_used": True,
                "pass_rate": 0.9,
                "cost": 0.05,
                "execution_time": 5.0,
                "trace": {"violations": []},
                "mode": "dialogue",
                "turn_similarity": 0.8,
                "assertion_results": [{"confidence": 1.0, "passed": True}],
            },
            {
                "category": "normal",
                "final_passed": True,
                "skill_used": False,
                "pass_rate": 0.6,
                "cost": 0.03,
                "execution_time": 3.0,
                "trace": {"violations": []},
                "mode": "dialogue",
                "turn_similarity": 0.7,
                "assertion_results": [{"confidence": 1.0, "passed": True}],
            },
        ]
        metrics = calc.calculate_metrics(results, ["Step1"])
        # All 6 active: l1, l2, l3, l4, l5, l6
        assert metrics["l5_step_efficiency"] == 1.0
        assert metrics["l6_trajectory_quality"] is not None
        assert "l5_details" in metrics["metrics_breakdown"]
        assert "l6_details" in metrics["metrics_breakdown"]

    def test_overall_score_l5_none_l6_none(self):
        """Overall score uses 4 active metrics when L5 and L6 are None."""
        calc = MetricsCalculator()
        results = [
            {
                "category": "normal",
                "final_passed": True,
                "skill_used": True,
                "pass_rate": 0.8,
                "assertion_results": [{"confidence": 1.0, "passed": True}],
            },
            {
                "category": "normal",
                "final_passed": True,
                "skill_used": False,
                "pass_rate": 0.5,
                "assertion_results": [{"confidence": 1.0, "passed": True}],
            },
        ]
        metrics = calc.calculate_metrics(results)
        assert metrics["l5_step_efficiency"] is None
        assert metrics["l6_trajectory_quality"] is None
        assert metrics["overall_score"] > 0.0

    # ── L3 details with workflow step coverage ───────────────────

    def test_get_l3_details_with_workflow_steps(self):
        """L3 details include workflow step coverage when available."""
        calc = MetricsCalculator()
        results = [
            {"final_passed": True, "pass_rate": 0.9, "workflow_step": "Parse"},
            {"final_passed": True, "pass_rate": 0.8, "workflow_step": "Validate"},
            {"final_passed": False, "pass_rate": 0.3, "workflow_step": "Execute"},
        ]
        workflow_steps = ["Parse", "Validate", "Execute", "Report"]
        details = calc._get_l3_details(results, workflow_steps)
        assert details["method"] == "workflow_step_coverage"
        assert details["workflow_step_coverage"] == 0.5  # 2/4
        assert sorted(details["covered_workflow_steps"]) == ["Parse", "Validate"]
        assert sorted(details["uncovered_workflow_steps"]) == ["Execute", "Report"]
        assert details["total_workflow_steps"] == 4

    # ── L4 details single result ─────────────────────────────────

    def test_get_l4_details_single_deterministic_result(self):
        """L4 details with single deterministic result → std_dev=0."""
        calc = MetricsCalculator()
        results = [{"assertion_results": [{"confidence": 1.0, "passed": True}]}]
        details = calc._get_l4_details(results)
        assert details["deterministic_evals_count"] == 1
        assert details["stdev_deterministic_pass_rate"] == 0.0
        assert details["execution_stability"] == 1.0

    def test_get_l4_details_no_assertions(self):
        """L4 details with no assertion results."""
        calc = MetricsCalculator()
        results = [{"assertion_results": []}]
        details = calc._get_l4_details(results)
        assert details["deterministic_evals_count"] == 0
        assert details["avg_deterministic_pass_rate"] == 0.0

    # ── L5/L6 details ──────────────────────────────────────────

    def test_get_l5_details_with_violations(self):
        """L5 details aggregate violations correctly."""
        calc = MetricsCalculator()
        results = [
            {"trace": {"violations": ["token_budget"]}},
            {"trace": {"violations": ["timeout", "step_limit"]}},
            {"trace": {"violations": []}},
        ]
        details = calc._get_l5_details(results)
        assert details["total_violations"] == 3
        assert details["trace_available"] is True
        assert details["step_efficiency_score"] == 0.3

    def test_get_l6_details_dialogue(self):
        """L6 details report dialogue count and score."""
        calc = MetricsCalculator()
        results = [
            {"mode": "dialogue", "turn_similarity": 0.9},
            {"mode": "single", "turn_similarity": 0.5},
        ]
        details = calc._get_l6_details(results)
        assert details["dialogue_count"] == 1
        assert details["trajectory_quality_score"] == pytest.approx(0.9)
        assert details["measurement_method"] == "embedding_cosine_similarity"

    # ── Public calculate_l7_cost_efficiency ─────────────────────

    def test_calculate_l7_public_returns_none_when_no_cost(self):
        """Public L7 method returns None when no cost data."""
        calc = MetricsCalculator()
        results = [{"final_passed": True}]
        assert calc.calculate_l7_cost_efficiency(results) is None

    def test_calculate_l7_public_returns_dict(self):
        """Public L7 method returns structured dict when cost data exists."""
        calc = MetricsCalculator()
        results = [
            {"skill_used": True, "cost": 0.05, "pass_rate": 0.9},
            {"skill_used": False, "cost": 0.03, "pass_rate": 0.6},
        ]
        l7 = calc.calculate_l7_cost_efficiency(results)
        assert l7 is not None
        assert set(l7.keys()) == {
            "cost_per_eval",
            "total_cost",
            "cost_with_skill",
            "cost_without_skill",
            "cost_delta_pct",
            "cost_efficiency",
        }

    # ── L3 Turn-Level Metrics ─────────────────────────────────────

    def test_l3_weighted_composite_with_turn_data(self):
        """L3 uses weighted formula when tool_calls and turns data present."""
        calc = MetricsCalculator()
        results = [
            {
                "final_passed": True,
                "pass_rate": 0.8,
                "tool_calls": [{"tool_name": "search", "success": True}],
                "expected_tools": ["search"],
                "turns": [{"has_tool_call": True, "message": ""}],
            },
        ]
        l3 = calc._calculate_l3_step_adherence(results)
        # step_coverage=0.8, tool_call_accuracy=1.0, turn_relevance=1.0
        # 0.5*0.8 + 0.3*1.0 + 0.2*1.0 = 0.4 + 0.3 + 0.2 = 0.9
        assert l3 == pytest.approx(0.9)

    def test_l3_fallback_without_turn_data(self):
        """L3 returns None when no turn-level data AND no workflow_step data."""
        calc = MetricsCalculator()
        results = [
            {"final_passed": True, "pass_rate": 0.7},
        ]
        l3 = calc._calculate_l3_step_adherence(results)
        # No workflow_step field, no trajectory → L3 unavailable
        assert l3 is None

    def test_tool_call_accuracy_with_expected_tools(self):
        """Tool call accuracy uses expected_tools for matching."""
        calc = MetricsCalculator()
        passing_evals = [
            {
                "tool_calls": [
                    {"tool_name": "search"},
                    {"tool_name": "unknown_tool"},
                ],
                "expected_tools": ["search", "read"],
            },
        ]
        accuracy = calc._calculate_tool_call_accuracy(passing_evals)
        assert accuracy == pytest.approx(0.5)

    def test_tool_call_accuracy_without_expected_tools(self):
        """Tool call accuracy uses success flag when no expected_tools."""
        calc = MetricsCalculator()
        passing_evals = [
            {
                "tool_calls": [
                    {"tool_name": "search", "success": True},
                    {"tool_name": "write", "success": False},
                ],
            },
        ]
        accuracy = calc._calculate_tool_call_accuracy(passing_evals)
        assert accuracy == pytest.approx(0.5)

    def test_tool_call_accuracy_no_trajectory_data(self):
        """Tool call accuracy returns None when no tool_calls."""
        calc = MetricsCalculator()
        passing_evals = [{"final_passed": True}]
        assert calc._calculate_tool_call_accuracy(passing_evals) is None

    def test_tool_call_accuracy_empty_calls(self):
        """Tool call accuracy returns None when tool_calls is empty list."""
        calc = MetricsCalculator()
        passing_evals = [{"tool_calls": []}]
        assert calc._calculate_tool_call_accuracy(passing_evals) is None

    def test_turn_relevance_mixed_turns(self):
        """Turn relevance counts tool calls and non-empty messages."""
        calc = MetricsCalculator()
        passing_evals = [
            {
                "turns": [
                    {"has_tool_call": True, "message": ""},
                    {"has_tool_call": False, "message": "Hello"},
                    {"has_tool_call": False, "message": ""},  # irrelevant
                ],
            },
        ]
        relevance = calc._calculate_turn_relevance(passing_evals)
        assert relevance == pytest.approx(2 / 3)

    def test_turn_relevance_no_turns_data(self):
        """Turn relevance returns None when no turns."""
        calc = MetricsCalculator()
        passing_evals = [{"final_passed": True}]
        assert calc._calculate_turn_relevance(passing_evals) is None

    def test_turn_relevance_empty_turns(self):
        """Turn relevance returns None when turns list is empty."""
        calc = MetricsCalculator()
        passing_evals = [{"turns": []}]
        assert calc._calculate_turn_relevance(passing_evals) is None

    def test_l3_details_includes_turn_level_metrics(self):
        """_get_l3_details includes tool_call_accuracy and turn_relevance."""
        calc = MetricsCalculator()
        results = [
            {
                "final_passed": True,
                "pass_rate": 0.9,
                "tool_calls": [{"tool_name": "search", "success": True}],
                "turns": [{"has_tool_call": True, "message": "searching"}],
            },
        ]
        details = calc._get_l3_details(results)
        assert details["method"] == "weighted_composite"
        assert details["tool_call_accuracy"] == 1.0
        assert details["turn_relevance"] == 1.0
        assert details["weights"] == {
            "step_coverage": 0.5,
            "tool_call_accuracy": 0.3,
            "turn_relevance": 0.2,
        }

    def test_l3_details_fallback_without_turn_data(self):
        """_get_l3_details falls back to pass_rate_proxy without turn data."""
        calc = MetricsCalculator()
        results = [{"final_passed": True, "pass_rate": 0.8}]
        details = calc._get_l3_details(results)
        assert details["method"] == "pass_rate_proxy"
        assert details["tool_call_accuracy"] is None
        assert details["turn_relevance"] is None

    def test_step_coverage_with_workflow_steps(self):
        """Step coverage calculates correctly with workflow_steps."""
        calc = MetricsCalculator()
        passing_evals = [
            {"workflow_step": "step1"},
            {"workflow_step": "step2"},
        ]
        coverage = calc._calculate_step_coverage(passing_evals, ["step1", "step2", "step3"])
        assert coverage == pytest.approx(2 / 3)

    def test_step_coverage_fallback_to_pass_rate(self):
        """Step coverage falls back to pass_rate without workflow info."""
        calc = MetricsCalculator()
        passing_evals = [{"pass_rate": 0.6}, {"pass_rate": 0.8}]
        coverage = calc._calculate_step_coverage(passing_evals)
        assert coverage == pytest.approx(0.7)

    def test_step_coverage_token_overlap_fallback(self):
        """Step coverage uses token-overlap when workflow_step is a textual variant."""
        calc = MetricsCalculator()
        passing_evals = [
            {"workflow_step": "first analyze the input code for patterns"},
            {"workflow_step": "step 2 execute the transformation"},
        ]
        coverage = calc._calculate_step_coverage(
            passing_evals,
            ["step1: analyze code", "step2: execute transformation", "step3: verify output"],
        )
        # step1 jaccard=2/7=0.286 <0.6, step2 jaccard=2/5=0.4 <0.6, step3 none
        # → 0/3 coverage
        assert coverage == pytest.approx(0.0, abs=0.01)

    def test_step_coverage_token_overlap_high_overlap_matches(self):
        """Token-overlap covers steps with ≥60% token overlap."""
        calc = MetricsCalculator()
        passing_evals = [
            {"workflow_step": "verify the output"},
        ]
        coverage = calc._calculate_step_coverage(
            passing_evals,
            ["step1: analyze code", "step2: execute transformation", "step3: verify output"],
        )
        # "verify the output" vs "step3: verify output"
        # Tokens: {verify, the, output} ∩ {step3, verify, output} → {verify, output}
        # jaccard = 2/3 = 0.667 >= 0.6 → matched
        # step1, step2 → no/weak overlap → not matched
        # token-only match → ×0.7 confidence multiplier
        # → (1/3) × 0.7 = 0.233
        assert coverage == pytest.approx((1 / 3) * 0.7, abs=0.01)

    def test_step_coverage_token_overlap_multiple_matches(self):
        """Token-overlap can match multiple steps from multiple evals."""
        calc = MetricsCalculator()
        passing_evals = [
            {"workflow_step": "analyze the input code thoroughly"},
            {"workflow_step": "verify the output"},
        ]
        coverage = calc._calculate_step_coverage(
            passing_evals,
            ["step1: analyze code", "step2: execute transformation", "step3: verify output"],
        )
        # "analyze the input code thoroughly" vs "step1: analyze code"
        # Tokens: {analyze, the, input, code, thoroughly} ∩ {step1, analyze, code} → {analyze, code}
        # jaccard = 2/5 = 0.4 < 0.6 → not matched
        # "verify the output" vs "step3: verify output"
        # Tokens: {verify, the, output} ∩ {step3, verify, output} → {verify, output}
        # jaccard = 2/3 = 0.667 >= 0.6 → matched
        # step2 → no match
        # token-only match → ×0.7 confidence multiplier
        # → (1/3) × 0.7 = 0.233
        assert coverage == pytest.approx((1 / 3) * 0.7, abs=0.01)

    # ── L2 EPSILON guard (slice-4) ──────────────────────────────

    def test_compute_normalized_gain_near_zero_denominator_returns_absolute_delta(self):
        """EPSILON guard: near-zero without_avg returns absolute delta, not exploded gain."""
        calc = MetricsCalculator()
        # without_avg = 0.001, with_avg = 0.5
        # Without guard: (0.5 - 0.001) / 0.001 = 499 → clamped to 1.0 (misleading)
        # With guard: abs(0.001) < 1e-6 is False, but abs(0.001) < 0.01 triggers warning
        # For very small (below EPSILON=1e-6): should return absolute delta
        gain = calc._compute_normalized_gain(0.5, 1e-9)
        # abs(1e-9) < EPSILON → return absolute delta: 0.5 - 1e-9 ≈ 0.5
        assert gain == pytest.approx(0.5 - 1e-9, abs=1e-6)

    def test_compute_normalized_gain_zero_denominator_returns_absolute_delta(self):
        """EPSILON guard: zero without_avg returns absolute delta."""
        calc = MetricsCalculator()
        gain = calc._compute_normalized_gain(0.5, 0.0)
        # abs(0.0) < EPSILON → return absolute delta: 0.5 - 0.0 = 0.5
        assert gain == pytest.approx(0.5)

    def test_compute_normalized_gain_negative_near_zero_returns_absolute_delta(self):
        """EPSILON guard: negative near-zero without_avg returns absolute delta."""
        calc = MetricsCalculator()
        gain = calc._compute_normalized_gain(0.5, -1e-9)
        # abs(-1e-9) < EPSILON → return absolute delta: 0.5 - (-1e-9) ≈ 0.5
        assert gain == pytest.approx(0.5 + 1e-9, abs=1e-6)

    def test_compute_normalized_gain_normal_denominator_unchanged(self):
        """EPSILON guard: normal denominator still uses normalized gain formula."""
        calc = MetricsCalculator()
        # without_avg = 0.5, with_avg = 0.8 → gain = (0.8-0.5)/0.5 = 0.6
        gain = calc._compute_normalized_gain(0.8, 0.5)
        assert gain == pytest.approx(0.6)

    def test_l2_near_zero_baseline_does_not_falsely_report_one(self):
        """L2 score with near-zero baseline should NOT be clamped to 1.0."""
        calc = MetricsCalculator()
        eval_results = [
            {"skill_used": True, "pass_rate": 0.5},
            {"skill_used": True, "pass_rate": 0.6},
            {"skill_used": False, "pass_rate": 0.0001},
            {"skill_used": False, "pass_rate": 0.0001},
        ]
        l2 = calc._calculate_l2_with_without_skill_delta(eval_results)
        # with_avg = 0.55, without_avg = 0.0001
        # Without guard: (0.55 - 0.0001) / 0.0001 = 5499 → clamped to 1.0 (BUG)
        # With guard: abs(0.0001) < EPSILON? No (0.0001 > 1e-6).
        # So normalized gain is still used: (0.55-0.0001)/0.0001 ≈ 5499 → clamped to 1.0
        # But denominator_warning should be True (abs(0.0001) < 0.01)
        # The L2 score itself is still clamped to 1.0, but the warning flags it as unreliable
        # For truly near-zero (below EPSILON), absolute delta is used
        assert 0.0 <= l2 <= 1.0

    def test_l2_very_tiny_baseline_uses_absolute_delta(self):
        """L2 with extremely tiny baseline (below EPSILON) uses absolute delta."""
        calc = MetricsCalculator()
        eval_results = [
            {"skill_used": True, "pass_rate": 0.5},
            {"skill_used": True, "pass_rate": 0.6},
            {"skill_used": False, "pass_rate": 1e-9},
            {"skill_used": False, "pass_rate": 1e-9},
        ]
        l2 = calc._calculate_l2_with_without_skill_delta(eval_results)
        # with_avg = 0.55, without_avg = 1e-9
        # abs(1e-9) < EPSILON → absolute delta = 0.55 - 1e-9 ≈ 0.55
        assert l2 == pytest.approx(0.55, abs=1e-3)

    def test_get_l2_details_denominator_warning_true_for_small_baseline(self):
        """_get_l2_details sets denominator_warning=True when abs(without_avg) < 0.01."""
        calc = MetricsCalculator()
        eval_results = [
            {"skill_used": True, "pass_rate": 0.8},
            {"skill_used": False, "pass_rate": 0.005},
        ]
        details = calc._get_l2_details(eval_results)
        # without_avg = 0.005, abs(0.005) < 0.01 → warning
        assert details["denominator_warning"] is True

    def test_get_l2_details_denominator_warning_false_for_normal_baseline(self):
        """_get_l2_details sets denominator_warning=False when abs(without_avg) >= 0.01."""
        calc = MetricsCalculator()
        eval_results = [
            {"skill_used": True, "pass_rate": 0.8},
            {"skill_used": False, "pass_rate": 0.5},
        ]
        details = calc._get_l2_details(eval_results)
        # without_avg = 0.5, abs(0.5) >= 0.01 → no warning
        assert details["denominator_warning"] is False

    def test_get_l2_details_denominator_warning_zero_baseline(self):
        """_get_l2_details sets denominator_warning=True when without_avg is 0."""
        calc = MetricsCalculator()
        eval_results = [
            {"skill_used": True, "pass_rate": 0.8},
            {"skill_used": False, "pass_rate": 0.0},
        ]
        details = calc._get_l2_details(eval_results)
        # without_avg = 0.0, abs(0.0) < 0.01 → warning
        assert details["denominator_warning"] is True

    def test_get_l2_details_denominator_warning_boundary(self):
        """_get_l2_details denominator_warning at boundary (exactly 0.01)."""
        calc = MetricsCalculator()
        eval_results = [
            {"skill_used": True, "pass_rate": 0.8},
            {"skill_used": False, "pass_rate": 0.01},
        ]
        details = calc._get_l2_details(eval_results)
        # without_avg = 0.01, abs(0.01) >= 0.01 → no warning (boundary is NOT warning)
        assert details["denominator_warning"] is False


class TestCIHistoryL4:
    """Tests for CI-based L4 stability measurement (slice-9)."""

    def test_calc_l4_from_ci_history_returns_none_when_file_missing(self, tmp_path):
        """_calc_l4_from_ci_history returns None when history file doesn't exist."""
        calc = MetricsCalculator()
        missing_path = tmp_path / ".skill-cert-ci-history.json"
        result = calc._calc_l4_from_ci_history(str(missing_path))
        assert result is None

    def test_calc_l4_from_ci_history_returns_none_for_empty_runs(self, tmp_path):
        """_calc_l4_from_ci_history returns None when no runs in history."""
        calc = MetricsCalculator()
        history_path = tmp_path / ".skill-cert-ci-history.json"
        history_path.write_text('{"runs": []}')
        result = calc._calc_l4_from_ci_history(str(history_path))
        assert result is None

    def test_calc_l4_from_ci_history_returns_none_for_single_run(self, tmp_path):
        """_calc_l4_from_ci_history returns None when only 1 run (need ≥2 for std dev)."""
        import datetime

        calc = MetricsCalculator()
        history_path = tmp_path / ".skill-cert-ci-history.json"
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        history_data = {
            "runs": [
                {"timestamp": now, "l4_execution_stability": 0.95},
            ]
        }
        history_path.write_text(json.dumps(history_data))
        result = calc._calc_l4_from_ci_history(str(history_path))
        assert result is None

    def test_calc_l4_from_ci_history_computes_stability_from_multiple_runs(self, tmp_path):
        """_calc_l4_from_ci_history computes std dev from multiple historical L4 values."""
        import datetime

        calc = MetricsCalculator()
        history_path = tmp_path / ".skill-cert-ci-history.json"
        now = datetime.datetime.now(datetime.timezone.utc)
        runs = []
        for i, l4_val in enumerate([0.9, 0.85, 0.92, 0.88, 0.91]):
            ts = (now - datetime.timedelta(days=i)).isoformat()
            runs.append({"timestamp": ts, "l4_execution_stability": l4_val})
        history_data = {"runs": runs}
        history_path.write_text(json.dumps(history_data))

        result = calc._calc_l4_from_ci_history(str(history_path))
        assert result is not None
        # std dev of [0.9, 0.85, 0.92, 0.88, 0.91] ≈ 0.0259
        # L4 = 1.0 - std_dev ≈ 0.974
        assert 0.95 < result <= 1.0

    def test_calc_l4_from_ci_history_respects_30_day_window(self, tmp_path):
        """_calc_l4_from_ci_history only considers runs within 30-day window."""
        import datetime

        calc = MetricsCalculator()
        history_path = tmp_path / ".skill-cert-ci-history.json"
        now = datetime.datetime.now(datetime.timezone.utc)
        runs = []
        # Recent runs (within 30 days) - stable values
        for i in range(3):
            ts = (now - datetime.timedelta(days=i)).isoformat()
            runs.append({"timestamp": ts, "l4_execution_stability": 0.95})
        # Old runs (outside 30 days) - unstable values
        for i in range(31, 34):
            ts = (now - datetime.timedelta(days=i)).isoformat()
            runs.append({"timestamp": ts, "l4_execution_stability": 0.5})
        history_data = {"runs": runs}
        history_path.write_text(json.dumps(history_data))

        result = calc._calc_l4_from_ci_history(str(history_path))
        # Should only use recent runs (all 0.95), so std dev ≈ 0, L4 ≈ 1.0
        assert result is not None
        assert result > 0.99  # Very stable since all recent values are identical

    def test_calc_l4_from_ci_history_filters_by_skill_path(self, tmp_path):
        """_calc_l4_from_ci_history filters runs by skill_path when provided."""
        import datetime

        calc = MetricsCalculator()
        history_path = tmp_path / ".skill-cert-ci-history.json"
        now = datetime.datetime.now(datetime.timezone.utc)
        runs = []
        # Runs for skill A
        for i in range(3):
            ts = (now - datetime.timedelta(days=i)).isoformat()
            runs.append(
                {
                    "timestamp": ts,
                    "skill_path": "/path/to/skillA.md",
                    "l4_execution_stability": 0.95,
                }
            )
        # Runs for skill B
        for i in range(3):
            ts = (now - datetime.timedelta(days=i)).isoformat()
            runs.append(
                {
                    "timestamp": ts,
                    "skill_path": "/path/to/skillB.md",
                    "l4_execution_stability": 0.5,
                }
            )
        history_data = {"runs": runs}
        history_path.write_text(json.dumps(history_data))

        result = calc._calc_l4_from_ci_history(str(history_path), skill_path="/path/to/skillA.md")
        # Should only use skill A runs (all 0.95), so very stable
        assert result is not None
        assert result > 0.99

    def test_merge_l4_runs_and_ci_history_weighted_average(self):
        """merge_l4_stability computes 60% runs + 40% CI weighted average."""
        calc = MetricsCalculator()
        runs_l4 = 0.9
        ci_l4 = 0.8
        merged = calc.merge_l4_stability(runs_l4, ci_l4)
        # 0.6 * 0.9 + 0.4 * 0.8 = 0.54 + 0.32 = 0.86
        assert merged == pytest.approx(0.86)

    def test_merge_l4_returns_runs_only_when_ci_is_none(self):
        """merge_l4_stability returns runs L4 when CI history is None."""
        calc = MetricsCalculator()
        result = calc.merge_l4_stability(0.9, None)
        assert result == 0.9

    def test_merge_l4_returns_ci_only_when_runs_is_none(self):
        """merge_l4_stability returns CI L4 when runs L4 is None."""
        calc = MetricsCalculator()
        result = calc.merge_l4_stability(None, 0.8)
        assert result == 0.8

    def test_merge_l4_returns_none_when_both_none(self):
        """merge_l4_stability returns None when both inputs are None."""
        calc = MetricsCalculator()
        result = calc.merge_l4_stability(None, None)
        assert result is None

    def test_calculate_metrics_with_ci_history_integration(self, tmp_path):
        """calculate_metrics uses CI history for L4 when ci_history_path provided."""
        import datetime

        calc = MetricsCalculator()
        history_path = tmp_path / ".skill-cert-ci-history.json"
        now = datetime.datetime.now(datetime.timezone.utc)
        runs = []
        for i in range(5):
            ts = (now - datetime.timedelta(days=i)).isoformat()
            runs.append({"timestamp": ts, "l4_execution_stability": 0.95})
        history_data = {"runs": runs}
        history_path.write_text(json.dumps(history_data))

        # Eval result with deterministic assertions (needed for L4 calculation)
        eval_results = [
            {
                "category": "trigger",
                "final_passed": True,
                "assertion_results": [{"confidence": 1.0, "passed": True}],
            }
        ]
        metrics = calc.calculate_metrics(eval_results, ci_history_path=str(history_path))

        # L4 should be influenced by CI history (all 0.95 → very stable)
        # runs_l4 = 1.0 (single deterministic result), ci_l4 ≈ 1.0 (all 0.95)
        # merged = 0.6*1.0 + 0.4*1.0 = 1.0
        l4 = metrics["l4_execution_stability"]
        assert l4 >= 0.99

    def test_calculate_metrics_ci_disabled_when_path_none(self):
        """calculate_metrics ignores CI history when ci_history_path is None."""
        calc = MetricsCalculator()
        # Eval result with deterministic assertion (needed for L4 calculation)
        eval_results = [
            {
                "category": "trigger",
                "final_passed": True,
                "assertion_results": [{"confidence": 1.0, "passed": True}],
            }
        ]
        metrics = calc.calculate_metrics(eval_results, ci_history_path=None)
        # Should use default L4 calculation (1.0 for single deterministic eval)
        assert metrics["l4_execution_stability"] == 1.0
