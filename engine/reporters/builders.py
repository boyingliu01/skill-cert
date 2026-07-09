"""Data preparation and section-building functions for report generation.

Extracted builder functions that assemble report data structures:
drift data, coverage data, config info, benchmark info, suggestions,
eval details, metrics sections, token/observability sections, and
Markdown section builders (stress, multi-skill).
"""

from datetime import datetime, timezone
from typing import Any

from engine.report_models import (
    AssertionResult as ReportAssertionResult,
)
from engine.report_models import (
    EvalDetail,
    ImprovementSuggestion,
    MetricDimension,
    MetricsSection,
    ObservabilitySection,
    TokenAnalysisSection,
    TokenBreakdown,
)
from engine.reporters.formatters import num


def determine_verdict(
    overall_score: float, drift: dict[str, Any] | None, degraded: bool = False
) -> str:
    """Determine verdict based on overall score and drift analysis.

    When ``degraded=True`` (coverage < 90% but above block threshold),
    the verdict is capped at PASS_WITH_CAVEATS — it cannot be PASS.
    """
    drift_verdict = "PASS" if drift is None else drift.get("overall_verdict", "PASS")
    if drift_verdict == "FAIL":
        return "FAIL"
    if drift_verdict == "PASS_WITH_CAVEATS" and overall_score < 0.8:
        return "PASS_WITH_CAVEATS"
    if overall_score >= 0.8:
        if degraded:
            return "PASS_WITH_CAVEATS"
        return "PASS"
    if overall_score >= 0.6:
        return "PASS_WITH_CAVEATS"
    return "FAIL"


def prepare_drift_data(drift: dict[str, Any] | None) -> dict[str, Any]:
    """Prepare drift data for template rendering."""
    if drift is None:
        return {
            "drift_detected": None,  # None = not applicable (single model)
            "highest_severity": "none",
            "average_variance": 0.0,
            "max_variance": 0.0,
            "drift_results": [],
            "model_pairs_compared": 0,
        }
    return {
        "drift_detected": drift.get("drift_detected", False),
        "highest_severity": drift.get("highest_severity", "none"),
        "average_variance": drift.get("average_variance", 0.0),
        "max_variance": drift.get("max_variance", 0.0),
        "drift_results": drift.get("drift_results", []),
    }


def compute_assertion_breakdown(results: list[dict]) -> dict[str, dict[str, int]]:
    """Compute assertion breakdown by weight category from results."""
    critical_passed = 0
    critical_total = 0
    important_passed = 0
    important_total = 0
    normal_passed = 0
    normal_total = 0

    for r in results:
        for a in r.get("grade", {}).get("assertion_results", []):
            weight = a.get("assertion", {}).get("weight", 1)
            if weight >= 3:
                critical_total += 1
                if a.get("passed"):
                    critical_passed += 1
            elif weight == 2:
                important_total += 1
                if a.get("passed"):
                    important_passed += 1
            else:
                normal_total += 1
                if a.get("passed"):
                    normal_passed += 1

    return {
        "critical": {"passed": critical_passed, "total": critical_total},
        "important": {"passed": important_passed, "total": important_total},
        "normal": {"passed": normal_passed, "total": normal_total},
    }


def prepare_coverage_data(
    metrics: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Prepare evaluation coverage data from results or config fallback."""
    _results = metrics.get("_results", [])
    total_evaluations = len(_results) or config.get("total_evaluations", 0)
    avg_pass_rate = (
        sum(r.get("pass_rate", 0) for r in _results) / len(_results)
        if _results
        else config.get("avg_pass_rate", 0.0)
    )

    if _results:
        assertion_breakdown = compute_assertion_breakdown(_results)
    else:
        assertion_breakdown = {
            "critical": {
                "passed": config.get("critical_passed", 0),
                "total": config.get("critical_total", 0),
            },
            "important": {
                "passed": config.get("important_passed", 0),
                "total": config.get("important_total", 0),
            },
            "normal": {
                "passed": config.get("normal_passed", 0),
                "total": config.get("normal_total", 0),
            },
        }

    return {
        "total_evaluations": total_evaluations,
        "avg_pass_rate": avg_pass_rate,
        "critical_passed": assertion_breakdown["critical"]["passed"],
        "critical_total": assertion_breakdown["critical"]["total"],
        "important_passed": assertion_breakdown["important"]["passed"],
        "important_total": assertion_breakdown["important"]["total"],
        "normal_passed": assertion_breakdown["normal"]["passed"],
        "normal_total": assertion_breakdown["normal"]["total"],
        "assertion_breakdown": assertion_breakdown,
    }


def prepare_config_info(config: dict[str, Any]) -> dict[str, Any] | None:
    """Prepare configuration info for report."""
    if not config:
        return None
    models = config.get("models", [])
    model_names = (
        ", ".join(
            str(m.get("model_name", m.get("name", "unknown")) if isinstance(m, dict) else m)
            for m in models
        )
        if isinstance(models, list)
        else str(models)
    )
    return {
        "models": model_names or "Not specified",
        "max_concurrency": config.get("max_concurrency", 5),
        "rate_limit_rpm": config.get("rate_limit_rpm", 60),
        "request_timeout": config.get("request_timeout", 120),
        "judge_temperature": config.get("judge_temperature", 0.0),
        "max_testgen_rounds": config.get("max_testgen_rounds", 3),
    }


def prepare_benchmark_info(
    metrics: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Prepare benchmark info for report."""
    total_tokens = config.get("total_tokens", 0)
    if not total_tokens:
        total_tokens = config.get("total_evaluator_tokens", 0)
    _results = metrics.get("_results", [])
    total_eval_tokens = sum(r.get("tokens_used", 0) for r in _results) if _results else 0
    return {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "spec_version": "v2.0",
        "total_requirements": 11,
        "total_acceptance_criteria": 74,
        "test_coverage": f"{len(_results)} evals, L1-L7 metrics computed",
        "total_tokens": f"{total_eval_tokens:,}" if total_eval_tokens else "N/A (local models)",
    }


def get_metric_suggestions(metrics: dict[str, Any]) -> list[str]:
    """Get suggestions for L1-L4 metrics."""
    suggestions = []
    l1_score = num(metrics.get("l1_trigger_accuracy", 0.0))
    if l1_score < 0.7:
        suggestions.append(
            "Improve trigger accuracy - skill may not be properly detecting trigger conditions"
        )

    l2_score = num(metrics.get("l2_with_without_skill_delta", 0.0))
    if l2_score < 0.5:
        suggestions.append(
            "Skill may not be providing sufficient value - consider enhancing core functionality"
        )

    l3_score = num(metrics.get("l3_step_adherence", 0.0))
    if l3_score < 0.7:
        suggestions.append("Improve adherence to expected workflow steps")

    l4_score = num(metrics.get("l4_execution_stability", 0.0))
    if l4_score < 0.8:
        suggestions.append("Address execution instability - results vary significantly across runs")
    return suggestions


def get_overall_suggestions(overall_score: float) -> list[str]:
    """Get suggestions based on overall score."""
    if overall_score >= 0.8:
        return []
    if overall_score >= 0.6:
        return ["Several areas need improvement to reach optimal performance"]
    return ["Major improvements needed across multiple areas"]


def get_cost_suggestions(cost_analysis: dict[str, Any]) -> list[str]:
    """Get suggestions based on cost analysis."""
    suggestions = []
    if cost_analysis.get("cost_delta_pct", 0) > 0.5:
        suggestions.append(
            f"Skill increases costs by "
            f"{cost_analysis['cost_delta_pct']:.0%} — "
            "consider optimizing prompt or reducing verbosity"
        )
    if cost_analysis.get("cost_efficiency", 0) < 0.1 and cost_analysis.get("cost_delta_pct", 0) > 0:
        suggestions.append("Low cost efficiency — quality gains don't justify cost increase")
    return suggestions


def get_latency_suggestions(latency_analysis: dict[str, Any]) -> list[str]:
    """Get suggestions based on latency analysis."""
    suggestions = []
    if latency_analysis.get("overhead_pct", 0) > 50:
        suggestions.append(
            f"Skill adds {latency_analysis['overhead_pct']}% "
            "latency overhead — "
            "optimize prompt or reduce steps"
        )
    slow_count = latency_analysis.get("slow_with_skill", 0)
    if slow_count > 0:
        suggestions.append(
            f"{slow_count} requests exceeded 30s threshold — consider async processing or timeouts"
        )
    return suggestions


def get_reliability_suggestions(reliability: dict[str, Any]) -> list[str]:
    """Get suggestions based on reliability analysis."""
    suggestions = []
    if reliability.get("error_rate", 0) > 0.2:
        suggestions.append(
            f"Error rate is {reliability['error_rate']:.0%} — "
            "implement retry logic or fallback models"
        )
    if reliability.get("retry_stats", {}).get("max_retries", 0) > 2:
        suggestions.append(
            f"Max retries of {reliability['retry_stats']['max_retries']} detected — "
            "consider backoff or circuit breaker"
        )
    errors_by_category = reliability.get("errors_by_category", {})
    if errors_by_category:
        if "timeout" in errors_by_category:
            suggestions.append("Timeout errors detected — increase timeout or optimize prompts")
        if "rate_limit" in errors_by_category:
            suggestions.append("Rate limit errors detected — reduce concurrency or request rate")
    return suggestions


def generate_suggestions(
    metrics: dict[str, Any],
    drift: dict[str, Any] | None,
    verdict: str,
    overall_score: float,
    cost_analysis: dict[str, Any] | None = None,
    latency_analysis: dict[str, Any] | None = None,
    reliability: dict[str, Any] | None = None,
) -> list[str]:
    """Generate improvement suggestions based on metrics and drift analysis."""
    suggestions: list[str] = []

    suggestions.extend(get_metric_suggestions(metrics))

    if drift and drift.get("drift_detected", False):
        suggestions.append(
            f"Address cross-model drift (highest severity: {drift.get('highest_severity', 'none')})"
        )

    suggestions.extend(get_overall_suggestions(overall_score))

    if cost_analysis:
        suggestions.extend(get_cost_suggestions(cost_analysis))

    if latency_analysis:
        suggestions.extend(get_latency_suggestions(latency_analysis))

    if reliability:
        suggestions.extend(get_reliability_suggestions(reliability))

    if not suggestions:
        suggestions.append("Performance is strong across all metrics")

    return suggestions


def create_summary(
    verdict: str, overall_score: float, l1: float, l2: float, l3: float, l4: float
) -> str:
    """Create executive summary based on results."""
    summary_parts = [f"This skill certification resulted in a {verdict} verdict."]

    if overall_score >= 0.8:
        summary_parts.append("The skill performs well across all evaluation dimensions.")
    elif overall_score >= 0.6:
        summary_parts.append("The skill shows promise but needs improvements in certain areas.")
    else:
        summary_parts.append("The skill requires significant improvements before certification.")

    summary_parts.append(f"L1:{l1:.0%}, L2:{l2:.0%}, L3:{l3:.0%}, L4:{l4:.0%}")

    return " ".join(summary_parts)


def build_eval_details(eval_results: list[dict[str, Any]] | None) -> list[EvalDetail]:
    """Build EvalDetail list from raw eval result dicts."""
    if not eval_results:
        return []

    details: list[EvalDetail] = []
    for r in eval_results:
        grade = r.get("grade") or {}
        assertion_results = grade.get("assertion_results") or []

        assertions = [
            ReportAssertionResult(
                type=(a.get("assertion") or {}).get("type", ""),
                expected=(a.get("assertion") or {}).get("value", ""),
                actual=a.get("reason", ""),
                passed=a.get("passed", False),
                weight=float((a.get("assertion") or {}).get("weight", 1)),
            )
            for a in assertion_results
        ]

        details.append(
            EvalDetail(
                eval_id=r.get("eval_id", 0),
                eval_name=r.get("eval_name", ""),
                eval_category=r.get("eval_category", r.get("category", "")),
                model=r.get("model", ""),
                phase=r.get("mode", ""),
                input=r.get("input") or "",
                output=r.get("output") or "",
                passed=r.get("final_passed", False),
                score=r.get("pass_rate", 0.0),
                assertions=assertions,
                execution_time=r.get("execution_time", 0.0),
                tokens_used=r.get("tokens_used", 0),
                cost=r.get("cost", 0.0),
                error=r.get("error"),
                workflow_step=r.get("workflow_step"),
                negative_case=r.get("negative_case", False),
            )
        )
    return details


def _build_l1_detail(metrics: dict[str, Any], breakdown: dict[str, Any]) -> MetricDimension:
    score = num(metrics.get("l1_trigger_accuracy", 0.0))
    trigger_evals = breakdown.get("l1_details", {}).get("total_trigger_evals", 0)
    passed = breakdown.get("l1_details", {}).get("passed_trigger_evals", 0)
    return MetricDimension(
        purpose=(
            "Verifies the model triggers the skill in correct scenarios"
            " and avoids false triggers."
        ),
        method=(
            f"Evaluates {trigger_evals} trigger cases"
            " (positive + negative) using deterministic assertions."
        ),
        result=(
            f"Trigger accuracy: {score:.0%} ({passed}/{trigger_evals} passed)."
            " Threshold: >=90%."
        ),
        analysis=(
            "Low accuracy indicates trigger conditions are ambiguous"
            " or description mismatches model interpretation."
        ),
        improvement=(
            "Add explicit trigger phrases, expand negative cases,"
            " or adjust description wording."
        ),
    )


def _build_l2_detail(metrics: dict[str, Any], breakdown: dict[str, Any]) -> MetricDimension:
    delta = num(metrics.get("l2_with_without_skill_delta", 0.0))
    with_avg = breakdown.get("l2_details", {}).get("with_skill_avg_pass_rate", 0.0)
    without_avg = breakdown.get("l2_details", {}).get("without_skill_avg_pass_rate", 0.0)
    return MetricDimension(
        purpose=(
            "Measures whether the skill demonstrably improves"
            " output quality over the baseline."
        ),
        method="Compares with-skill vs without-skill pass rates on the same eval suite.",
        result=(
            f"Output delta: {delta:.1%}"
            f" (with: {with_avg:.0%}, without: {without_avg:.0%})."
            " Threshold: >=20%."
        ),
        analysis=(
            "Low delta means the skill adds little value."
            " The model may already perform the task well without it."
        ),
        improvement=(
            "Strengthen workflow steps, add domain-specific instructions,"
            " or target harder eval cases."
        ),
    )


def _build_l3_detail(metrics: dict[str, Any], breakdown: dict[str, Any]) -> MetricDimension:
    score = num(metrics.get("l3_step_adherence", 0.0))
    coverage = breakdown.get("l3_details", {}).get("step_coverage_ratio", 0.0)
    return MetricDimension(
        purpose=(
            "Checks if the model follows the skill's"
            " defined workflow steps during execution."
        ),
        method=(
            "Measures step coverage via token-overlap matching"
            " against defined workflow steps."
        ),
        result=(
            f"Step adherence: {score:.0%} (coverage: {coverage:.0%})."
            " Threshold: >=85%."
        ),
        analysis=(
            "Low adherence means steps are skipped"
            " or the workflow is not well-integrated into the prompt."
        ),
        improvement="Simplify workflow steps, add clearer transition cues, or reduce step count.",
    )


def _build_l4_detail(metrics: dict[str, Any], breakdown: dict[str, Any]) -> MetricDimension:
    std = num(breakdown.get("l4_details", {}).get("stdev_deterministic_pass_rate", 0.0))
    return MetricDimension(
        purpose="Measures result consistency across multiple runs of the same evaluation.",
        method="Computes standard deviation of deterministic pass rates across N runs.",
        result=f"Stability std: {std:.3f}. Threshold: <=0.10.",
        analysis=(
            "High variance indicates nondeterministic behavior"
            " or sensitivity to prompt order."
        ),
        improvement=(
            "Increase run count, lock random seeds,"
            " or stabilize model response temperature."
        ),
    )


def _build_l5_detail(metrics: dict[str, Any], breakdown: dict[str, Any]) -> MetricDimension:
    score = num(metrics.get("l5_step_efficiency", 0.0))
    return MetricDimension(
        purpose=(
            "Verifies the skill operates within step, token,"
            " and tool call limits."
        ),
        method=(
            "EnvelopeChecker validates each eval run against"
            " max_steps, max_tokens, and max_tool_calls."
        ),
        result=f"Step efficiency: {score:.0%}.",
        analysis=(
            "Low efficiency means the skill consumes excessive steps"
            " or tokens for its task."
        ),
        improvement=(
            "Optimize workflow to reduce redundant steps,"
            " or increase envelope limits."
        ),
    )


def _build_l6_detail(metrics: dict[str, Any], breakdown: dict[str, Any]) -> MetricDimension:
    score = num(metrics.get("l6_trajectory_quality", 0.0))
    return MetricDimension(
        purpose=(
            "Evaluates multi-turn dialogue coherence"
            " and decision quality (dialogue mode only)."
        ),
        method=(
            "LLM-as-Judge scores turn-level relevance,"
            " tool call accuracy, and goal completion."
        ),
        result=f"Trajectory quality: {score:.0%}.",
        analysis=(
            "Low quality indicates the model loses context"
            " or makes poor intermediate decisions."
        ),
        improvement=(
            "Add intermediate checkpoints, reduce turn count,"
            " or strengthen context preservation."
        ),
    )


def _build_l7_detail(cost_analysis: dict[str, Any] | None) -> MetricDimension:
    if not cost_analysis:
        return MetricDimension(purpose="Cost efficiency not available (no cost data).")
    eff = cost_analysis.get("cost_efficiency", 0.0)
    delta = cost_analysis.get("cost_delta_pct", 0.0)
    return MetricDimension(
        purpose=(
            "Determines whether the quality improvement"
            " justifies the additional cost."
        ),
        method=(
            "Compares per-eval cost for with-skill"
            " vs without-skill runs using pricing table."
        ),
        result=f"Cost efficiency: {eff:.2f}, delta: {delta:.1%}.",
        analysis="High cost delta with low L2 gain means poor return on investment.",
        improvement="Optimize prompt length, reduce tool calls, or switch to a cheaper model.",
    )


def _build_l8_detail(latency_analysis: dict[str, Any] | None) -> MetricDimension:
    if not latency_analysis:
        return MetricDimension(purpose="Latency analysis not available.")
    overhead = latency_analysis.get("overhead_pct", 0.0)
    ws = latency_analysis.get("with_skill", {})
    wos = latency_analysis.get("without_skill", {})
    return MetricDimension(
        purpose="Measures the latency overhead introduced by the skill.",
        method="Compares P50/P95/P99 latency between with-skill and without-skill runs.",
        result=(
            f"Overhead: {overhead:.0f}%"
            f" (P50 with: {ws.get('p50', 0):.2f}s,"
            f" without: {wos.get('p50', 0):.2f}s)."
        ),
        analysis="High overhead may degrade user experience, especially for interactive skills.",
        improvement="Reduce skill complexity, optimize step count, or use faster model inference.",
    )


def build_metrics_section(
    metrics: dict[str, Any], metrics_breakdown: dict[str, Any]
) -> MetricsSection:
    """Build MetricsSection from metrics data with per-metric five-field analysis."""
    l4_details = metrics_breakdown.get("l4_details", {})
    cost_analysis = metrics.get("cost_analysis")
    latency_analysis = metrics.get("latency_analysis")
    l1_score = num(metrics.get("l1_trigger_accuracy", 0.0))
    l2_score = num(metrics.get("l2_with_without_skill_delta", 0.0))
    l3_score = num(metrics.get("l3_step_adherence", 0.0))
    l5_score = num(metrics.get("l5_step_efficiency", 0.0))
    l6_score = num(metrics.get("l6_trajectory_quality", 0.0))

    ws_p50 = latency_analysis.get("with_skill", {}).get("p50", 0.0) if latency_analysis else 0.0
    ws_p95 = latency_analysis.get("with_skill", {}).get("p95", 0.0) if latency_analysis else 0.0
    ws_p99 = latency_analysis.get("with_skill", {}).get("p99", 0.0) if latency_analysis else 0.0

    return MetricsSection(
        l1_trigger_accuracy=l1_score * 100,
        l1_detail=_build_l1_detail(metrics, metrics_breakdown),
        l2_output_delta=l2_score,
        l2_detail=_build_l2_detail(metrics, metrics_breakdown),
        l3_step_adherence=l3_score * 100,
        l3_detail=_build_l3_detail(metrics, metrics_breakdown),
        l4_stability_std=num(l4_details.get("stdev_deterministic_pass_rate", 0.0)),
        l4_detail=_build_l4_detail(metrics, metrics_breakdown),
        l5_step_efficiency=l5_score * 100,
        l5_detail=_build_l5_detail(metrics, metrics_breakdown),
        l6_trajectory_quality=l6_score * 100,
        l6_detail=_build_l6_detail(metrics, metrics_breakdown),
        l7_cost_efficiency=cost_analysis.get("cost_efficiency", 0.0) if cost_analysis else 0.0,
        l7_detail=_build_l7_detail(cost_analysis),
        l8_latency_p50=ws_p50 * 1000,
        l8_latency_p95=ws_p95 * 1000,
        l8_latency_p99=ws_p99 * 1000,
        l8_detail=_build_l8_detail(latency_analysis),
    )


def build_token_section(token_analysis: dict[str, Any] | None) -> TokenAnalysisSection:
    """Build TokenAnalysisSection from token data."""
    if not token_analysis:
        return TokenAnalysisSection()
    return TokenAnalysisSection(
        total_tokens=token_analysis.get("total_tokens", 0),
        total_cost=token_analysis.get("total_cost", 0.0),
        by_phase={k: TokenBreakdown(**v) for k, v in token_analysis.get("by_phase", {}).items()},
        by_model={k: TokenBreakdown(**v) for k, v in token_analysis.get("by_model", {}).items()},
        by_eval=token_analysis.get("by_eval", []),
    )


def build_observability_section(
    observability: dict[str, Any] | None,
) -> ObservabilitySection:
    """Build ObservabilitySection from observability data."""
    if not observability:
        return ObservabilitySection()
    return ObservabilitySection(
        trace_count=observability.get("trace_count", 0),
        total_events=observability.get("total_events", 0),
        total_duration_ms=observability.get("total_duration_ms", 0.0),
        total_tool_calls=observability.get("total_tool_calls", 0),
        trace_export_path=observability.get("trace_export_path", ""),
        trace_format=observability.get("trace_format", "jsonl"),
    )


def convert_suggestions(suggestions: list[str]) -> list[ImprovementSuggestion]:
    """Convert string suggestions to ImprovementSuggestion objects."""
    improvements = []
    for s in suggestions:
        if isinstance(s, ImprovementSuggestion):
            improvements.append(s)
        else:
            improvements.append(
                ImprovementSuggestion(
                    category="general",
                    priority="medium",
                    title=s[:50] if len(s) > 50 else s,
                    description=s,
                )
            )
    return improvements


def build_verdict_reasons(metrics: dict[str, Any], drift: dict[str, Any] | None) -> list[str]:
    """Build verdict reasons from metrics and drift."""
    reasons = []
    l1 = num(metrics.get("l1_trigger_accuracy", 0.0))
    l2 = num(metrics.get("l2_with_without_skill_delta", 0.0))
    l3 = num(metrics.get("l3_step_adherence", 0.0))
    if l1 >= 0.9:
        reasons.append(f"L1 trigger accuracy: {l1:.0%}")
    if l2 >= 0.2:
        reasons.append(f"L2 output delta: {l2:.1f}%")
    if l3 >= 0.85:
        reasons.append(f"L3 step adherence: {l3:.0%}")
    return reasons


def build_blocking_issues(drift: dict[str, Any] | None) -> list[str]:
    """Build blocking issues from drift analysis."""
    issues = []
    if drift and drift.get("highest_severity") == "high":
        issues.append(
            f"High severity drift detected (variance: {drift.get('max_variance', 0):.3f})"
        )
    return issues


def build_caveats(metrics: dict[str, Any], drift: dict[str, Any] | None) -> list[str]:
    """Build caveats from metrics and drift."""
    caveats = []
    if drift and drift.get("drift_detected"):
        caveats.append(f"Drift detected (severity: {drift.get('highest_severity', 'none')})")
    return caveats


def build_stress_section(result: dict[str, Any]) -> str:
    """Build Markdown stress/scalability section."""
    verdict = result.get("verdict", "FAIL")
    score = result.get("scalability_score", 0)
    lines = [
        "## Scalability",
        "",
        f"**Verdict:** {verdict} | **Score:** {score:.1f}/100",
        "",
        f"- **Total evals:** {result.get('total_evals', 0)}",
        f"- **Completed:** {result.get('completed', 0)}",
        f"- **Failed:** {result.get('failed', 0)}",
        f"- **Timed out:** {result.get('timed_out', 0)}",
        f"- **Errored:** {result.get('errored', 0)}",
        f"- **Completion rate:** {result.get('completion_rate', 0):.1%}",
        f"- **Fairness ratio:** {result.get('fairness_ratio', 0):.2f}",
        "",
        "**Latency**",
        "",
    ]
    lat = result.get("latency", {})
    lines.append(f"- **Avg:** {lat.get('avg', 0):.2f}s")
    lines.append(f"- **Min:** {lat.get('min', 0):.2f}s | **Max:** {lat.get('max', 0):.2f}s")
    lines.append(f"- **Median:** {lat.get('median', 0):.2f}s")
    lines.append(f"- **P95:** {lat.get('p95', 0):.2f}s | **P99:** {lat.get('p99', 0):.2f}s")
    lines.append("")
    lines.append(f"**Peak memory:** {result.get('memory_mb_peak', 0):.2f} MB")
    lines.append("")
    model_counts = result.get("model_exec_counts", {})
    if model_counts:
        lines.append("**Model execution counts**")
        lines.append("")
        for model, count in model_counts.items():
            lines.append(f"- {model}: {count}")
        lines.append("")
    return "\n".join(lines)


def build_multi_skill_section(report: dict[str, Any]) -> str:
    """Build Markdown multi-skill analysis section."""
    lines = [
        "## Multi-Skill Analysis",
        "",
        f"**Skills Analysed**: {report.get('skill_count', 0)}",
        f"**Overall Risk**: {report.get('overall_risk', 'none').upper()}",
        "",
        report.get("summary", "No conflicts detected."),
        "",
        "| Category | Count |",
        "|----------|-------|",
        f"| Trigger Overlaps | {report.get('trigger_conflicts', 0)} |",
        f"| Prompt Contamination | {report.get('prompt_contamination_conflicts', 0)} |",
        f"| Token Overflow | {report.get('token_overflow_conflicts', 0)} |",
        "",
    ]

    conflicts = report.get("conflicts", [])
    if conflicts:
        lines.append("### Conflicts")
        lines.append("")
        lines.append("| Severity | Type | Skill A | Skill B | Details |")
        lines.append("|----------|------|---------|---------|---------|")
        for c in conflicts:
            if hasattr(c, "to_dict"):
                cd = c.to_dict()
            else:
                cd = c
            lines.append(
                f"| {cd.get('severity', '')} | {cd.get('conflict_type', '')} | "
                f"{cd.get('skill_a', '')} | {cd.get('skill_b', '')} | "
                f"{cd.get('description', '')} |"
            )
        lines.append("")

    return "\n".join(lines)


def build_metric_analysis(metric_name: str, details: dict[str, Any] | None) -> dict[str, Any]:
    """Build 5-dimension metric analysis for a single metric.

    Returns a dict with keys: purpose, method, result_summary, analysis, suggestions.
    Computed deterministically via if/else branches — no LLM calls.

    Args:
        metric_name: One of "L1".."L8", "drift", "security", "cost", "reliability".
        details: Metric-specific dict with score/rate/count fields.
    """
    from engine.constants import METRIC_METADATA  # noqa: F811

    if details is None:
        details = {}

    meta = METRIC_METADATA.get(metric_name, {})
    purpose = meta.get("purpose", f"Evaluate {metric_name} performance")
    method = meta.get("method", "Standard metric computation")

    result_summary = ""
    analysis = ""
    suggestions: list[str] = []

    # ── L1: Trigger Accuracy ───────────────────────────────────────
    if metric_name == "L1":
        score = details.get("score", 0.0)
        total = details.get("total_trigger_evals", 0)
        passed = details.get("passed_trigger_evals", 0)
        fp = details.get("fp_count", 0)
        fn = details.get("fn_count", 0)
        status = "PASS" if score >= 0.9 else "FAIL"
        result_summary = (
            f"触发准确率: {score:.1%} ({passed}/{total} 通过) — {status} (阈值≥90%)"
        )
        if fp > fn:
            analysis = "误触发偏多（FP > FN），Skill描述可能过于宽泛，导致模型在不相关场景也误触发"
        elif fn > fp:
            analysis = "漏触发偏多（FN > FP），Skill触发条件不够明确，模型未能识别应触发场景"
        else:
            analysis = "触发准确率在各维度均衡，FP与FN分布基本对称"
        if score < 0.7:
            suggestions.append("添加更明确的触发短语，减少触发条件歧义")
        if score < 0.9:
            suggestions.append("扩充反例用例，覆盖更多不应触发场景")

    # ── L2: With/Without Skill Delta ───────────────────────────────
    elif metric_name == "L2":
        score = details.get("score", 0.0)
        improvement = details.get("improvement_percentage", 0.0)
        with_avg = details.get("with_skill_avg_pass_rate", 0.0)
        without_avg = details.get("without_skill_avg_pass_rate", 0.0)
        status = "PASS" if score >= 0.2 else "FAIL"
        result_summary = (
            f"输出增益: {improvement:.1f}% (With: {with_avg:.0%}, Without: {without_avg:.0%})"
            f" — {status} (阈值≥20%)"
        )
        if improvement < 5.0:
            analysis = "增益极低（<5%），Skill未明显提升模型输出质量，模型本身可能已有相关能力"
        elif improvement < 0:
            analysis = "Skill引入负增益，提示词可能干扰了模型的原有判断"
        elif improvement >= 20:
            analysis = "Skill带来显著提升，成功将领域知识注入模型行为"
        else:
            analysis = "Skill有正向增益但未达阈值，建议针对性强化关键步骤"
        if improvement < 20:
            suggestions.append("增强Skill的核心步骤指令，提供更具体的领域知识")
        if improvement < 5:
            suggestions.append("考虑将Skill中的基础知识融入系统提示词，而非单独Skill")

    # ── L3: Step Adherence ─────────────────────────────────────────
    elif metric_name == "L3":
        score = details.get("score", 0.0)
        coverage = details.get("step_coverage_ratio", 0.0)
        status = "PASS" if score >= 0.85 else "FAIL"
        result_summary = (
            f"步骤遵循度: {score:.1%} (覆盖率: {coverage:.0%}) — {status} (阈值≥85%)"
        )
        if score < 0.7:
            analysis = "步骤遵循度严重不足，工作流步骤过于复杂或缺少明确执行指引"
        elif score < 0.85:
            analysis = "部分步骤被跳过，可能是工作流定义不够简洁或模型难以理解中间步骤"
        else:
            analysis = "模型良好遵循工作流步骤，Skill的结构设计合理"
        if score < 0.85:
            suggestions.append("简化工作流步骤，减少步骤数量或合并相关步骤")
            suggestions.append("为每个步骤添加明确的转换提示（如'完成后进入下一步...'）")

    # ── L4: Execution Stability ────────────────────────────────────
    elif metric_name == "L4":
        score = details.get("score")
        std = details.get("stdev_deterministic_pass_rate", 0.0)
        runs = details.get("runs", 1)
        if score is None or runs < 2:
            result_summary = "N/A — 仅单次执行，无法评估稳定性"
            analysis = "单次执行不能反映稳定性，需要≥2次执行才能计算标准差"
        else:
            status = "PASS" if std <= 0.10 else "FAIL"
            result_summary = (
                f"执行稳定性标准差: {std:.3f} — {status} (阈值≤0.10)"
            )
            if std > 0.10:
                analysis = "多次执行结果波动较大，Skill可能存在非确定性行为（如依赖模型随机性）"
            else:
                analysis = "执行结果稳定，Skill在不同轮次间表现一致"
        if runs < 2:
            suggestions.append("增加执行次数（--runs≥2）以评估稳定性")
        if std > 0.10:
            suggestions.append("锁定随机种子或降低模型temperature以增强确定性")

    # ── L5: Step Efficiency ────────────────────────────────────────
    elif metric_name == "L5":
        score = details.get("score", 0.0)
        violations = details.get("violations", 0)
        status = "PASS" if score >= 0.7 else "FAIL"
        result_summary = (
            f"步骤效率: {score:.1%} ({violations} 次违规) — {status}"
        )
        if score == 1.0:
            analysis = "所有执行在操作边界内完成，步骤/Token/工具调用均未超限"
        elif score >= 0.7:
            analysis = "存在少量违规，整体效率可接受"
        else:
            analysis = "多次违规表明Skill消耗过多步骤、Token或工具调用"
        if violations > 0:
            suggestions.append("优化工作流减少冗余步骤或降低Token消耗")
        if violations >= 2:
            suggestions.append("考虑提高操作包络限制或拆分复杂Skill")

    # ── L6: Trajectory Quality ─────────────────────────────────────
    elif metric_name == "L6":
        score = details.get("score", 0.0)
        result_summary = f"轨迹质量: {score:.1%}"
        if score >= 0.8:
            analysis = "多轮对话轨迹连贯，决策路径合理，目标达成度高"
        elif score >= 0.6:
            analysis = "对话轨迹基本合理但存在局部决策问题或上下文丢失"
        else:
            analysis = "对话轨迹质量低，模型可能迷失方向或做出不当中间决策"
        if score < 0.7:
            suggestions.append("添加中间检查点，在关键步骤后确认当前方向")
            suggestions.append("强化上下文保留机制或减少单次对话轮数")

    # ── L7: Cost Efficiency ────────────────────────────────────────
    elif metric_name == "L7":
        delta_pct = details.get("cost_delta_pct", 0.0)
        efficiency = details.get("cost_efficiency", 0.0)
        total_cost = details.get("total_cost", 0.0)
        result_summary = (
            f"成本效率: {efficiency:.4f}, 总成本: ${total_cost:.2f}, 成本增量: {delta_pct:.1%}"
        )
        if delta_pct > 0.5:
            analysis = "Skill显著增加成本（>50%），ROI可能不理想"
        elif delta_pct < 0:
            analysis = "Skill降低了执行成本，极高性价比"
        elif delta_pct < 0.2:
            analysis = "成本增量在可接受范围，Skill带来的增益值得额外成本"
        else:
            analysis = "成本增量较高，需评估增益是否能证明开销合理"
        if delta_pct > 0.5:
            suggestions.append("优化提示词长度，减少冗余内容以降低Token消耗")
        if efficiency < 0.01 and delta_pct > 0:
            suggestions.append("成本效率极低 — 质量增益无法证明成本增加的合理性")

    # ── L8: Latency ────────────────────────────────────────────────
    elif metric_name == "L8":
        overhead = details.get("overhead_pct", 0.0)
        ws = details.get("with_skill", {})
        ws_p50 = ws.get("p50", 0.0) if ws else 0.0
        result_summary = (
            f"延迟开销: {overhead:.0f}% (P50 With: {ws_p50:.2f}s)"
        )
        if overhead > 50:
            analysis = "延迟开销过大（>50%），严重影响交互式使用体验"
        elif overhead > 20:
            analysis = "延迟开销较高，可能影响用户体验但对非交互式场景可接受"
        elif overhead < 0:
            analysis = "Skill反而降低延迟（可能因更精确的指引减少了模型思考时间）"
        else:
            analysis = "延迟开销在正常范围，Skill未显著拖慢执行速度"
        if overhead > 50:
            suggestions.append("大幅优化Skill结构，减少步骤或使用更快的模型")
        if overhead > 20:
            suggestions.append("考虑异步处理或并行执行非依赖步骤")

    # ── Drift ───────────────────────────────────────────────────────
    elif metric_name == "drift":
        models = details.get("models", 1)
        drift_detected = details.get("drift_detected")
        severity = details.get("highest_severity", "none")
        max_var = details.get("max_variance", 0.0)
        avg_var = details.get("average_variance", 0.0)
        if drift_detected is None or models < 2:
            result_summary = "Skipped — 单模型评估，无法检测跨模型漂移"
            analysis = "跨模型漂移检测需要≥2个不同provider的模型"
            suggestions.append("增加至少一个不同provider的模型以启用漂移检测")
        elif drift_detected:
            result_summary = (
                f"检测到跨模型漂移 — 最高严重度: {severity}"
                f" (Max方差: {max_var:.3f}, Avg方差: {avg_var:.3f})"
            )
            if severity == "high":
                analysis = "严重跨模型漂移 — Skill极度依赖特定模型，无法在多模型间稳定工作"
            elif severity == "moderate":
                analysis = "中等跨模型漂移 — 不同模型间存在显著差异，需关注模型适配性"
            else:
                analysis = "轻微跨模型漂移 — 模型间差异在可接受范围内"
            if severity in ("moderate", "high"):
                suggestions.append("Skill中避免依赖特定模型特性，使用通用化描述")
                suggestions.append("针对表现较差的模型调整提示词或增加适配说明")
        else:
            result_summary = "未检测到显著漂移 — 所有模型表现一致"
            analysis = "Skill在不同模型上都表现一致，跨模型稳定性良好"

    # ── Security ────────────────────────────────────────────────────
    elif metric_name == "security":
        probe_count = details.get("probe_count", 0)
        triggered = details.get("triggered", 0)
        bypasses = details.get("bypasses_found", 0)
        if bypasses == 0 and triggered == 0:
            result_summary = f"安全扫描通过 — 0/{probe_count} 探针触发，未发现绕过"
            analysis = "未检测到安全风险，Skill定义不包含危险指令或可注入模式"
        else:
            result_summary = (
                f"安全问题 — {triggered}/{probe_count} 探针触发, {bypasses} 绕过"
            )
            analysis = "检测到潜在安全风险，Skill可能包含危险指令或存在注入点"
        if bypasses > 0:
            suggestions.append("立即移除硬编码凭证或危险命令")
            suggestions.append("使用参数化输入替代直接拼接命令")
        if triggered > 0:
            suggestions.append("审查触发探针的Skill内容，确保指令上下文安全")

    # ── Cost (separate section) ─────────────────────────────────────
    elif metric_name == "cost":
        total_cost = details.get("total_cost", 0.0)
        cost_per_eval = details.get("cost_per_eval", 0.0)
        model = details.get("model", "unknown")
        result_summary = (
            f"总成本: ${total_cost:.2f}, 单次评测: ${cost_per_eval:.4f} (模型: {model})"
        )
        if total_cost > 1.0:
            analysis = "评测成本较高，大量评测用例或高成本模型可能影响批量评测可行性"
        elif total_cost > 0.1:
            analysis = "评测成本适中，适合常规使用"
        else:
            analysis = "评测成本极低，可频繁运行"
        if total_cost > 1.0:
            suggestions.append("考虑降低评测用例数或切换到更经济的模型")
            suggestions.append("缓存常用评测结果以降低重复评测成本")

    # ── Reliability ─────────────────────────────────────────────────
    elif metric_name == "reliability":
        total_evals = details.get("total_evals", 0)
        error_rate = details.get("error_rate", 0.0)
        success_rate = details.get("success_rate", 0.0)
        retry_stats = details.get("retry_stats", {})
        avg_retries = retry_stats.get("avg_retries", 0.0)
        max_retries = retry_stats.get("max_retries", 0)
        result_summary = (
            f"成功率: {success_rate:.1%}, 错误率: {error_rate:.1%}"
            f" ({total_evals} 次执行, 平均重试: {avg_retries:.1f})"
        )
        if error_rate > 0.2:
            analysis = "评测过程中错误率过高（>20%），评测结果可能不够可靠"
        elif error_rate > 0.05:
            analysis = "存在一定错误率，整体评测可靠性尚可"
        else:
            analysis = "评测过程高度可靠，API调用稳定性良好"
        if error_rate > 0.1:
            suggestions.append("实现指数退避重试策略以提升成功率")
        if max_retries > 2:
            suggestions.append(f"检测到高达{max_retries}次的重试 — 考虑熔断器或备用模型")
        errors_by_category = details.get("errors_by_category", {})
        if "timeout" in errors_by_category:
            suggestions.append("超时错误频发 — 增加超时时间或优化提示词复杂度")
        if "rate_limit" in errors_by_category:
            suggestions.append("速率限制错误 — 降低并发数或增加请求间隔")

    # ── Unknown metric ──────────────────────────────────────────────
    else:
        result_summary = f"{metric_name}: data available"
        analysis = f"Metric analysis for '{metric_name}' — no specific rule defined"

    return {
        "purpose": purpose,
        "method": method,
        "result_summary": result_summary,
        "analysis": analysis,
        "suggestions": suggestions,
    }
