"""Stability module — multi-run execution with std dev calculation for L4."""

import logging
import math
import statistics
from typing import Any

from engine.constants import StabilityThresholds
from engine.deadline import PhaseTimer

logger = logging.getLogger(__name__)

# ── t-distribution approximation (no scipy dependency) ──────────────────────

# Lookup table for common confidence levels and degrees of freedom (1-30)
# t-values for 95% CI two-tailed
_T_TABLE_95 = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    11: 2.201,
    12: 2.179,
    13: 2.160,
    14: 2.145,
    15: 2.131,
    16: 2.120,
    17: 2.110,
    18: 2.101,
    19: 2.093,
    20: 2.086,
    21: 2.080,
    22: 2.074,
    23: 2.069,
    24: 2.064,
    25: 2.060,
    26: 2.056,
    27: 2.052,
    28: 2.048,
    29: 2.045,
    30: 2.042,
}


def _get_t_value(df: int, confidence: float = 0.95) -> float:
    """Get t-value for given degrees of freedom and confidence level.

    Uses lookup table for 95% CI; falls back to normal approximation for
    other confidence levels or df > 30.
    """
    if confidence == 0.95 and df in _T_TABLE_95:
        return _T_TABLE_95[df]

    # Normal approximation for large df or non-standard confidence
    # Using Abramowitz & Stegun approximation for inverse normal
    if confidence <= 0 or confidence >= 1:
        return 1.96
    alpha = 1 - confidence
    p = 1 - alpha / 2
    # Rational approximation for inverse normal (Abramowitz & Stegun 26.2.23)
    t = p
    c = [2.515517, 0.802853, 0.010328]
    d = [1.432788, 0.189269, 0.001308]
    if p > 0.5:
        t = 1 - p
    w = math.sqrt(-2 * math.log(t))
    z = w - (c[0] + c[1] * w + c[2] * w * w) / (1 + d[0] * w + d[1] * w * w + d[2] * w * w * w)
    if p < 0.5:
        z = -z
    return z


def _compute_confidence_interval(
    values: list[float], confidence: float = 0.95
) -> tuple[float, float]:
    """Compute confidence interval for a list of values.

    Returns (lower, upper) bounds of the CI.
    """
    n = len(values)
    if n < 2:
        mean_val = values[0] if values else 0.0
        return (mean_val, mean_val)

    mean_val = statistics.mean(values)
    se = statistics.stdev(values) / math.sqrt(n)
    t_val = _get_t_value(n - 1, confidence)
    margin = t_val * se
    return (max(0.0, mean_val - margin), min(1.0, mean_val + margin))


class StabilityRunner:
    """Runs evals multiple times and computes stability metrics."""

    def __init__(
        self,
        base_runner,
        num_runs: int = 3,
        max_concurrency: int = 5,
        num_trials: int | None = None,
        confidence: float = StabilityThresholds.CONFIDENCE_LEVEL,
    ):
        self.base_runner = base_runner
        self.num_runs = num_trials if num_trials is not None else num_runs
        self.max_concurrency = max_concurrency
        self.confidence = confidence

    def _run_trials(
        self,
        evals: list[dict[str, Any]],
        skill_path: str,
        model_adapter,
        with_skill: bool,
        deadline: Any | None = None,
    ) -> list[list[dict[str, Any]]]:
        """Run evals N times and return list of results per run."""
        timer = PhaseTimer(phase_name="stability", item_count=self.num_runs, deadline=deadline)
        all_run_results = []
        for i in range(self.num_runs):
            if deadline is not None and deadline.expired:
                logger.warning("Deadline expired before stability run %d/%d", i + 1, self.num_runs)
                break

            if with_skill:
                results = self.base_runner.run_with_skill(evals, skill_path, model_adapter)
            else:
                results = self.base_runner.run_without_skill(evals, model_adapter)

            timer.items_completed = i + 1
            timer.log_progress(f"Run {i + 1}/{self.num_runs}")
            all_run_results.append(results)
        return all_run_results

    def _compute_eval_stability(
        self,
        eval_id: str,
        all_run_results: list[list[dict[str, Any]]],
    ) -> dict[str, Any]:
        """Compute stability metrics for a single eval."""
        pass_rates = []
        for run_results in all_run_results:
            run_result = next((r for r in run_results if r.get("eval_id") == eval_id), None)
            if run_result and not run_result.get("error"):
                grade = run_result.get("grade", {})
                pr = grade.get("pass_rate", 0.0)
                pass_rates.append(pr)
            else:
                pass_rates.append(0.0)

        mean_pr = statistics.mean(pass_rates) if pass_rates else 0.0
        std_pr = statistics.stdev(pass_rates) if len(pass_rates) > 1 else 0.0
        cv = std_pr / mean_pr if mean_pr > 0 else 0.0
        ci_lower, ci_upper = _compute_confidence_interval(pass_rates, self.confidence)

        return {
            "pass_rates": pass_rates,
            "mean_pass_rate": mean_pr,
            "std_dev": std_pr,
            "runs_completed": len(pass_rates),
            "coefficient_of_variation": cv,
            "confidence_interval": (ci_lower, ci_upper),
        }

    def _aggregate_stability(
        self,
        stability_per_eval: dict[str, Any],
    ) -> tuple[float, float, float, tuple[float, float]]:
        """Aggregate stability metrics across all evals."""
        all_means = [v["mean_pass_rate"] for v in stability_per_eval.values()]
        all_stds = [v["std_dev"] for v in stability_per_eval.values()]
        overall_std = statistics.stdev(all_stds) if len(all_stds) > 1 else 0.0
        overall_mean_stability = statistics.mean(all_means) if all_means else 0.0
        overall_cv = overall_std / overall_mean_stability if overall_mean_stability > 0 else 0.0

        if len(all_means) >= 2:
            overall_ci = _compute_confidence_interval(all_means, self.confidence)
        else:
            overall_ci = (overall_mean_stability, overall_mean_stability)

        return overall_std, overall_mean_stability, overall_cv, overall_ci

    def run_stability(
        self,
        evals: list[dict[str, Any]],
        skill_path: str,
        model_adapter,
        with_skill: bool = True,
        deadline: Any | None = None,
    ) -> dict[str, Any]:
        """Run evals N times and return pass rates + stability stats per eval."""
        all_run_results = self._run_trials(
            evals, skill_path, model_adapter, with_skill, deadline=deadline
        )

        eval_ids = [e.get("id") for e in evals]
        stability_per_eval = {}
        for eval_id in eval_ids:
            if eval_id is not None:
                stability_per_eval[eval_id] = self._compute_eval_stability(eval_id, all_run_results)

        overall_std, overall_mean_stability, overall_cv, overall_ci = self._aggregate_stability(
            stability_per_eval
        )

        return {
            "runs_completed": self.num_runs,
            "per_eval_stability": stability_per_eval,
            "overall_mean_pass_rate": overall_mean_stability,
            "overall_std_dev": overall_std,
            "coefficient_of_variation": overall_cv,
            "confidence_interval": overall_ci,
            "stability_pct": max(0, 1.0 - overall_std) if overall_std <= 1.0 else 0.0,
        }


def _score_from_ci_width(width_ratio: float) -> float | None:
    if width_ratio < 0.10:
        return 1.0
    elif width_ratio < 0.20:
        return 0.8
    elif width_ratio < 0.35:
        return 0.5
    else:
        return 0.0


def _score_from_cv(coefficient_of_variation: float) -> float:
    if coefficient_of_variation <= 0.10:
        return 1.0
    elif coefficient_of_variation <= 0.20:
        return 0.8
    elif coefficient_of_variation <= 0.35:
        return 0.5
    else:
        return 0.0


def calculate_l4_stability(stability_data: dict[str, Any]) -> float:
    ci = stability_data.get("confidence_interval")
    overall_mean = stability_data.get("overall_mean_pass_rate", 0.0)

    if ci and overall_mean > 0:
        ci_lower, ci_upper = ci
        ci_width = ci_upper - ci_lower
        width_ratio = ci_width / overall_mean
        result = _score_from_ci_width(width_ratio)
        if result is not None:
            return result

    overall_std = stability_data.get("overall_std_dev", 0.0)
    if overall_mean == 0:
        return 0.0

    coefficient_of_variation = overall_std / overall_mean
    return _score_from_cv(coefficient_of_variation)
