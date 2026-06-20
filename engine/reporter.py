"""Reporting module for skill-cert engine — generates Markdown and JSON reports."""

from datetime import datetime, timezone
from typing import Any

from jinja2 import Environment

from engine.report_models import (
    ImprovementSuggestion,
    MetricsSection,
    ObservabilitySection,
    ReportMetadata,
    StructuredReport,
    TokenAnalysisSection,
    TokenBreakdown,
    VerdictSummary,
)


class Reporter:
    """Generates Markdown and JSON reports for skill certification results."""

    @staticmethod
    def _redact_config(config: dict[str, Any]) -> dict[str, Any]:
        """Strip sensitive fields (api_key) from config dict for safe reporting."""
        redacted = dict(config)
        models_raw = redacted.get("models")
        if isinstance(models_raw, list):
            redacted["models"] = [
                {k: v for k, v in m.items() if k != "api_key"}
                for m in models_raw
                if isinstance(m, dict)
            ]
        return redacted

    def __init__(self):
        """Initialize reporter with Jinja2 templates."""
        # Define templates inline for simplicity
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
    def _num(value: Any, default: float = 0.0) -> float:
        if value is None:
            return default
        return float(value)

    def generate_report(
        self,
        metrics: dict[str, Any],
        drift: dict[str, Any],
        config: dict[str, Any],
        maintainability: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """
        Generate Markdown and JSON reports from metrics and drift analysis.

        Args:
            metrics: Metrics calculation results from MetricsCalculator
            drift: Drift analysis results from DriftDetector
            config: Configuration parameters

        Returns:
            Tuple of (markdown_report, json_report)
        """
        overall_score = self._num(metrics.get("overall_score", 0.0))
        l1_score = self._num(metrics.get("l1_trigger_accuracy", 0.0))
        l2_score = self._num(metrics.get("l2_with_without_skill_delta", 0.0))
        l3_score = self._num(metrics.get("l3_step_adherence", 0.0))
        l4_score = self._num(metrics.get("l4_execution_stability", 0.0))

        metrics_breakdown = metrics.get("metrics_breakdown", {})
        l1_details = metrics_breakdown.get("l1_details", {})
        l2_details = metrics_breakdown.get("l2_details", {})
        l3_details = metrics_breakdown.get("l3_details", {})
        l4_details = metrics_breakdown.get("l4_details", {})

        # Determine verdict (degraded mode caps at PASS_WITH_CAVEATS)
        degraded = metrics.get("degraded", False)
        verdict = self._determine_verdict(overall_score, drift, degraded=degraded)

        # Prepare data sections
        drift_data = self._prepare_drift_data(drift)
        coverage_data = self._prepare_coverage_data(metrics, config)
        config_info = self._prepare_config_info(config)
        benchmark_info = self._prepare_benchmark_info(metrics, config)
        summary = self._create_summary(
            verdict, overall_score, l1_score, l2_score, l3_score, l4_score
        )

        # Get analysis data
        cost_analysis = metrics.get("l7_cost_efficiency")
        latency_analysis = metrics.get("l8_latency", {})
        reliability = metrics.get("reliability", {})

        # Generate suggestions
        suggestions = self._generate_suggestions(
            metrics, drift, verdict, overall_score, cost_analysis, latency_analysis, reliability
        )

        # Render markdown
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
        )

        # Create JSON report
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
            "config": self._redact_config(config),
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

        return markdown_report, json_report

    def _determine_verdict(
        self, overall_score: float, drift: dict[str, Any], degraded: bool = False
    ) -> str:
        """Determine verdict based on overall score and drift analysis.

        When ``degraded=True`` (coverage < 90% but above block threshold),
        the verdict is capped at PASS_WITH_CAVEATS — it cannot be PASS.
        """
        drift_verdict = drift.get("overall_verdict", "PASS")
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

    def _prepare_drift_data(self, drift: dict[str, Any]) -> dict[str, Any]:
        """Prepare drift data for template rendering."""
        return {
            "drift_detected": drift.get("drift_detected", False),
            "highest_severity": drift.get("highest_severity", "none"),
            "average_variance": drift.get("average_variance", 0.0),
            "max_variance": drift.get("max_variance", 0.0),
            "drift_results": drift.get("drift_results", []),
        }

    def _prepare_coverage_data(
        self,
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

        # Assertion breakdown from results or config fallback
        if _results:
            assertion_breakdown = self._compute_assertion_breakdown(_results)
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

    def _compute_assertion_breakdown(self, results: list[dict]) -> dict[str, dict[str, int]]:
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

    def _prepare_config_info(self, config: dict[str, Any]) -> dict[str, Any] | None:
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

    def _prepare_benchmark_info(
        self,
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

    def _generate_suggestions(
        self,
        metrics: dict[str, Any],
        drift: dict[str, Any],
        verdict: str,
        overall_score: float,
        cost_analysis: dict[str, Any] | None = None,
        latency_analysis: dict[str, Any] | None = None,
        reliability: dict[str, Any] | None = None,
    ) -> list[str]:
        """Generate improvement suggestions based on metrics and drift analysis."""
        suggestions = []

        # L1-L4 suggestions
        suggestions.extend(self._get_metric_suggestions(metrics))

        # Drift suggestions
        if drift.get("drift_detected", False):
            suggestions.append(
                f"Address cross-model drift "
                f"(highest severity: {drift.get('highest_severity', 'none')})"
            )

        # Overall performance suggestions
        suggestions.extend(self._get_overall_suggestions(overall_score))

        # Cost suggestions
        if cost_analysis:
            suggestions.extend(self._get_cost_suggestions(cost_analysis))

        # Latency suggestions
        if latency_analysis:
            suggestions.extend(self._get_latency_suggestions(latency_analysis))

        # Reliability suggestions
        if reliability:
            suggestions.extend(self._get_reliability_suggestions(reliability))

        if not suggestions:
            suggestions.append("Performance is strong across all metrics")

        return suggestions

    def _get_metric_suggestions(self, metrics: dict[str, Any]) -> list[str]:
        """Get suggestions for L1-L4 metrics."""
        suggestions = []
        l1_score = self._num(metrics.get("l1_trigger_accuracy", 0.0))
        if l1_score < 0.7:
            suggestions.append(
                "Improve trigger accuracy - skill may not be properly detecting trigger conditions"
            )

        l2_score = self._num(metrics.get("l2_with_without_skill_delta", 0.0))
        if l2_score < 0.5:
            suggestions.append(
                "Skill may not be providing sufficient value - "
                "consider enhancing core functionality"
            )

        l3_score = self._num(metrics.get("l3_step_adherence", 0.0))
        if l3_score < 0.7:
            suggestions.append("Improve adherence to expected workflow steps")

        l4_score = self._num(metrics.get("l4_execution_stability", 0.0))
        if l4_score < 0.8:
            suggestions.append(
                "Address execution instability - results vary significantly across runs"
            )
        return suggestions

    def _get_overall_suggestions(self, overall_score: float) -> list[str]:
        """Get suggestions based on overall score."""
        if overall_score >= 0.8:
            return []
        if overall_score >= 0.6:
            return ["Several areas need improvement to reach optimal performance"]
        return ["Major improvements needed across multiple areas"]

    def _get_cost_suggestions(self, cost_analysis: dict[str, Any]) -> list[str]:
        """Get suggestions based on cost analysis."""
        suggestions = []
        if cost_analysis.get("cost_delta_pct", 0) > 0.5:
            suggestions.append(
                f"Skill increases costs by "
                f"{cost_analysis['cost_delta_pct']:.0%} — "
                "consider optimizing prompt or reducing verbosity"
            )
        if (
            cost_analysis.get("cost_efficiency", 0) < 0.1
            and cost_analysis.get("cost_delta_pct", 0) > 0
        ):
            suggestions.append("Low cost efficiency — quality gains don't justify cost increase")
        return suggestions

    def _get_latency_suggestions(self, latency_analysis: dict[str, Any]) -> list[str]:
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
                f"{slow_count} requests exceeded 30s threshold — "
                "consider async processing or timeouts"
            )
        return suggestions

    def _get_reliability_suggestions(self, reliability: dict[str, Any]) -> list[str]:
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
                suggestions.append(
                    "Rate limit errors detected — reduce concurrency or request rate"
                )
        return suggestions

    def _create_summary(
        self, verdict: str, overall_score: float, l1: float, l2: float, l3: float, l4: float
    ) -> str:
        """Create executive summary based on results."""
        summary_parts = [f"This skill certification resulted in a {verdict} verdict."]

        if overall_score >= 0.8:
            summary_parts.append("The skill performs well across all evaluation dimensions.")
        elif overall_score >= 0.6:
            summary_parts.append("The skill shows promise but needs improvements in certain areas.")
        else:
            summary_parts.append(
                "The skill requires significant improvements before certification."
            )

        summary_parts.append(f"L1:{l1:.0%}, L2:{l2:.0%}, L3:{l3:.0%}, L4:{l4:.0%}")

        return " ".join(summary_parts)

    def generate_report_with_multi_skill(
        self,
        metrics: dict[str, Any],
        drift: dict[str, Any],
        config: dict[str, Any],
        multi_skill_report: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
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

        multi_md = self._build_multi_skill_section(multi_skill_report)
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

    # ── Structured Report Methods ─────────────────────────────

    def build_structured_report(
        self,
        metrics: dict[str, Any],
        drift: dict[str, Any],
        config: dict[str, Any],
        maintainability: dict[str, Any] | None = None,
        token_analysis: dict[str, Any] | None = None,
        observability: dict[str, Any] | None = None,
        session_telemetry: list[dict[str, Any]] | None = None,
    ) -> StructuredReport:
        """Build a StructuredReport from metrics and drift analysis.

        This is the canonical structured output for skill-cert evaluation.
        """
        # Build metadata (redact config to prevent credential leaks)
        redacted_config = self._redact_config(config)
        metadata = ReportMetadata(
            skill_name=config.get("skill_name", ""),
            skill_path=config.get("skill_path", ""),
            models=redacted_config.get("models", []),
            timestamp=config.get("timestamp", datetime.now(timezone.utc).isoformat()),
            engine_version=config.get("engine_version", "0.1.0"),
        )

        # Build verdict
        overall_score = self._num(metrics.get("overall_score", 0.0))
        degraded = metrics.get("degraded", False)
        verdict = self._determine_verdict(overall_score, drift, degraded=degraded)
        verdict_summary = VerdictSummary(
            verdict=verdict,  # type: ignore[arg-type]
            confidence=overall_score,
            reasons=self._build_verdict_reasons(metrics, drift),
            blocking_issues=self._build_blocking_issues(drift),
            caveats=self._build_caveats(metrics, drift),
        )

        # Build sections
        metrics_breakdown = metrics.get("metrics_breakdown", {})
        metrics_section = self._build_metrics_section(metrics, metrics_breakdown)
        token_section = self._build_token_section(token_analysis)
        obs_section = self._build_observability_section(observability)

        # Build improvements
        cost_analysis = metrics.get("cost_analysis")
        latency_analysis = metrics.get("latency_analysis")
        suggestions = self._generate_suggestions(
            metrics, drift, verdict, overall_score, cost_analysis, latency_analysis
        )
        improvements = self._convert_suggestions(suggestions)

        extras: dict[str, Any] = {"raw_metrics": metrics}
        if session_telemetry:
            extras["session_telemetry"] = session_telemetry

        return StructuredReport(
            metadata=metadata,
            verdict=verdict_summary,
            metrics=metrics_section,
            token_analysis=token_section,
            observability=obs_section,
            improvements=improvements,
            drift=drift,
            extras=extras,
        )

    def _build_metrics_section(
        self, metrics: dict[str, Any], metrics_breakdown: dict[str, Any]
    ) -> MetricsSection:
        """Build MetricsSection from metrics data."""
        l4_details = metrics_breakdown.get("l4_details", {})
        cost_analysis = metrics.get("cost_analysis")
        latency_analysis = metrics.get("latency_analysis")

        return MetricsSection(
            l1_trigger_accuracy=self._num(metrics.get("l1_trigger_accuracy", 0.0)) * 100,
            l2_output_delta=self._num(metrics.get("l2_with_without_skill_delta", 0.0)),
            l3_step_adherence=self._num(metrics.get("l3_step_adherence", 0.0)) * 100,
            l4_stability_std=self._num(l4_details.get("stdev_deterministic_pass_rate", 0.0)),
            l5_step_efficiency=self._num(metrics.get("l5_step_efficiency", 0.0)) * 100,
            l6_trajectory_quality=self._num(metrics.get("l6_trajectory_quality", 0.0)) * 100,
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

    def _build_token_section(self, token_analysis: dict[str, Any] | None) -> TokenAnalysisSection:
        """Build TokenAnalysisSection from token data."""
        if not token_analysis:
            return TokenAnalysisSection()
        return TokenAnalysisSection(
            total_tokens=token_analysis.get("total_tokens", 0),
            total_cost=token_analysis.get("total_cost", 0.0),
            by_phase={
                k: TokenBreakdown(**v) for k, v in token_analysis.get("by_phase", {}).items()
            },
            by_model={
                k: TokenBreakdown(**v) for k, v in token_analysis.get("by_model", {}).items()
            },
            by_eval=token_analysis.get("by_eval", []),
        )

    def _build_observability_section(
        self,
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

    def _convert_suggestions(self, suggestions: list[str]) -> list[ImprovementSuggestion]:
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

    def _build_verdict_reasons(self, metrics: dict[str, Any], drift: dict[str, Any]) -> list[str]:
        """Build verdict reasons from metrics and drift."""
        reasons = []
        l1 = self._num(metrics.get("l1_trigger_accuracy", 0.0))
        l2 = self._num(metrics.get("l2_with_without_skill_delta", 0.0))
        l3 = self._num(metrics.get("l3_step_adherence", 0.0))
        if l1 >= 0.9:
            reasons.append(f"L1 trigger accuracy: {l1:.0%}")
        if l2 >= 0.2:
            reasons.append(f"L2 output delta: {l2:.1f}%")
        if l3 >= 0.85:
            reasons.append(f"L3 step adherence: {l3:.0%}")
        return reasons

    def _build_blocking_issues(self, drift: dict[str, Any]) -> list[str]:
        """Build blocking issues from drift analysis."""
        issues = []
        if drift.get("highest_severity") == "high":
            issues.append(
                f"High severity drift detected (variance: {drift.get('max_variance', 0):.3f})"
            )
        return issues

    def _build_caveats(self, metrics: dict[str, Any], drift: dict[str, Any]) -> list[str]:
        """Build caveats from metrics and drift."""
        caveats = []
        if drift.get("drift_detected"):
            caveats.append(f"Drift detected (severity: {drift.get('highest_severity', 'none')})")
        return caveats

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
        md_report, json_report = self.generate_report(metrics, drift, config)

        stress_section = self._build_stress_section(stress_result)
        md_report = md_report.replace("\n## Raw Results", f"\n{stress_section}\n## Raw Results")

        json_report["scalability"] = stress_result
        return md_report, json_report

    def _build_stress_section(self, result: dict[str, Any]) -> str:
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
