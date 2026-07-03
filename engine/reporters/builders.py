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
            "drift_detected": False,
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


def build_metrics_section(
    metrics: dict[str, Any], metrics_breakdown: dict[str, Any]
) -> MetricsSection:
    """Build MetricsSection from metrics data."""
    l4_details = metrics_breakdown.get("l4_details", {})
    cost_analysis = metrics.get("cost_analysis")
    latency_analysis = metrics.get("latency_analysis")

    return MetricsSection(
        l1_trigger_accuracy=num(metrics.get("l1_trigger_accuracy", 0.0)) * 100,
        l2_output_delta=num(metrics.get("l2_with_without_skill_delta", 0.0)),
        l3_step_adherence=num(metrics.get("l3_step_adherence", 0.0)) * 100,
        l4_stability_std=num(l4_details.get("stdev_deterministic_pass_rate", 0.0)),
        l5_step_efficiency=num(metrics.get("l5_step_efficiency", 0.0)) * 100,
        l6_trajectory_quality=num(metrics.get("l6_trajectory_quality", 0.0)) * 100,
        l7_cost_efficiency=cost_analysis.get("cost_efficiency", 0.0) if cost_analysis else 0.0,
        l8_latency_p50=latency_analysis.get("with_skill", {}).get("p50", 0.0) * 1000
        if latency_analysis and latency_analysis.get("with_skill")
        else 0.0,
        l8_latency_p95=latency_analysis.get("with_skill", {}).get("p95", 0.0) * 1000
        if latency_analysis and latency_analysis.get("with_skill")
        else 0.0,
        l8_latency_p99=latency_analysis.get("with_skill", {}).get("p99", 0.0) * 1000
        if latency_analysis and latency_analysis.get("with_skill")
        else 0.0,
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
