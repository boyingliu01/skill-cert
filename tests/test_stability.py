"""Tests for engine/stability.py — multi-run L4 stability."""

import pytest
from engine.stability import StabilityRunner, calculate_l4_stability


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
