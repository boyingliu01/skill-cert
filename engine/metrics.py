"""Metrics module for skill-cert engine — calculates L1-L8 evaluation metrics."""

from dataclasses import dataclass
from typing import Any

from engine.constants import TimingLimits
from engine.envelope import EnvelopeChecker


class _DictTrace:
    """Adapter to allow EnvelopeChecker.check() to work with dict traces."""

    def __init__(self, data: dict):
        self.steps = data.get("steps", 0)
        self.tool_call_count = data.get("tool_calls", data.get("tool_call_count", 0))
        self.tokens = data.get("tokens", 0)
        self.time_ms = data.get("time_ms", 0)
        self.cost = data.get("cost", 0.0)


@dataclass
class MetricResult:
    """Result of a single metric calculation."""

    name: str
    value: float
    description: str


class MetricsCalculator:
    """Calculates L1-L4 metrics for skill certification."""

    def __init__(self):
        """Initialize metrics calculator."""
        pass

    def calculate_metrics(
        self, eval_results: list[dict[str, Any]], workflow_steps: list[str] | None = None
    ) -> dict[str, Any]:
        """Calculate all L1-L6 metrics from evaluation results."""
        l1_score = self._calculate_l1_trigger_accuracy(eval_results)
        l2_score = self._calculate_l2_with_without_skill_delta(eval_results)
        l3_score = self._calculate_l3_step_adherence(eval_results, workflow_steps)
        l4_score = self._calculate_l4_execution_stability(eval_results)
        l5_score = self._calculate_l5_step_efficiency(eval_results)
        l6_score = self._calculate_l6_trajectory_quality(eval_results)

        active_metrics = 6
        score_sum = l1_score + l2_score + l3_score + l4_score
        if l5_score is not None:
            score_sum += l5_score
        else:
            active_metrics -= 1
        if l6_score is not None:
            score_sum += l6_score
        else:
            active_metrics -= 1
        overall_score = score_sum / active_metrics if eval_results and active_metrics > 0 else 0.0

        l7 = self._calculate_l7_cost_efficiency(eval_results)
        l8 = self._calculate_l8_latency_metrics(eval_results)

        return {
            "overall_score": overall_score,
            "l1_trigger_accuracy": l1_score,
            "l2_with_without_skill_delta": l2_score,
            "l3_step_adherence": l3_score,
            "l4_execution_stability": l4_score,
            "l5_step_efficiency": l5_score,
            "l6_trajectory_quality": l6_score,
            "l7_cost_efficiency": l7,
            "l8_latency_metrics": l8,
            "metrics_breakdown": {
                "l1_details": self._get_l1_details(eval_results),
                "l2_details": self._get_l2_details(eval_results),
                "l3_details": self._get_l3_details(eval_results, workflow_steps),
                "l4_details": self._get_l4_details(eval_results),
                "l5_details": self._get_l5_details(eval_results),
                "l6_details": self._get_l6_details(eval_results),
                "l8_latency_details": l8 if l8 else {},
            },
        }

    def calculate_l7_cost_efficiency(
        self, eval_results: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """Calculate L7 cost efficiency metrics. Returns None when no cost data."""
        l7 = self._calculate_l7_cost_efficiency(eval_results)
        if l7 is None:
            return None
        return {
            "cost_per_eval": l7["cost_per_eval"],
            "total_cost": l7["total_cost"],
            "cost_with_skill": l7["cost_with_skill"],
            "cost_without_skill": l7["cost_without_skill"],
            "cost_delta_pct": l7["cost_delta_pct"],
            "cost_efficiency": l7["cost_efficiency"],
        }

    def _calculate_l1_trigger_accuracy(self, eval_results: list[dict[str, Any]]) -> float:
        """L1: Trigger accuracy (filter eval_category=='trigger', calculate accuracy).

        Uses F1 score when negative_case eval results are present to account for both
        true positives (correct triggers on positive cases) and true negatives
        (correct non-triggers on negative cases). Falls back to simple accuracy.
        """
        f1 = self._calculate_f1_score(eval_results)
        if f1 is not None:
            return f1

        trigger_results = [r for r in eval_results if r.get("category") == "trigger"]
        if not trigger_results:
            return 0.0
        passed_triggers = sum(1 for r in trigger_results if r.get("final_passed", False))
        return passed_triggers / len(trigger_results) if trigger_results else 0.0

    @staticmethod
    def _calculate_f1_score(eval_results: list[dict[str, Any]]) -> float | None:
        """Calculate F1 score from positive and negative trigger eval results.

        Uses negative_case flag to classify TP/TN/FP/FN:
        - TP: pos case, final_passed=True  → model correctly triggered
        - TN: neg case, final_passed=True  → model correctly did NOT trigger
        - FP: neg case, final_passed=False → model incorrectly triggered
        - FN: pos case, final_passed=False → model incorrectly did NOT trigger

        Returns None when no trigger eval results or no negative_case evals found
        (caller should fall back to accuracy).
        """
        trigger_results = [r for r in eval_results if r.get("category") == "trigger"]
        if not trigger_results:
            return None

        has_negative = any(r.get("negative_case", False) for r in trigger_results)
        if not has_negative:
            return None

        tp = 0
        fp = 0
        fn = 0
        for r in trigger_results:
            is_neg = r.get("negative_case", False)
            passed = r.get("final_passed", False)
            if not is_neg and passed:
                tp += 1
            elif is_neg and not passed:
                fp += 1
            elif not is_neg and not passed:
                fn += 1

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        if precision + recall == 0.0:
            return 0.0
        return 2 * precision * recall / (precision + recall)

    @staticmethod
    def _extract_with_without_groups(eval_results):
        with_skill = [r for r in eval_results if r.get("skill_used", True)]
        without_skill = [r for r in eval_results if not r.get("skill_used", True)]
        return with_skill, without_skill

    @staticmethod
    def _avg_pass_rate(results):
        if not results:
            return 0.0
        return sum(r.get("pass_rate", 0.0) for r in results) / len(results)

    @staticmethod
    def _compute_normalized_gain(with_avg, without_avg):
        if without_avg > 0:
            return (with_avg - without_avg) / without_avg
        return with_avg - without_avg

    def _calculate_l2_with_without_skill_delta(self, eval_results: list[dict[str, Any]]) -> float:
        with_skill, without_skill = self._extract_with_without_groups(eval_results)
        if not with_skill or not without_skill:
            if not eval_results:
                return 0.0
            return self._avg_pass_rate(eval_results)
        with_avg = self._avg_pass_rate(with_skill)
        without_avg = self._avg_pass_rate(without_skill)
        normalized_gain = self._compute_normalized_gain(with_avg, without_avg)
        return max(0.0, min(1.0, normalized_gain))

    def _calculate_l3_step_adherence(
        self,
        eval_results: list[dict[str, Any]],
        workflow_steps: list[str] | None = None,
    ) -> float:
        """L3: Step adherence.

        Weighted combination of step_coverage, tool_call_accuracy, turn_relevance.
        Formula: 0.5 * step_coverage + 0.3 * tool_call_accuracy + 0.2 * turn_relevance
        Falls back to step_coverage only when turn-level data is unavailable.
        """
        if not eval_results:
            return 0.0

        passing_evals = [r for r in eval_results if r.get("final_passed", False)]
        if not passing_evals:
            return 0.0

        # Calculate base step_coverage
        step_coverage = self._calculate_step_coverage(passing_evals, workflow_steps)

        # Check for turn-level data
        tool_call_accuracy = self._calculate_tool_call_accuracy(passing_evals)
        turn_relevance = self._calculate_turn_relevance(passing_evals)

        if tool_call_accuracy is not None and turn_relevance is not None:
            return 0.5 * step_coverage + 0.3 * tool_call_accuracy + 0.2 * turn_relevance

        # Fallback: step_coverage only (backward compatible)
        return step_coverage

    def _calculate_step_coverage(
        self, passing_evals: list[dict[str, Any]], workflow_steps: list[str] | None = None
    ) -> float:
        """Calculate step coverage from passing evaluations."""
        has_workflow_step_info = any(r.get("workflow_step") is not None for r in passing_evals)
        if has_workflow_step_info and workflow_steps is not None:
            total_steps = len(workflow_steps)
            if total_steps == 0:
                return 0.0
            covered_steps: set[str] = set()
            for r in passing_evals:
                ws = r.get("workflow_step")
                if ws:
                    covered_steps.add(ws)
            return len(covered_steps) / total_steps
        else:
            return sum(r.get("pass_rate", 0.0) for r in passing_evals) / len(passing_evals)

    def _calculate_tool_call_accuracy(self, passing_evals: list[dict[str, Any]]) -> float | None:
        """Calculate tool call accuracy from trajectory data in eval results.

        Returns None if no trajectory data is available.
        """
        trajectory_results = [r for r in passing_evals if r.get("tool_calls") is not None]
        if not trajectory_results:
            return None

        total_calls = 0
        correct_calls = 0
        for r in trajectory_results:
            calls = r.get("tool_calls", [])
            expected_tools = r.get("expected_tools", [])
            for call in calls:
                total_calls += 1
                if expected_tools:
                    if call.get("tool_name") in expected_tools:
                        correct_calls += 1
                elif call.get("success", False):
                    correct_calls += 1

        if total_calls == 0:
            return None
        return correct_calls / total_calls

    def _calculate_turn_relevance(self, passing_evals: list[dict[str, Any]]) -> float | None:
        """Calculate turn relevance from trajectory data in eval results.

        Returns None if no trajectory data is available.
        """
        trajectory_results = [r for r in passing_evals if r.get("turns") is not None]
        if not trajectory_results:
            return None

        total_turns = 0
        relevant_turns = 0
        for r in trajectory_results:
            turns = r.get("turns", [])
            for turn in turns:
                total_turns += 1
                if turn.get("has_tool_call") or (turn.get("message") and turn["message"].strip()):
                    relevant_turns += 1

        if total_turns == 0:
            return None
        return relevant_turns / total_turns

    @staticmethod
    def _extract_deterministic_pass_rates(eval_results):
        rates = []
        for result in eval_results:
            det_assertions = [
                ar for ar in result.get("assertion_results", []) if ar.get("confidence", 0.0) == 1.0
            ]
            if det_assertions:
                det_passed = sum(1 for ar in det_assertions if ar.get("passed", False))
                rates.append(det_passed / len(det_assertions))
        return rates

    @staticmethod
    def _compute_std_dev(values):
        if len(values) < 2:
            return 0.0
        avg = sum(values) / len(values)
        variance = sum((x - avg) ** 2 for x in values) / len(values)
        return variance**0.5

    def _calculate_l4_execution_stability(self, eval_results: list[dict[str, Any]]) -> float:
        if not eval_results:
            return 1.0
        deterministic_results = self._extract_deterministic_pass_rates(eval_results)
        if len(deterministic_results) < 2:
            return 1.0 if deterministic_results else 0.0
        std_dev = self._compute_std_dev(deterministic_results)
        return max(0.0, 1.0 - std_dev)

    def _get_l1_details(self, eval_results: list[dict[str, Any]]) -> dict[str, Any]:
        """Get detailed information for L1 metric."""
        trigger_results = [r for r in eval_results if r.get("category") == "trigger"]
        passed_triggers = sum(1 for r in trigger_results if r.get("final_passed", False))
        f1 = self._calculate_f1_score(eval_results)

        details: dict[str, Any] = {
            "total_trigger_evals": len(trigger_results),
            "passed_trigger_evals": passed_triggers,
            "trigger_accuracy": passed_triggers / len(trigger_results) if trigger_results else 0.0,
        }
        if f1 is not None:
            positive = [r for r in trigger_results if not r.get("negative_case", False)]
            negative = [r for r in trigger_results if r.get("negative_case", False)]
            tp = sum(1 for r in positive if r.get("final_passed", False))
            tn = sum(1 for r in negative if r.get("final_passed", False))
            fp = sum(1 for r in negative if not r.get("final_passed", False))
            fn = sum(1 for r in positive if not r.get("final_passed", False))
            details["f1_score"] = f1
            details["confusion_matrix"] = {
                "true_positives": tp,
                "true_negatives": tn,
                "false_positives": fp,
                "false_negatives": fn,
            }
        return details

    def _get_l2_details(self, eval_results: list[dict[str, Any]]) -> dict[str, Any]:
        """Get detailed information for L2 metric."""
        with_skill_results = [r for r in eval_results if r.get("skill_used", True)]
        without_skill_results = [r for r in eval_results if not r.get("skill_used", True)]

        with_skill_avg = (
            sum(r.get("pass_rate", 0.0) for r in with_skill_results) / len(with_skill_results)
            if with_skill_results
            else 0.0
        )
        without_skill_avg = (
            sum(r.get("pass_rate", 0.0) for r in without_skill_results) / len(without_skill_results)
            if without_skill_results
            else 0.0
        )

        return {
            "with_skill_avg_pass_rate": with_skill_avg,
            "without_skill_avg_pass_rate": without_skill_avg,
            "delta": with_skill_avg - without_skill_avg,
            "improvement_percentage": (
                (with_skill_avg - without_skill_avg) / without_skill_avg * 100
            )
            if without_skill_avg > 0
            else 0.0,
        }

    def _get_l3_details(
        self, eval_results: list[dict[str, Any]], workflow_steps: list[str] | None = None
    ) -> dict[str, Any]:
        passing_evals = [r for r in eval_results if r.get("final_passed", False)]
        total_evals = len(eval_results)
        l3_value = self._calculate_l3_step_adherence(eval_results, workflow_steps)
        step_coverage = (
            self._calculate_step_coverage(passing_evals, workflow_steps) if passing_evals else 0.0
        )
        tool_call_accuracy = self._calculate_tool_call_accuracy(passing_evals)
        turn_relevance = self._calculate_turn_relevance(passing_evals)
        details = self._build_l3_base_details(
            total_evals, passing_evals, step_coverage, tool_call_accuracy, turn_relevance
        )
        details = self._apply_l3_workflow_details(details, passing_evals, workflow_steps, l3_value)
        return details

    @staticmethod
    def _build_l3_base_details(total_evals, passing_evals, step_cov, tool_acc, turn_rel):
        method = (
            "weighted_composite"
            if (tool_acc is not None and turn_rel is not None)
            else "pass_rate_proxy"
        )
        details = {
            "total_evaluations": total_evals,
            "passing_evaluations": len(passing_evals),
            "step_coverage_ratio": len(passing_evals) / total_evals if total_evals > 0 else 0.0,
            "method": method,
            "step_coverage": step_cov,
            "tool_call_accuracy": tool_acc,
            "turn_relevance": turn_rel,
        }
        if method == "weighted_composite":
            details["weights"] = {
                "step_coverage": 0.5,
                "tool_call_accuracy": 0.3,
                "turn_relevance": 0.2,
            }
        return details

    @staticmethod
    def _apply_l3_workflow_details(details, passing_evals, workflow_steps, l3_value):
        has_workflow_step_info = any(r.get("workflow_step") is not None for r in passing_evals)
        if has_workflow_step_info and workflow_steps is not None:
            covered_steps = {r["workflow_step"] for r in passing_evals if r.get("workflow_step")}
            if details["method"] == "pass_rate_proxy":
                details["method"] = "workflow_step_coverage"
            details["workflow_step_coverage"] = l3_value
            details["covered_workflow_steps"] = sorted(covered_steps)
            details["total_workflow_steps"] = len(workflow_steps)
            details["uncovered_workflow_steps"] = sorted(set(workflow_steps) - covered_steps)
        else:
            details["workflow_step_coverage"] = None
        return details

    def _get_l4_details(self, eval_results: list[dict[str, Any]]) -> dict[str, Any]:
        deterministic_results = self._extract_deterministic_pass_rates(eval_results)
        if not deterministic_results:
            return {
                "deterministic_evals_count": 0,
                "avg_deterministic_pass_rate": 0.0,
                "stdev_deterministic_pass_rate": 0.0,
                "execution_stability": 0.0,
            }
        avg_pass_rate = sum(deterministic_results) / len(deterministic_results)
        std_dev = self._compute_std_dev(deterministic_results)
        stability_score = max(0.0, 1.0 - std_dev)
        return {
            "deterministic_evals_count": len(deterministic_results),
            "avg_deterministic_pass_rate": avg_pass_rate,
            "stdev_deterministic_pass_rate": std_dev,
            "execution_stability": stability_score,
        }

    @staticmethod
    def _count_envelope_violations(eval_results, checker) -> tuple[bool, int]:
        violations = 0
        trace_found = False
        for r in eval_results:
            trace = r.get("trace")
            if trace is not None:
                trace_found = True
                if isinstance(trace, dict) and "violations" in trace:
                    violations += len(trace["violations"])
                else:
                    trace_obj = trace if not isinstance(trace, dict) else _DictTrace(trace)
                    result = checker.check(trace_obj)
                    if not result.passed:
                        violations += len(result.violations)
        return trace_found, violations

    @staticmethod
    def _score_l5_from_violations(violations: int) -> float:
        if violations == 0:
            return 1.0
        if violations == 1:
            return 0.7
        return 0.3

    def _calculate_l5_step_efficiency(
        self, eval_results, envelope: EnvelopeChecker | None = None
    ) -> float | None:
        checker = envelope or EnvelopeChecker()
        trace_found, violations = self._count_envelope_violations(eval_results, checker)
        if not trace_found:
            return None
        return self._score_l5_from_violations(violations)

    def _calculate_l6_trajectory_quality(self, eval_results) -> float | None:
        dialogue_results = [r for r in eval_results if r.get("mode") == "dialogue"]
        if not dialogue_results:
            return None
        scores = []
        for r in dialogue_results:
            sim = r.get("turn_similarity")
            if sim is not None:
                scores.append(min(1.0, max(0.0, float(sim))))
        if not scores:
            return None
        return round(sum(scores) / len(scores), 2)

    def _get_l5_details(self, eval_results) -> dict:
        violations = 0
        trace_found = False
        for r in eval_results:
            trace = r.get("trace")
            if trace is not None:
                trace_found = True
                violations += len(trace.get("violations", []))
        score = self._calculate_l5_step_efficiency(eval_results)
        return {
            "step_efficiency_score": score,
            "total_violations": violations,
            "trace_available": trace_found,
        }

    def _get_l6_details(self, eval_results) -> dict:
        dialogue_results = [r for r in eval_results if r.get("mode") == "dialogue"]
        score = self._calculate_l6_trajectory_quality(eval_results)
        return {
            "trajectory_quality_score": score,
            "dialogue_count": len(dialogue_results),
            "measurement_method": "embedding_cosine_similarity",
        }

    # ── L7: Cost Efficiency ──────────────────────────────────────

    def _calculate_l7_cost_efficiency(self, eval_results) -> dict | None:
        costs = [r.get("cost") for r in eval_results if "cost" in r]
        if not costs:
            return None
        with_skill = [r for r in eval_results if r.get("skill_used") and "cost" in r]
        without_skill = [r for r in eval_results if not r.get("skill_used") and "cost" in r]
        return self._build_cost_result(costs, with_skill, without_skill, eval_results)

    def _build_cost_result(self, costs, with_skill, without_skill, eval_results):
        total_cost = sum(costs)
        cost_per_eval = total_cost / len(costs)
        cost_with = self._avg_cost(with_skill)
        cost_without = self._avg_cost(without_skill)
        cost_delta_pct = (cost_with - cost_without) / cost_without if cost_without > 0 else 0.0
        l2_delta = self._calculate_l2_with_without_skill_delta(eval_results)
        cost_efficiency = round(l2_delta / cost_delta_pct, 4) if cost_delta_pct > 0 else 0.0
        return {
            "cost_per_eval": round(cost_per_eval, 4),
            "total_cost": round(total_cost, 4),
            "cost_with_skill": round(cost_with, 4),
            "cost_without_skill": round(cost_without, 4),
            "cost_delta_pct": round(cost_delta_pct, 4),
            "cost_efficiency": cost_efficiency,
        }

    @staticmethod
    def _avg_cost(results):
        if not results:
            return 0.0
        return sum(r["cost"] for r in results) / len(results)

    # ── L8: Latency Metrics ──────────────────────────────────────

    def _calculate_l8_latency_metrics(self, eval_results) -> dict | None:
        with_times = self._extract_times(eval_results, skill_used=True)
        without_times = self._extract_times(eval_results, skill_used=False)
        if not with_times and not without_times:
            return None
        stats = {}
        if with_times:
            stats["with_skill"] = self._compute_latency_stats(with_times)
        if without_times:
            stats["without_skill"] = self._compute_latency_stats(without_times)
        if with_times and without_times:
            stats.update(self._compute_overhead(with_times, without_times))
        return stats

    @staticmethod
    def _extract_times(eval_results, skill_used):
        return [
            r["execution_time"]
            for r in eval_results
            if r.get("skill_used") == skill_used
            and "execution_time" in r
            and r["execution_time"] > 0
        ]

    @staticmethod
    def _compute_overhead(with_times, without_times):
        with_avg = sum(with_times) / len(with_times)
        without_avg = sum(without_times) / len(without_times)
        overhead_pct = ((with_avg - without_avg) / max(without_avg, 0.001)) * 100
        threshold = TimingLimits.SLOW_REQUEST_THRESHOLD
        return {
            "overhead_pct": round(overhead_pct, 1),
            "slow_threshold_sec": threshold,
            "slow_with_skill": sum(1 for t in with_times if t > threshold),
            "slow_without_skill": sum(1 for t in without_times if t > threshold),
        }

    def _compute_latency_stats(self, times: list[float]) -> dict:
        """Compute P50, P95, P99 for a list of execution times."""
        sorted_times = sorted(times)
        n = len(sorted_times)
        return {
            "p50": round(sorted_times[n // 2], 3),
            "p95": round(sorted_times[int(n * 0.95)] if n > 1 else sorted_times[0], 3),
            "p99": round(sorted_times[int(n * 0.99)] if n > 1 else sorted_times[0], 3),
            "mean": round(sum(sorted_times) / n, 3),
            "min": round(sorted_times[0], 3),
            "max": round(sorted_times[-1], 3),
            "count": n,
        }
