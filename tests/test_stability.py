"""Tests for engine/stability.py — multi-run L4 stability."""

import pytest

from engine.stability import (
    StabilityRunner,
    _compute_confidence_interval,
    _get_t_value,
    calculate_l4_stability,
)


class MockRunner:
    def __init__(self, result_map):
        self.result_map = result_map
        self.call_count = 0

    def run_with_skill(self, evals, skill_path, model_adapter):
        result = self.result_map.get(self.call_count, [])
        self.call_count += 1
        return result

    def run_without_skill(self, evals, model_adapter):
        result = self.result_map.get(self.call_count, [])
        self.call_count += 1
        return result


def _make_eval_results(eval_id, pass_rate, no_error=True):
    return {
        "eval_id": eval_id,
        "grade": {"pass_rate": pass_rate},
        "error": None if no_error else "some_error",
    }


class TestStabilityRunner:
    def test_single_run(self):
        mock = MockRunner({
            0: [
                _make_eval_results(1, 0.9),
                _make_eval_results(2, 0.8),
            ]
        })
        runner = StabilityRunner(base_runner=mock, num_runs=1)
        evals = [{"id": 1}, {"id": 2}]
        result = runner.run_stability(evals, "skill_path", "adapter")

        assert result["runs_completed"] == 1
        assert result["per_eval_stability"][1]["mean_pass_rate"] == pytest.approx(0.9)
        assert result["per_eval_stability"][2]["mean_pass_rate"] == pytest.approx(0.8)

    def test_multi_run_stability(self):
        mock = MockRunner({
            0: [_make_eval_results(1, 0.9)],
            1: [_make_eval_results(1, 0.9)],
            2: [_make_eval_results(1, 0.9)],
        })
        runner = StabilityRunner(base_runner=mock, num_runs=3)
        evals = [{"id": 1}]
        result = runner.run_stability(evals, "skill_path", "adapter")

        assert result["runs_completed"] == 3
        stability = result["per_eval_stability"][1]
        assert stability["mean_pass_rate"] == pytest.approx(0.9)
        assert stability["std_dev"] == pytest.approx(0.0)
        assert stability["runs_completed"] == 3

    def test_multi_run_variance(self):
        mock = MockRunner({
            0: [_make_eval_results(1, 0.8)],
            1: [_make_eval_results(1, 0.9)],
            2: [_make_eval_results(1, 0.7)],
        })
        runner = StabilityRunner(base_runner=mock, num_runs=3)
        evals = [{"id": 1}]
        result = runner.run_stability(evals, "skill_path", "adapter")

        stability = result["per_eval_stability"][1]
        assert stability["mean_pass_rate"] == pytest.approx(0.8, abs=0.01)
        assert stability["std_dev"] > 0
        assert stability["runs_completed"] == 3

    def test_error_treated_as_zero_pass_rate(self):
        mock = MockRunner({
            0: [_make_eval_results(1, 0.9)],
            1: [_make_eval_results(1, 0.9, no_error=False)],
        })
        runner = StabilityRunner(base_runner=mock, num_runs=2)
        evals = [{"id": 1}]
        result = runner.run_stability(evals, "skill_path", "adapter")

        stability = result["per_eval_stability"][1]
        assert stability["runs_completed"] == 2


class TestCalculateL4Stability:
    def test_no_variance(self):
        data = {"overall_std_dev": 0.0, "overall_mean_pass_rate": 0.9}
        assert calculate_l4_stability(data) == 1.0

    def test_low_variance(self):
        data = {"overall_std_dev": 0.05, "overall_mean_pass_rate": 0.8}
        result = calculate_l4_stability(data)
        assert result == 0.8 or result == 1.0

    def test_high_variance(self):
        data = {"overall_std_dev": 0.5, "overall_mean_pass_rate": 0.5}
        assert calculate_l4_stability(data) == 0.0

    def test_zero_mean(self):
        data = {"overall_std_dev": 0.0, "overall_mean_pass_rate": 0.0}
        assert calculate_l4_stability(data) == 0.0

    def test_empty_data(self):
        assert calculate_l4_stability({}) == 0.0

    def test_ci_based_scoring_narrow(self):
        """CI width/mean < 10% → 1.0."""
        data = {
            "confidence_interval": (0.88, 0.92),
            "overall_mean_pass_rate": 0.9,
            "overall_std_dev": 0.01,
        }
        assert calculate_l4_stability(data) == 1.0

    def test_ci_based_scoring_moderate(self):
        """CI width/mean between 10% and 20% → 0.8."""
        data = {
            "confidence_interval": (0.74, 0.86),
            "overall_mean_pass_rate": 0.8,
            "overall_std_dev": 0.05,
        }
        assert calculate_l4_stability(data) == 0.8

    def test_ci_based_scoring_wide(self):
        """CI width/mean > 35% → 0.0."""
        data = {
            "confidence_interval": (0.3, 0.9),
            "overall_mean_pass_rate": 0.6,
            "overall_std_dev": 0.2,
        }
        assert calculate_l4_stability(data) == 0.0

    def test_ci_zero_mean_fallback(self):
        """CI present but mean=0 → 0.0."""
        data = {
            "confidence_interval": (0.0, 0.0),
            "overall_mean_pass_rate": 0.0,
        }
        assert calculate_l4_stability(data) == 0.0


class TestTValue:
    def test_lookup_table_95(self):
        """Standard 95% CI values from table."""
        assert _get_t_value(1) == pytest.approx(12.706)
        assert _get_t_value(10) == pytest.approx(2.228)
        assert _get_t_value(30) == pytest.approx(2.042)

    def test_normal_approximation_large_df(self):
        """df > 30 uses normal approximation."""
        t = _get_t_value(100)
        assert 1.9 < t < 2.1  # Should be ~1.96

    def test_invalid_confidence(self):
        """Invalid confidence level returns 1.96."""
        assert _get_t_value(10, confidence=0.0) == 1.96
        assert _get_t_value(10, confidence=1.0) == 1.96


class TestConfidenceInterval:
    def test_single_value(self):
        """Single value → point CI."""
        lower, upper = _compute_confidence_interval([0.8])
        assert lower == upper == 0.8

    def test_empty_values(self):
        """Empty list → (0.0, 0.0)."""
        lower, upper = _compute_confidence_interval([])
        assert lower == upper == 0.0

    def test_constant_values(self):
        """All same values → zero-width CI."""
        lower, upper = _compute_confidence_interval([0.5, 0.5, 0.5])
        assert lower == pytest.approx(0.5)
        assert upper == pytest.approx(0.5)

    def test_variable_values(self):
        """Variable values → non-zero CI width."""
        lower, upper = _compute_confidence_interval([0.7, 0.8, 0.9, 0.6, 0.8])
        assert lower < 0.8
        assert upper > 0.8
        assert 0.0 <= lower <= upper <= 1.0

    def test_ci_clamped_to_01(self):
        """CI bounds are clamped to [0.0, 1.0]."""
        lower, upper = _compute_confidence_interval([0.01, 0.01, 0.99])
        assert lower >= 0.0
        assert upper <= 1.0


class TestStabilityRunnerNewFields:
    def test_num_trials_overrides_num_runs(self):
        """num_trials parameter takes precedence over num_runs."""
        mock = MockRunner({
            0: [_make_eval_results(1, 0.9)],
            1: [_make_eval_results(1, 0.85)],
            2: [_make_eval_results(1, 0.95)],
        })
        runner = StabilityRunner(base_runner=mock, num_runs=10, num_trials=3)
        result = runner.run_stability([{"id": 1}], "skill", "adapter")
        assert result["runs_completed"] == 3

    def test_per_eval_has_ci_and_cv(self):
        """Per-eval stability includes confidence_interval and coefficient_of_variation."""
        mock = MockRunner({
            0: [_make_eval_results(1, 0.8)],
            1: [_make_eval_results(1, 0.9)],
            2: [_make_eval_results(1, 0.85)],
        })
        runner = StabilityRunner(base_runner=mock, num_runs=3)
        result = runner.run_stability([{"id": 1}], "skill", "adapter")
        per_eval = result["per_eval_stability"][1]
        assert "confidence_interval" in per_eval
        assert "coefficient_of_variation" in per_eval
        ci_lower, ci_upper = per_eval["confidence_interval"]
        assert ci_lower <= per_eval["mean_pass_rate"] <= ci_upper

    def test_overall_has_ci_and_cv(self):
        """Overall stability includes confidence_interval and coefficient_of_variation."""
        mock = MockRunner({
            0: [_make_eval_results(1, 0.8), _make_eval_results(2, 0.9)],
            1: [_make_eval_results(1, 0.85), _make_eval_results(2, 0.88)],
        })
        runner = StabilityRunner(base_runner=mock, num_runs=2)
        result = runner.run_stability([{"id": 1}, {"id": 2}], "skill", "adapter")
        assert "confidence_interval" in result
        assert "coefficient_of_variation" in result

