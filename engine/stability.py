"""Stability module — multi-run execution with std dev calculation for L4."""

from typing import Dict, Any, List, Callable
import statistics
import time


class StabilityRunner:
    """Runs evals multiple times and computes stability metrics."""

    def __init__(self, base_runner, num_runs: int = 3, max_concurrency: int = 5):
        self.base_runner = base_runner
        self.num_runs = num_runs
        self.max_concurrency = max_concurrency

    def run_stability(self, evals: List[Dict[str, Any]], skill_path: str, model_adapter, with_skill: bool = True) -> Dict[str, Any]:
        """Run evals N times and return pass rates + stability stats per eval."""
        all_run_results = []
        for run_idx in range(self.num_runs):
            if with_skill:
                results = self.base_runner.run_with_skill(evals, skill_path, model_adapter)
            else:
                results = self.base_runner.run_without_skill(evals, model_adapter)
            all_run_results.append(results)

        # Compute per-eval stability
        eval_ids = [e.get("id") for e in evals]
        stability_per_eval = {}
        for eval_id in eval_ids:
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

            stability_per_eval[eval_id] = {
                "pass_rates": pass_rates,
                "mean_pass_rate": mean_pr,
                "std_dev": std_pr,
                "runs_completed": len(pass_rates),
            }

        # Aggregate stability
        all_means = [v["mean_pass_rate"] for v in stability_per_eval.values()]
        all_stds = [v["std_dev"] for v in stability_per_eval.values()]
        overall_std = statistics.stdev(all_stds) if len(all_stds) > 1 else 0.0
        overall_mean_stability = statistics.mean(all_means) if all_means else 0.0

        return {
            "runs_completed": self.num_runs,
            "per_eval_stability": stability_per_eval,
            "overall_mean_pass_rate": overall_mean_stability,
            "overall_std_dev": overall_std,
            "stability_pct": max(0, 1.0 - overall_std) if overall_std <= 1.0 else 0.0,
        }


def calculate_l4_stability(stability_data: Dict[str, Any]) -> float:
    """Calculate L4 stability score from multi-run data.

    Returns:
        float 0.0-1.0 where 1.0 means fully stable (std <= 10% of mean)
    """
    overall_std = stability_data.get("overall_std_dev", 0.0)
    overall_mean = stability_data.get("overall_mean_pass_rate", 0.0)

    if overall_mean == 0:
        return 0.0

    coefficient_of_variation = overall_std / overall_mean if overall_mean > 0 else float('inf')

    if coefficient_of_variation <= 0.10:
        return 1.0
    elif coefficient_of_variation <= 0.20:
        return 0.8
    elif coefficient_of_variation <= 0.35:
        return 0.5
    else:
        return 0.0
