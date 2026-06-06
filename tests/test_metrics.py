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

        # With avg: (0.0 + 0.8) / 2 = 0.40
        # Without avg: (0.5 + 0.5) / 2 = 0.50
        # Normalized gain: (0.40 - 0.50) / 0.50 = -0.20 → capped to 0.0
        assert l2_score == pytest.approx(0.0)

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
            },
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
        """L3 falls back to step_coverage when no turn-level data."""
        calc = MetricsCalculator()
        results = [
            {"final_passed": True, "pass_rate": 0.7},
        ]
        l3 = calc._calculate_l3_step_adherence(results)
        assert l3 == pytest.approx(0.7)

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
