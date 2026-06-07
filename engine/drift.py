"""Drift detection module for skill-cert engine — detects cross-model performance variations."""

from dataclasses import dataclass
from typing import Any

from engine.constants import DriftThresholds
from engine.grader import EvalCase, Grader


@dataclass
class DriftResult:
    """Result of drift detection analysis."""

    model_a: str
    model_b: str
    pass_rate_a: float
    pass_rate_b: float
    variance: float
    severity: str  # none, low, moderate, high
    verdict: str  # PASS, PASS_WITH_CAVEATS, FAIL


class DriftDetector:
    """Detects cross-model drift in skill certification results."""

    def __init__(self):
        """Initialize drift detector."""
        pass

    def _extract_prompt(self, eval_case: EvalCase | dict) -> str:
        """Extract prompt from eval case."""
        if isinstance(eval_case, dict):
            return eval_case.get("prompt") or eval_case.get("input", "")
        return getattr(eval_case, "prompt", "") or ""

    def _build_assertions(self, eval_case: EvalCase | dict) -> list:
        """Build assertions list from eval case."""
        if isinstance(eval_case, dict):
            from engine.grader import EvalAssertion

            assertions = []
            for a in eval_case.get("assertions", []):
                if isinstance(a, dict):
                    assertions.append(
                        EvalAssertion(
                            name=a.get("name", ""),
                            type=a.get("type", "contains"),
                            value=a.get("value", ""),
                            weight=int(float(a.get("weight", 1))),
                        )
                    )
                elif isinstance(a, EvalAssertion):
                    assertions.append(a)
            return assertions
        return []

    def _convert_to_eval_case(self, eval_case: EvalCase | dict, prompt: str) -> EvalCase:
        """Convert dict to EvalCase if needed."""
        if isinstance(eval_case, dict):
            from engine.grader import EvalCase

            return EvalCase(
                id=eval_case.get("id", 0),
                name=eval_case.get("name", ""),
                category=eval_case.get("category", "normal"),
                prompt=prompt,
                assertions=self._build_assertions(eval_case),
            )
        return eval_case

    def _grade_eval(self, eval_case: EvalCase | dict, model_output: str, grader: Grader) -> dict:
        """Grade a single eval case."""
        if isinstance(eval_case, dict):
            case = self._convert_to_eval_case(eval_case, model_output)
            return grader.grade_output(case, model_output)
        return grader.grade_output(eval_case, model_output)

    def _calculate_model_pass_rate(self, eval_results: list) -> float:
        """Calculate pass rate for a model's eval results."""
        if eval_results:
            return sum(r["pass_rate"] for r in eval_results) / len(eval_results)
        return 0.0

    def _compare_model_pair(
        self, model_a: str, model_b: str, pass_rate_a: float, pass_rate_b: float
    ) -> DriftResult:
        """Compare two models and return drift result."""
        variance = abs(pass_rate_a - pass_rate_b)
        severity = self._determine_severity(variance)
        verdict = self._map_verdict(severity)

        return DriftResult(
            model_a=model_a,
            model_b=model_b,
            pass_rate_a=pass_rate_a,
            pass_rate_b=pass_rate_b,
            variance=variance,
            severity=severity,
            verdict=verdict,
        )

    def _run_model_evaluations(
        self, eval_cases: list[EvalCase], model_adapters: dict[str, Any], grader: Grader
    ) -> dict[str, dict]:
        """Run evaluations for all models and return results."""
        model_eval_results = {}
        model_names = list(model_adapters.keys())

        for model_name in model_names:
            adapter = model_adapters[model_name]
            eval_results = []

            for eval_case in eval_cases:
                prompt = self._extract_prompt(eval_case)
                if not prompt:
                    prompt = ""
                model_output = adapter.chat([{"role": "user", "content": prompt}])
                grade_result = self._grade_eval(eval_case, model_output, grader)
                eval_results.append(grade_result)

            total_pass_rate = self._calculate_model_pass_rate(eval_results)
            model_eval_results[model_name] = {"results": eval_results, "pass_rate": total_pass_rate}

        return model_eval_results

    def _build_all_pairwise_comparisons(
        self, model_names: list[str], model_eval_results: dict[str, dict]
    ) -> list[DriftResult]:
        """Build all pairwise drift comparisons."""
        results = []
        for i in range(len(model_names)):
            for j in range(i + 1, len(model_names)):
                model_a = model_names[i]
                model_b = model_names[j]

                pass_rate_a = model_eval_results[model_a]["pass_rate"]
                pass_rate_b = model_eval_results[model_b]["pass_rate"]

                drift_result = self._compare_model_pair(model_a, model_b, pass_rate_a, pass_rate_b)
                results.append(drift_result)

        return results

    def detect_drift(
        self, eval_cases: list[EvalCase], model_adapters: dict[str, Any], grader: Grader
    ) -> list[DriftResult]:
        """
        Run same evals across multiple models and detect drift.

        Args:
            eval_cases: List of evaluation cases to run
            model_adapters: Dictionary mapping model names to adapter objects
            grader: Grader instance to evaluate outputs

        Returns:
            List of drift results comparing model pairs
        """
        model_eval_results = self._run_model_evaluations(eval_cases, model_adapters, grader)
        model_names = list(model_adapters.keys())
        return self._build_all_pairwise_comparisons(model_names, model_eval_results)

    def _determine_severity(self, variance: float) -> str:
        """Determine drift severity based on variance thresholds."""
        if variance <= DriftThresholds.NONE:
            return "none"
        elif variance <= DriftThresholds.LOW:
            return "low"
        elif variance <= DriftThresholds.MODERATE:
            return "moderate"
        else:
            return "high"

    def _map_verdict(self, severity: str) -> str:
        """Map severity level to verdict."""
        if severity in ["none", "low"]:
            return "PASS"
        elif severity == "moderate":
            return "PASS_WITH_CAVEATS"
        else:  # high
            return "FAIL"

    def _build_empty_drift_report(self) -> dict[str, Any]:
        """Build empty drift report when no results exist."""
        return {
            "drift_detected": False,
            "highest_severity": "none",
            "average_variance": 0.0,
            "model_pairs_compared": 0,
            "summary": "No drift analysis performed",
        }

    def _build_drift_metrics(self, drift_results: list[DriftResult]) -> dict[str, Any]:
        highest_severity = self._get_highest_severity(drift_results)
        avg_variance = sum(r.variance for r in drift_results) / len(drift_results)
        max_variance = max(r.variance for r in drift_results)
        severity_counts = self._count_severities(drift_results)
        overall_verdict = self._aggregate_verdict(drift_results)
        return {
            "drift_detected": highest_severity in ["moderate", "high"],
            "highest_severity": highest_severity,
            "average_variance": avg_variance,
            "max_variance": max_variance,
            "model_pairs_compared": len(drift_results),
            "severity_distribution": severity_counts,
            "overall_verdict": overall_verdict,
        }

    @staticmethod
    def _count_severities(drift_results):
        counts = {"none": 0, "low": 0, "moderate": 0, "high": 0}
        for r in drift_results:
            if r.severity in counts:
                counts[r.severity] += 1
        return counts

    def _build_uncertainty_metrics(self, drift_results: list[DriftResult]) -> dict[str, Any]:
        """Build cross-model uncertainty metrics."""
        pass_rates = []
        for r in drift_results:
            pass_rates.extend([r.pass_rate_a, r.pass_rate_b])
        unique_rates = list(set(pass_rates))
        cmp = self.calculate_cmp(drift_results)
        cme = self.calculate_cme(unique_rates)

        return {
            "cross_model_uncertainty": {
                "cmp_agreement_rate": cmp,
                "cme_variation": cme,
            },
            "summary": (
                f"Drift analysis completed. Highest severity: "
                f"{self._get_highest_severity(drift_results)}. "
                f"Average variance: "
                f"{sum(r.variance for r in drift_results) / len(drift_results):.3f}"
            ),
        }

    def aggregate_drift_report(self, drift_results: list[DriftResult]) -> dict[str, Any]:
        """Generate aggregated drift report from individual results."""
        if not drift_results:
            return self._build_empty_drift_report()

        metrics = self._build_drift_metrics(drift_results)
        uncertainty = self._build_uncertainty_metrics(drift_results)

        return {**metrics, **uncertainty}

    def _get_highest_severity(self, drift_results: list[DriftResult]) -> str:
        """Get the highest severity level from a list of drift results."""
        severity_order = {"none": 0, "low": 1, "moderate": 2, "high": 3}
        return max(drift_results, key=lambda r: severity_order[r.severity]).severity

    def _aggregate_verdict(self, drift_results: list[DriftResult]) -> str:
        """Aggregate verdicts from all comparisons."""
        # If any comparison resulted in FAIL, overall verdict is FAIL
        if any(r.verdict == "FAIL" for r in drift_results):
            return "FAIL"
        # If any comparison resulted in PASS_WITH_CAVEATS, overall verdict is PASS_WITH_CAVEATS
        elif any(r.verdict == "PASS_WITH_CAVEATS" for r in drift_results):
            return "PASS_WITH_CAVEATS"
        else:
            return "PASS"

    def calculate_cmp(self, drift_results: list[DriftResult]) -> dict[str, Any]:
        """Calculate Cross-Model Performance (CMP) metrics.

        CMP measures agreement between models using:
        - agreement_rate: proportion of model pairs with severity <= 'low'
        - pairwise_agreements: list of per-pair agreement details

        Returns dict with agreement_rate and pairwise details.
        """
        if not drift_results:
            return {"agreement_rate": 1.0, "pairwise_agreements": []}

        agreeing = sum(1 for r in drift_results if r.severity in ("none", "low"))
        agreement_rate = agreeing / len(drift_results)

        pairwise = []
        for r in drift_results:
            pairwise.append(
                {
                    "model_a": r.model_a,
                    "model_b": r.model_b,
                    "agrees": r.severity in ("none", "low"),
                    "variance": r.variance,
                }
            )

        return {
            "agreement_rate": round(agreement_rate, 4),
            "pairwise_agreements": pairwise,
        }

    def calculate_cme(self, pass_rates: list[float]) -> dict[str, Any]:
        """Calculate Cross-Model Entropy (CME) metrics.

        CME measures variability across models using:
        - coefficient_of_variation (CV): std/mean
        - max_min_spread: max(pass_rates) - min(pass_rates)
        - mean_pass_rate: average of all pass rates

        Returns dict with CV, spread, and mean.
        """
        if not pass_rates:
            return {"coefficient_of_variation": 0.0, "max_min_spread": 0.0, "mean_pass_rate": 0.0}

        n = len(pass_rates)
        mean_pr = sum(pass_rates) / n
        max_pr = max(pass_rates)
        min_pr = min(pass_rates)
        spread = max_pr - min_pr

        if n < 2 or mean_pr == 0:
            cv = 0.0
        else:
            variance = sum((x - mean_pr) ** 2 for x in pass_rates) / n
            std_dev = variance**0.5
            cv = std_dev / mean_pr

        return {
            "coefficient_of_variation": round(cv, 4),
            "max_min_spread": round(spread, 4),
            "mean_pass_rate": round(mean_pr, 4),
        }
