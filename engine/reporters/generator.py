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
    build_metric_analysis,
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

### L1: Trigger Accuracy — {{ "%.0f"|format(l1_score * 100) }}% {{ "PASS" if l1_score >= 0.9 else "FAIL" }}
**评测目的**: {{ l1_analysis.purpose }}
**评测方法**: {{ l1_analysis.method }}
**评测结果**: {{ l1_analysis.result_summary }}
**分析**: {{ l1_analysis.analysis }}
**改进建议**:
{% for s in l1_analysis.suggestions %}- {{ s }}
{% endfor %}

### L2: With/Without Skill Delta — {{ "%.0f"|format(l2_score * 100) }}% {{ "PASS" if l2_score >= 0.2 else "FAIL" }}
**评测目的**: {{ l2_analysis.purpose }}
**评测方法**: {{ l2_analysis.method }}
**评测结果**: {{ l2_analysis.result_summary }}
**分析**: {{ l2_analysis.analysis }}
**改进建议**:
{% for s in l2_analysis.suggestions %}- {{ s }}
{% endfor %}

### L3: Step Adherence — {{ "%.0f"|format(l3_score * 100) }}% {{ "PASS" if l3_score >= 0.85 else "FAIL" }}
**评测目的**: {{ l3_analysis.purpose }}
**评测方法**: {{ l3_analysis.method }}
**评测结果**: {{ l3_analysis.result_summary }}
**分析**: {{ l3_analysis.analysis }}
**改进建议**:
{% for s in l3_analysis.suggestions %}- {{ s }}
{% endfor %}

### L4: Execution Stability
{% if l4_score is not none %}{{ "%.0f"|format(l4_score * 100) }}%{% else %}N/A{% endif %}
**评测目的**: {{ l4_analysis.purpose }}
**评测方法**: {{ l4_analysis.method }}
**评测结果**: {{ l4_analysis.result_summary }}
**分析**: {{ l4_analysis.analysis }}
**改进建议**:
{% for s in l4_analysis.suggestions %}- {{ s }}
{% endfor %}

{% if l5_analysis %}
### L5: Step Efficiency — {{ "%.0f"|format(l5_score * 100) }}%
**评测目的**: {{ l5_analysis.purpose }}
**评测方法**: {{ l5_analysis.method }}
**评测结果**: {{ l5_analysis.result_summary }}
**分析**: {{ l5_analysis.analysis }}
**改进建议**:
{% for s in l5_analysis.suggestions %}- {{ s }}
{% endfor %}
{% endif %}
{% if l6_analysis %}
### L6: Trajectory Quality — {{ "%.0f"|format(l6_score * 100) }}%
**评测目的**: {{ l6_analysis.purpose }}
**评测方法**: {{ l6_analysis.method }}
**评测结果**: {{ l6_analysis.result_summary }}
**分析**: {{ l6_analysis.analysis }}
**改进建议**:
{% for s in l6_analysis.suggestions %}- {{ s }}
{% endfor %}
{% endif %}

## Drift Analysis

{% if drift_analysis.skipped %}
**Skipped**: {{ drift_analysis.result_summary }}
{% else %}
### Drift
**评测目的**: {{ drift_analysis.purpose }}
**评测方法**: {{ drift_analysis.method }}
**评测结果**: {{ drift_analysis.result_summary }}
**分析**: {{ drift_analysis.analysis }}
**改进建议**:
{% for s in drift_analysis.suggestions %}- {{ s }}
{% endfor %}

{% if drift_detected and drift_results %}
#### Model Comparisons
{% for result in drift_results %}
- {{ result.model_a }} vs {{ result.model_b }}: {{ result.severity }} severity (variance: {{ "%.3f"|format(result.variance) }})
{% endfor %}
{% endif %}
{% endif %}

## Evaluation Coverage

- **Total Evaluations**: {{ total_evaluations }}
- **Pass Rate**: {{ "%.2f"|format(avg_pass_rate * 100) }}%
- **Critical Assertions**: {{ critical_passed }}/{{ critical_total }} passed
- **Important Assertions**: {{ important_passed }}/{{ important_total }} passed
- **Normal Assertions**: {{ normal_passed }}/{{ normal_total }} passed
{% if cost_analysis %}

## L7: Cost Efficiency

**评测目的**: {{ l7_analysis.purpose }}
**评测方法**: {{ l7_analysis.method }}
**评测结果**: {{ l7_analysis.result_summary }}
**分析**: {{ l7_analysis.analysis }}
**改进建议**:
{% for s in l7_analysis.suggestions %}- {{ s }}
{% endfor %}
{% endif %}
{% if latency_analysis %}

## L8: Execution Latency

**评测目的**: {{ l8_analysis.purpose }}
**评测方法**: {{ l8_analysis.method }}
**评测结果**: {{ l8_analysis.result_summary }}
**分析**: {{ l8_analysis.analysis }}
**改进建议**:
{% for s in l8_analysis.suggestions %}- {{ s }}
{% endfor %}
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
{% endif %}
{% if reliability and reliability.total_evals > 0 %}

## Reliability Analysis

**评测目的**: {{ reliability_analysis.purpose }}
**评测方法**: {{ reliability_analysis.method }}
**评测结果**: {{ reliability_analysis.result_summary }}
**分析**: {{ reliability_analysis.analysis }}
**改进建议**:
{% for s in reliability_analysis.suggestions %}- {{ s }}
{% endfor %}

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

{% if dq %}
## Description Quality

**Score**: {{ "%.0f"|format(dq.score) }}/100

| Dimension | Status |
|-----------|--------|
| WHAT (describes what the skill does) | {{ "✅" if dq.has_what else "❌" }} |
| WHEN (describes when to use it) | {{ "✅" if dq.has_when else "❌" }} |
| Trigger Words (enumerates triggers) | {{ "✅" if dq.has_trigger_words else "❌" }} |
| Exclusion (not when scenarios) | {{ "✅" if dq.has_exclusion else "❌" }} |
| Third Person (objective style) | {{ "✅" if dq.uses_third_person else "❌" }} |
| Trigger Word Count | {{ dq.trigger_word_count }} |

{% if dq.issues %}
**Issues:**
{% for issue in dq.issues %}
- {{ issue }}
{% endfor %}
{% endif %}
{% endif %}
{% if sq %}
## Structure Quality

**Score**: {{ "%.0f"|format(sq.score) }}/100
**SKILL.md Lines**: {{ sq.skill_md_line_count }}
**Over Limit (>500 lines)**: {{ "⚠️" if sq.skill_md_over_limit else "✅" }}
**Has Routing Table**: {{ "✅" if sq.has_routing_table else "❌" }}
**Is Router Pattern**: {{ "✅" if sq.is_router_pattern else "❌" }}

{% if sq.issues %}
**Issues:**
{% for issue in sq.issues %}
- {{ issue }}
{% endfor %}
{% endif %}
{% endif %}
{% if su %}
## Script Usage

**Score**: {{ "%.0f"|format(su.score) }}/100
**Scripts Found**: {{ su.script_count }}

{% if su.script_references %}
**Scripts:**
{% for ref in su.script_references %}
- {{ ref }}
{% endfor %}
{% endif %}

{% if su.issues %}
**Issues:**
{% for issue in su.issues %}
- {{ issue }}
{% endfor %}
{% endif %}
{% endif %}
{% if tp %}
## Tool Permission

**Score**: {{ "%.0f"|format(tp.score) }}/100
**Status**: {{ "✅ PASS" if tp.passed else "❌ FAIL" }}
**Has tools.md**: {{ "✅" if tp.has_tools_md else "❌" }}

{% if tp.dangerous_tools_allowed %}
**Dangerous tools without whitelist:**
{% for tool in tp.dangerous_tools_allowed %}
- {{ tool }}
{% endfor %}
{% endif %}

{% if tp.issues %}
**Issues:**
{% for issue in tp.issues %}
- {{ issue }}
{% endfor %}
{% endif %}
{% endif %}
{% if pd %}
## Progressive Disclosure

**Status**: {{ "✅ PASS" if pd.passed else "❌ FAIL" }}
**Has references/**: {{ pd.has_references_dir }}
**References File Count**: {{ pd.references_file_count }}
**References Token Count**: {{ pd.references_token_count }}
**Runtime-to-Index Ratio**: {{ pd.runtime_to_index_ratio }}

{% if pd.tiered_cost_result %}
### Tiered Cost Analysis

| Tier | Token Count | File Count | Over Budget |
|------|------------|------------|-------------|
| Index | {{ pd.tiered_cost_result.index.token_count }} | {{ pd.tiered_cost_result.index.file_count }} | {{ "⚠️" if pd.tiered_cost_result.index.over_budget else "✅" }} |
| Load | {{ pd.tiered_cost_result.load.token_count }} | {{ pd.tiered_cost_result.load.file_count }} | {{ "⚠️" if pd.tiered_cost_result.load.over_budget else "✅" }} |
| Runtime | {{ pd.tiered_cost_result.runtime.token_count }} | {{ pd.tiered_cost_result.runtime.file_count }} | - |
| **Total** | **{{ pd.tiered_cost_result.total_tokens }}** | - | **All: {{ "⚠️" if not pd.tiered_cost_result.all_within_budget else "✅" }}** |

ROE Ratio: {{ pd.tiered_cost_result.roe_ratio }}
{% endif %}

{% if pd.issues %}
**Issues:**
{% for issue in pd.issues %}
- {{ issue }}
{% endfor %}
{% endif %}
{% endif %}
{% if hk %}
## Hooks Detection

**Score**: {{ "%.0f"|format(hk.score) }}/100
**Status**: {{ "✅ PASS" if hk.passed else "❌ FAIL" }}

**Safety Hooks**: {{ hk.safety_hooks | join(", ") if hk.safety_hooks else "None detected" }}
**Operational Hooks**: {{ hk.operational_hooks | join(", ") if hk.operational_hooks else "None detected" }}

{% if hk.issues %}
**Issues:**
{% for issue in hk.issues %}
- {{ issue }}
{% endfor %}
{% endif %}
{% endif %}

## Eval Results Drill-Down

### Failed Eval Cases

{% set failed_cases = eval_results | selectattr("final_passed", "equalto", false) | list %}
{% if failed_cases %}
| # | Eval Name | Category | Model | Pass Rate | Error |
|---|-----------|----------|-------|-----------|-------|
{% for case in failed_cases %}
| {{ case.get("eval_id", case.get("id", "")) }} | {{ case.get("eval_name", case.get("name", "")) }} | {{ case.get("category", "") }} | {{ case.get("model", case.get("model_name", "")) }} | {{ "%.0f"|format(case.get("pass_rate", 0.0) * 100) }}% | {{ case.get("error", "") }} |
{% endfor %}
{% else %}
_All eval cases passed — no failures to report._
{% endif %}

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
        eval_results: list[dict[str, Any]] | None = None,
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
        l4_score = metrics.get("l4_execution_stability")

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
        summary = create_summary(
            verdict,
            overall_score,
            l1_score,
            l2_score,
            l3_score,
            l4_score if l4_score is not None else 0.0,
        )

        cost_analysis = metrics.get("l7_cost_efficiency")
        latency_analysis = metrics.get("l8_latency", {})
        reliability = metrics.get("reliability", {})
        description_quality = (
            config.get("description_quality") if isinstance(config, dict) else None
        )
        script_usage = config.get("script_usage") if isinstance(config, dict) else None
        tool_permission = config.get("tool_permission") if isinstance(config, dict) else None
        hooks_detection = config.get("hooks_detection") if isinstance(config, dict) else None
        progressive_disclosure = metrics.get("progressive_disclosure") or config.get(
            "progressive_disclosure"
        )
        structure_quality = config.get("structure_quality") if isinstance(config, dict) else None

        suggestions = generate_suggestions(
            metrics, drift, verdict, overall_score, cost_analysis, latency_analysis, reliability
        )

        # Build 5-dimension metric analyses via build_metric_analysis()
        l1_analysis = build_metric_analysis("L1", {
            "score": l1_score,
            "total_trigger_evals": l1_details.get("total_trigger_evals", 0),
            "passed_trigger_evals": l1_details.get("passed_trigger_evals", 0),
            "fp_count": l1_details.get("fp_count", 0),
            "fn_count": l1_details.get("fn_count", 0),
        })
        l2_analysis = build_metric_analysis("L2", {
            "score": l2_score,
            "improvement_percentage": l2_details.get("improvement_percentage", 0.0),
            "with_skill_avg_pass_rate": l2_details.get("with_skill_avg_pass_rate", 0.0),
            "without_skill_avg_pass_rate": l2_details.get("without_skill_avg_pass_rate", 0.0),
        })
        l3_analysis = build_metric_analysis("L3", {
            "score": l3_score,
            "step_coverage_ratio": l3_details.get("step_coverage_ratio", 0.0),
        })
        l4_analysis = build_metric_analysis("L4", {
            "score": l4_score,
            "stdev_deterministic_pass_rate": l4_details.get(
                "stdev_deterministic_pass_rate", 0.0
            ),
            "runs": l4_details.get("runs", 1),
        })
        l5_score_val = num(metrics.get("l5_step_efficiency", 0.0))
        l5_analysis = build_metric_analysis("L5", {
            "score": l5_score_val,
            "violations": metrics.get("l5_violations", 0),
        })
        l6_score_val = num(metrics.get("l6_trajectory_quality", 0.0))
        l6_analysis = build_metric_analysis("L6", {"score": l6_score_val})
        drift_analysis = build_metric_analysis("drift", {
            "models": len(config.get("models", [])),
            "drift_detected": drift_data.get("drift_detected"),
            "highest_severity": drift_data.get("highest_severity", "none"),
            "max_variance": drift_data.get("max_variance", 0.0),
            "average_variance": drift_data.get("average_variance", 0.0),
        })
        l7_analysis = build_metric_analysis("L7", cost_analysis if cost_analysis else {})
        l8_analysis = build_metric_analysis("L8", latency_analysis if latency_analysis else {})
        reliability_analysis = build_metric_analysis(
            "reliability", reliability if reliability else {}
        )

        markdown_report = self.markdown_template.render(
            verdict=verdict,
            overall_score=overall_score,
            summary=summary,
            l1_score=l1_score,
            l2_score=l2_score,
            l3_score=l3_score,
            l4_score=l4_score,
            l5_score=l5_score_val,
            l6_score=l6_score_val,
            l1_analysis=l1_analysis,
            l2_analysis=l2_analysis,
            l3_analysis=l3_analysis,
            l4_analysis=l4_analysis,
            l5_analysis=l5_analysis,
            l6_analysis=l6_analysis,
            drift_analysis=drift_analysis,
            l7_analysis=l7_analysis,
            l8_analysis=l8_analysis,
            reliability_analysis=reliability_analysis,
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
            dq=description_quality,
            su=script_usage,
            tp=tool_permission,
            hk=hooks_detection,
            pd=progressive_disclosure,
            sq=structure_quality,
            eval_results=eval_results or [],
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
        if description_quality:
            json_report["description_quality"] = description_quality
        if script_usage:
            json_report["script_usage"] = script_usage
        if tool_permission:
            json_report["tool_permission"] = tool_permission
        if structure_quality:
            json_report["structure_quality"] = structure_quality

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
        if config.get("description_quality"):
            extras["description_quality"] = config["description_quality"]
        if config.get("script_usage"):
            extras["script_usage"] = config["script_usage"]
        if config.get("tool_permission"):
            extras["tool_permission"] = config["tool_permission"]
        if config.get("structure_quality"):
            extras["structure_quality"] = config["structure_quality"]
        if config.get("progressive_disclosure"):
            extras["progressive_disclosure"] = config["progressive_disclosure"]

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
