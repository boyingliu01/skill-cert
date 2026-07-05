"""Report generation module — Reporter class for Markdown and JSON reports.

Contains the Reporter class which orchestrates report generation by delegating
to helper functions in formatters.py and builders.py.
"""

from datetime import datetime, timezone
from typing import Any

from jinja2 import Environment

from engine.report_models import (
    EvalDetail,
    ImprovementSuggestion,
    MetricsSection,
    ObservabilitySection,
    ReportMetadata,
    StructuredReport,
    TokenAnalysisSection,
    VerdictSummary,
)
from engine.reporters.builders import (
    build_blocking_issues,
    build_caveats,
    build_eval_details,
    build_metrics_section,
    build_multi_skill_section,
    build_observability_section,
    build_stress_section,
    build_token_section,
    build_verdict_reasons,
    convert_suggestions,
    create_summary,
    determine_verdict,
    generate_suggestions,
    prepare_benchmark_info,
    prepare_config_info,
    prepare_coverage_data,
    prepare_drift_data,
)
from engine.reporters.formatters import num, redact_config


class Reporter:
    """Generates Markdown and JSON reports for skill certification results."""

    def __init__(self):
        """Initialize reporter with Jinja2 templates."""
        self.markdown_template_str = """# Skill Certification Report

## Executive Summary

**Verdict**: {{ verdict }}
**Overall Score**: {{ "%.2f"|format(overall_score * 100) }}%

{{ summary }}

## L1-L4 Metrics

### L1: Trigger Accuracy
- **Score**: {{ "%.2f"|format(l1_score * 100) }}%
- **Details**:
  {{ l1_details.total_trigger_evals }} trigger evaluations,
  {{ l1_details.passed_trigger_evals }} passed
- **Accuracy**: {{ "%.2f"|format(l1_details.trigger_accuracy * 100) }}%

### L2: With/Without Skill Delta
- **Score**: {{ "%.2f"|format(l2_score * 100) }}%
- **With Skill Avg**: {{ "%.2f"|format(l2_details.with_skill_avg_pass_rate * 100) }}%
- **Without Skill Avg**: {{ "%.2f"|format(l2_details.without_skill_avg_pass_rate * 100) }}%
- **Improvement**: {{ "%.2f"|format(l2_details.improvement_percentage) }}%
{% if l2_details.denominator_warning %}
⚠️ **Warning**: Without-skill baseline is near zero — L2 gain may be unreliable.
{% endif %}

### L3: Step Adherence
- **Score**: {{ "%.2f"|format(l3_score * 100) }}%
- **Coverage**: {{ "%.2f"|format(l3_details.step_coverage_ratio * 100) }}%
  of evaluations covered expected steps

### L4: Execution Stability
- **Score**: {{ "%.2f"|format(l4_score * 100) }}%
- **Stability**: {{ "%.2f"|format(l4_details.execution_stability * 100) }}%
- **Std Dev**: {{ "%.3f"|format(l4_details.stdev_deterministic_pass_rate) }}

## Drift Analysis

{% if drift_detected %}
### Cross-Model Drift Detected
- **Highest Severity**: {{ highest_severity }}
- **Average Variance**: {{ "%.3f"|format(average_variance) }}
- **Max Variance**: {{ "%.3f"|format(max_variance) }}

#### Model Comparisons
{% for result in drift_results %}
- {{ result.model_a }} vs {{ result.model_b }}:
  {{ result.severity }} severity
  (variance: {{ "%.3f"|format(result.variance) }})
{% endfor %}
{% else %}
### No Significant Drift Detected
- All model comparisons show consistent performance
{% endif %}

## Evaluation Coverage

- **Total Evaluations**: {{ total_evaluations }}
- **Pass Rate**: {{ "%.2f"|format(avg_pass_rate * 100) }}%
- **Critical Assertions**: {{ critical_passed }}/{{ critical_total }} passed
- **Important Assertions**: {{ important_passed }}/{{ important_total }} passed
- **Normal Assertions**: {{ normal_passed }}/{{ normal_total }} passed
{% if cost_analysis %}

## Cost Analysis

### L7: Cost Efficiency
- **Cost per Eval**: ${{ "%.4f"|format(cost_analysis.cost_per_eval) }}
- **Total Cost**: ${{ "%.2f"|format(cost_analysis.total_cost) }}
- **With Skill (avg)**: ${{ "%.4f"|format(cost_analysis.cost_with_skill) }}
- **Without Skill (avg)**: ${{ "%.4f"|format(cost_analysis.cost_without_skill) }}
- **Cost Delta**: {{ "%.1f"|format(cost_analysis.cost_delta_pct * 100) }}%
- **Cost Efficiency **(L2/Cost){{ "%.2f"|format(cost_analysis.cost_efficiency) }}
{% if cost_analysis.cost_delta_pct > 0.5 %}
⚠️ Skill increases costs by more than 50%. Consider optimizing.
{% endif %}
{% endif %}
{% if latency_analysis %}

## Latency Analysis

### L8: Execution Latency
{% if latency_analysis.with_skill %}
| Metric | With Skill | Without Skill | Overhead |
|--------|-----------|---------------|----------|
| P50 |
  {{ "%.2f"|format(latency_analysis.with_skill.p50) }}s |
  {{ "%.2f"|format(latency_analysis.without_skill.p50) }}s |
  {% if latency_analysis.with_skill.p50 > latency_analysis.without_skill.p50 %}
    +{{ "%.1f"|format(
        ((latency_analysis.with_skill.p50 - latency_analysis.without_skill.p50)
         / latency_analysis.without_skill.p50 * 100)
        if latency_analysis.without_skill.p50 > 0 else 0
    ) }}%
  {% else %}—{% endif %} |
| P95 |
  {{ "%.2f"|format(latency_analysis.with_skill.p95) }}s |
  {{ "%.2f"|format(latency_analysis.without_skill.p95) }}s |
  {% if latency_analysis.with_skill.p95 > latency_analysis.without_skill.p95 %}
    +{{ "%.1f"|format(
        ((latency_analysis.with_skill.p95 - latency_analysis.without_skill.p95)
         / latency_analysis.without_skill.p95 * 100)
        if latency_analysis.without_skill.p95 > 0 else 0
    ) }}%
  {% else %}—{% endif %} |
| Mean |
  {{ "%.2f"|format(latency_analysis.with_skill.mean) }}s |
  {{ "%.2f"|format(latency_analysis.without_skill.mean) }}s |
  — |
| Slow (>30s) |
  {{ latency_analysis.slow_with_skill }} |
  {{ latency_analysis.slow_without_skill }} |
  +{{ latency_analysis.slow_with_skill - latency_analysis.slow_without_skill }} |
{% endif %}
{% if latency_analysis.overhead_pct and latency_analysis.overhead_pct > 20 %}
⚠️ Skill adds {{ latency_analysis.overhead_pct }}% latency overhead.
{% endif %}
{% endif %}
{% if reliability and reliability.total_evals > 0 %}

## Reliability Analysis

| Metric | Value |
|--------|-------|
| Total Eval Runs | {{ reliability.total_evals }} |
| Success Rate | {{ "%.1f"|format(reliability.success_rate * 100) }}% |
| Error Rate | {{ "%.1f"|format(reliability.error_rate * 100) }}% |
| Retries (avg) | {{ "%.2f"|format(reliability.retry_stats.avg_retries) }} |
| Retries (max) | {{ reliability.retry_stats.max_retries }} |

{% if reliability.errors_by_category %}
### Errors by Category
{% for category, count in reliability.errors_by_category.items() %}
- **{{ category }}**: {{ count }}
{% endfor %}
{% endif %}
{% endif %}

## Improvement Suggestions

{% for suggestion in suggestions %}
- {{ suggestion }}
{% endfor %}

## Configuration

{% if config_info %}
- **Models**: {{ config_info.models }}
- **Max Concurrency**: {{ config_info.max_concurrency }}
- **Rate Limit**: {{ config_info.rate_limit_rpm }} RPM
- **Request Timeout**: {{ config_info.request_timeout }}s
- **Judge Temperature**: {{ config_info.judge_temperature }}
- **Max Testgen Rounds**:
  {{ config_info.max_testgen_rounds }}
{% else %}
- Configuration details not available
{% endif %}

{% if maintainability %}
## Maintainability

**Score**: {{ maintainability.total_score }}/100 (Grade: {{ maintainability.grade }})

| Dimension | Score |
|-----------|-------|
| Readability | {{ maintainability.readability_score }} |
| Completeness | {{ maintainability.completeness_score }} |
| Freshness | {{ maintainability.freshness_score }} |

{% if maintainability.readability_details.avg_line_length > 100 %}
  ⚠️ Average line length exceeds 100 characters:
    {{ maintainability.readability_details.avg_line_length }}
{% endif %}
{% if maintainability.readability_details.max_depth > 3 %}
⚠️ Section nesting exceeds 3 levels: depth {{ maintainability.readability_details.max_depth }}
{% endif %}
{% if maintainability.readability_details.todo_count > 0 %}
⚠️ Contains {{ maintainability.readability_details.todo_count }} TODO/FIXME marker(s)
{% endif %}
{% if maintainability.completeness_details.has_workflow == false %}
⚠️ Missing Workflow section
{% endif %}
{% if maintainability.completeness_details.has_anti_patterns == false %}
⚠️ Missing Anti-Patterns section
{% endif %}
{% if maintainability.completeness_details.has_triggers == false %}
⚠️ Missing Triggers section
{% endif %}
{% if maintainability.freshness_details.outdated_refs > 0 %}
⚠️ {{ maintainability.freshness_details.outdated_refs }} outdated reference(s) detected
{% endif %}
{% endif %}
	{% if calibration %}

	## Calibration Analysis

	| Metric | Value |
	|--------|-------|
	| Agreement Rate | {{ "%.1f"|format(calibration.agreement_rate * 100) }}% |
	| Cohen's Kappa | {{ "%.3f"|format(calibration.cohens_kappa) }} |
	| False Positive Rate | {{ "%.1f"|format(calibration.false_positive_rate * 100) }}% |
	| False Negative Rate | {{ "%.1f"|format(calibration.false_negative_rate * 100) }}% |
	| Total Cases | {{ calibration.total_cases }} |

	Interpretation: Kappa > 0.8 = strong agreement, 0.6-0.8 = moderate, < 0.6 = weak calibration.
	{% endif %}

	## Benchmark Information

- **Generated**: {{ benchmark_info.timestamp }}
- **Tool Version**: skill-cert v2.0
- **Spec Version**: {{ benchmark_info.spec_version }}
- **Total Requirements**: {{ benchmark_info.total_requirements }}
- **Total Acceptance Criteria**: {{ benchmark_info.total_acceptance_criteria }}
- **Test Coverage**: {{ benchmark_info.test_coverage }}
- **Total Token Usage**: {{ benchmark_info.total_tokens }} tokens

## Raw Results

For detailed results, see the JSON output.
"""

        self.env = Environment()
        self.markdown_template = self.env.from_string(self.markdown_template_str)

    @staticmethod
    def _redact_config(config: dict[str, Any]) -> dict[str, Any]:
        """Strip sensitive fields (api_key) from config dict for safe reporting."""
        return redact_config(config)

    @staticmethod
    def _num(value: Any, default: float = 0.0) -> float:
        """Convert value to float, returning default if None."""
        return num(value, default)

    def generate_report(
        self,
        metrics: dict[str, Any],
        drift: dict[str, Any] | None,
        config: dict[str, Any],
        maintainability: dict[str, Any] | None = None,
        calibration_data: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Generate Markdown and JSON reports from metrics and drift analysis.

        Args:
            metrics: Metrics calculation results from MetricsCalculator
            drift: Drift analysis results from DriftDetector
            config: Configuration parameters
            maintainability: Optional maintainability scoring data

        Returns:
            Tuple of (markdown_report, json_report)
        """
        overall_score = num(metrics.get("overall_score", 0.0))
        l1_score = num(metrics.get("l1_trigger_accuracy", 0.0))
        l2_score = num(metrics.get("l2_with_without_skill_delta", 0.0))
        l3_score = num(metrics.get("l3_step_adherence", 0.0))
        l4_score = num(metrics.get("l4_execution_stability", 0.0))

        metrics_breakdown = metrics.get("metrics_breakdown", {})
        l1_details = metrics_breakdown.get("l1_details", {})
        l2_details = metrics_breakdown.get("l2_details", {})
        l3_details = metrics_breakdown.get("l3_details", {})
        l4_details = metrics_breakdown.get("l4_details", {})

        degraded = metrics.get("degraded", False)
        verdict = determine_verdict(overall_score, drift, degraded=degraded)

        drift_data = prepare_drift_data(drift)
        coverage_data = prepare_coverage_data(metrics, config)
        config_info = prepare_config_info(config)
        benchmark_info = prepare_benchmark_info(metrics, config)
        summary = create_summary(verdict, overall_score, l1_score, l2_score, l3_score, l4_score)

        cost_analysis = metrics.get("l7_cost_efficiency")
        latency_analysis = metrics.get("l8_latency", {})
        reliability = metrics.get("reliability", {})

        suggestions = generate_suggestions(
            metrics, drift, verdict, overall_score, cost_analysis, latency_analysis, reliability
        )

        markdown_report = self.markdown_template.render(
            verdict=verdict,
            overall_score=overall_score,
            summary=summary,
            l1_score=l1_score,
            l2_score=l2_score,
            l3_score=l3_score,
            l4_score=l4_score,
            l1_details=l1_details,
            l2_details=l2_details,
            l3_details=l3_details,
            l4_details=l4_details,
            **drift_data,
            **coverage_data,
            suggestions=suggestions,
            config_info=config_info,
            benchmark_info=benchmark_info,
            cost_analysis=cost_analysis,
            latency_analysis=latency_analysis,
            reliability=reliability,
            maintainability=maintainability,
            calibration=calibration_data,
        )

        # Progressive disclosure data (from spec, passed via metrics or config)
        progressive_disclosure = metrics.get("progressive_disclosure") or config.get(
            "progressive_disclosure"
        )

        json_report = {
            "verdict": verdict,
            "overall_score": overall_score,
            "metrics": {
                "l1_trigger_accuracy": l1_score,
                "l2_with_without_skill_delta": l2_score,
                "l3_step_adherence": l3_score,
                "l4_execution_stability": l4_score,
            },
            "drift_analysis": drift,
            "evaluation_coverage": coverage_data,
            "improvement_suggestions": suggestions,
            "timestamp": config.get("timestamp", ""),
            "config": redact_config(config),
            "config_summary": config_info,
            "benchmark": benchmark_info,
        }

        if cost_analysis:
            json_report["cost_analysis"] = cost_analysis
        if latency_analysis:
            json_report["latency_analysis"] = latency_analysis
        if reliability:
            json_report["reliability"] = reliability
        if maintainability:
            json_report["maintainability"] = maintainability
        if progressive_disclosure:
            json_report["progressive_disclosure"] = progressive_disclosure

        return markdown_report, json_report

    def _determine_verdict(
        self, overall_score: float, drift: dict[str, Any] | None, degraded: bool = False
    ) -> str:
        """Determine verdict based on overall score and drift analysis."""
        return determine_verdict(overall_score, drift, degraded=degraded)

    def _prepare_drift_data(self, drift: dict[str, Any] | None) -> dict[str, Any]:
        """Prepare drift data for template rendering."""
        return prepare_drift_data(drift)

    def _prepare_coverage_data(
        self, metrics: dict[str, Any], config: dict[str, Any]
    ) -> dict[str, Any]:
        """Prepare evaluation coverage data from results or config fallback."""
        return prepare_coverage_data(metrics, config)

    def _compute_assertion_breakdown(self, results: list[dict]) -> dict[str, dict[str, int]]:
        """Compute assertion breakdown by weight category from results."""
        from engine.reporters.builders import compute_assertion_breakdown

        return compute_assertion_breakdown(results)

    def _prepare_config_info(self, config: dict[str, Any]) -> dict[str, Any] | None:
        """Prepare configuration info for report."""
        return prepare_config_info(config)

    def _prepare_benchmark_info(
        self, metrics: dict[str, Any], config: dict[str, Any]
    ) -> dict[str, Any]:
        """Prepare benchmark info for report."""
        return prepare_benchmark_info(metrics, config)

    def _generate_suggestions(
        self,
        metrics: dict[str, Any],
        drift: dict[str, Any] | None,
        verdict: str,
        overall_score: float,
        cost_analysis: dict[str, Any] | None = None,
        latency_analysis: dict[str, Any] | None = None,
        reliability: dict[str, Any] | None = None,
    ) -> list[str]:
        """Generate improvement suggestions based on metrics and drift analysis."""
        return generate_suggestions(
            metrics, drift, verdict, overall_score, cost_analysis, latency_analysis, reliability
        )

    def _get_metric_suggestions(self, metrics: dict[str, Any]) -> list[str]:
        """Get suggestions for L1-L4 metrics."""
        from engine.reporters.builders import get_metric_suggestions

        return get_metric_suggestions(metrics)

    def _get_overall_suggestions(self, overall_score: float) -> list[str]:
        """Get suggestions based on overall score."""
        from engine.reporters.builders import get_overall_suggestions

        return get_overall_suggestions(overall_score)

    def _get_cost_suggestions(self, cost_analysis: dict[str, Any]) -> list[str]:
        """Get suggestions based on cost analysis."""
        from engine.reporters.builders import get_cost_suggestions

        return get_cost_suggestions(cost_analysis)

    def _get_latency_suggestions(self, latency_analysis: dict[str, Any]) -> list[str]:
        """Get suggestions based on latency analysis."""
        from engine.reporters.builders import get_latency_suggestions

        return get_latency_suggestions(latency_analysis)

    def _get_reliability_suggestions(self, reliability: dict[str, Any]) -> list[str]:
        """Get suggestions based on reliability analysis."""
        from engine.reporters.builders import get_reliability_suggestions

        return get_reliability_suggestions(reliability)

    def _create_summary(
        self, verdict: str, overall_score: float, l1: float, l2: float, l3: float, l4: float
    ) -> str:
        """Create executive summary based on results."""
        return create_summary(verdict, overall_score, l1, l2, l3, l4)

    def generate_report_with_multi_skill(
        self,
        metrics: dict[str, Any],
        drift: dict[str, Any],
        config: dict[str, Any],
        multi_skill_report: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        """Generate report with multi-skill analysis section."""
        safe_metrics = {
            "overall_score": metrics.get("overall_score", 0.5),
            "l1_trigger_accuracy": metrics.get("l1_trigger_accuracy", 0.0),
            "l2_with_without_skill_delta": metrics.get("l2_with_without_skill_delta", 0.0),
            "l3_step_adherence": metrics.get("l3_step_adherence", 0.0),
            "l4_execution_stability": metrics.get("l4_execution_stability", 0.0),
            "metrics_breakdown": metrics.get(
                "metrics_breakdown",
                {
                    "l1_details": {
                        "total_trigger_evals": 0,
                        "passed_trigger_evals": 0,
                        "trigger_accuracy": 0.0,
                    },
                    "l2_details": {
                        "with_skill_avg_pass_rate": 0.0,
                        "without_skill_avg_pass_rate": 0.0,
                        "improvement_percentage": 0.0,
                        "denominator_warning": False,
                    },
                    "l3_details": {"step_coverage_ratio": 0.0},
                    "l4_details": {
                        "execution_stability": 0.0,
                        "stdev_deterministic_pass_rate": 0.0,
                    },
                },
            ),
        }
        md_report, json_report = self.generate_report(safe_metrics, drift, config)

        multi_md = build_multi_skill_section(multi_skill_report)
        md_report = md_report.replace("\n## Raw Results", f"\n{multi_md}\n## Raw Results")

        json_report["multi_skill_analysis"] = {
            "skill_count": multi_skill_report.get("skill_count", 0),
            "overall_risk": multi_skill_report.get("overall_risk", "none"),
            "summary": multi_skill_report.get("summary", ""),
            "conflicts": [
                c.to_dict() if hasattr(c, "to_dict") else c
                for c in multi_skill_report.get("conflicts", [])
            ],
            "trigger_conflicts": multi_skill_report.get("trigger_conflicts", 0),
            "prompt_contamination_conflicts": multi_skill_report.get(
                "prompt_contamination_conflicts", 0
            ),
            "token_overflow_conflicts": multi_skill_report.get("token_overflow_conflicts", 0),
        }

        return md_report, json_report

    def _build_multi_skill_section(self, report: dict[str, Any]) -> str:
        """Build Markdown multi-skill analysis section."""
        return build_multi_skill_section(report)

    def build_structured_report(
        self,
        metrics: dict[str, Any],
        drift: dict[str, Any] | None,
        config: dict[str, Any],
        maintainability: dict[str, Any] | None = None,
        token_analysis: dict[str, Any] | None = None,
        observability: dict[str, Any] | None = None,
        session_telemetry: list[dict[str, Any]] | None = None,
        eval_results: list[dict[str, Any]] | None = None,
        calibration_data: dict[str, Any] | None = None,
    ) -> StructuredReport:
        """Build a StructuredReport from metrics and drift analysis.

        This is the canonical structured output for skill-cert evaluation.
        """
        redacted_config = redact_config(config)
        metadata = ReportMetadata(
            skill_name=config.get("skill_name", ""),
            skill_path=config.get("skill_path", ""),
            models=redacted_config.get("models", []),
            timestamp=config.get("timestamp", datetime.now(timezone.utc).isoformat()),
            engine_version=config.get("engine_version", "0.1.0"),
        )

        overall_score = num(metrics.get("overall_score", 0.0))
        degraded = metrics.get("degraded", False)
        verdict = determine_verdict(overall_score, drift, degraded=degraded)
        verdict_summary = VerdictSummary(
            verdict=verdict,  # type: ignore[arg-type]
            confidence=overall_score,
            reasons=build_verdict_reasons(metrics, drift),
            blocking_issues=build_blocking_issues(drift),
            caveats=build_caveats(metrics, drift),
        )

        metrics_breakdown = metrics.get("metrics_breakdown", {})
        metrics_section = build_metrics_section(metrics, metrics_breakdown)
        token_section = build_token_section(token_analysis)
        obs_section = build_observability_section(observability)

        cost_analysis = metrics.get("cost_analysis")
        latency_analysis = metrics.get("latency_analysis")
        suggestions = generate_suggestions(
            metrics, drift, verdict, overall_score, cost_analysis, latency_analysis
        )
        improvements = convert_suggestions(suggestions)

        extras: dict[str, Any] = {"raw_metrics": metrics}
        if session_telemetry:
            extras["session_telemetry"] = session_telemetry
        if calibration_data:
            extras["calibration"] = calibration_data

        eval_details = build_eval_details(eval_results)

        return StructuredReport(
            metadata=metadata,
            verdict=verdict_summary,
            metrics=metrics_section,
            eval_details=eval_details,
            token_analysis=token_section,
            observability=obs_section,
            improvements=improvements,
            drift=drift if drift is not None else {},
            calibration=calibration_data if calibration_data else None,
            extras=extras,
        )

    def _build_eval_details(self, eval_results: list[dict[str, Any]] | None) -> list[EvalDetail]:
        """Build EvalDetail list from raw eval result dicts."""
        return build_eval_details(eval_results)

    def _build_metrics_section(
        self, metrics: dict[str, Any], metrics_breakdown: dict[str, Any]
    ) -> MetricsSection:
        """Build MetricsSection from metrics data."""
        return build_metrics_section(metrics, metrics_breakdown)

    def _build_token_section(self, token_analysis: dict[str, Any] | None) -> TokenAnalysisSection:
        """Build TokenAnalysisSection from token data."""
        return build_token_section(token_analysis)

    def _build_observability_section(
        self, observability: dict[str, Any] | None
    ) -> ObservabilitySection:
        """Build ObservabilitySection from observability data."""
        return build_observability_section(observability)

    def _convert_suggestions(self, suggestions: list[str]) -> list[ImprovementSuggestion]:
        """Convert string suggestions to ImprovementSuggestion objects."""
        return convert_suggestions(suggestions)

    def _build_verdict_reasons(
        self, metrics: dict[str, Any], drift: dict[str, Any] | None
    ) -> list[str]:
        """Build verdict reasons from metrics and drift."""
        return build_verdict_reasons(metrics, drift)

    def _build_blocking_issues(self, drift: dict[str, Any] | None) -> list[str]:
        """Build blocking issues from drift analysis."""
        return build_blocking_issues(drift)

    def _build_caveats(self, metrics: dict[str, Any], drift: dict[str, Any] | None) -> list[str]:
        """Build caveats from metrics and drift."""
        return build_caveats(metrics, drift)

    def generate_json_report(self, report: StructuredReport) -> str:
        """Generate JSON string from StructuredReport."""
        return report.model_dump_json(indent=2)

    def validate_json_report(self, json_data: dict[str, Any]) -> list[str]:
        """Validate JSON report against schema.

        Returns list of validation errors (empty if valid).
        """
        errors = []
        try:
            StructuredReport.model_validate(json_data)
        except Exception as e:
            errors.append(str(e))
        return errors

    def generate_report_with_stress(
        self,
        metrics: dict[str, Any],
        drift: dict[str, Any],
        config: dict[str, Any],
        stress_result: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        """Generate report with stress/scalability section."""
        md_report, json_report = self.generate_report(metrics, drift, config)

        stress_section = build_stress_section(stress_result)
        md_report = md_report.replace("\n## Raw Results", f"\n{stress_section}\n## Raw Results")

        json_report["scalability"] = stress_result
        return md_report, json_report

    def _build_stress_section(self, result: dict[str, Any]) -> str:
        """Build Markdown stress/scalability section."""
        return build_stress_section(result)
