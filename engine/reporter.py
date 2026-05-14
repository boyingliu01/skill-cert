"""Reporting module for skill-cert engine — generates Markdown and JSON reports."""

from typing import Dict, Any, Tuple, List
from datetime import datetime, timezone
from jinja2 import Environment


class Reporter:
    """Generates Markdown and JSON reports for skill certification results."""
    
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
- **Details**: {{ l1_details.total_trigger_evals }} trigger evaluations, {{ l1_details.passed_trigger_evals }} passed
- **Accuracy**: {{ "%.2f"|format(l1_details.trigger_accuracy * 100) }}%

### L2: With/Without Skill Delta
- **Score**: {{ "%.2f"|format(l2_score * 100) }}%
- **With Skill Avg**: {{ "%.2f"|format(l2_details.with_skill_avg_pass_rate * 100) }}%
- **Without Skill Avg**: {{ "%.2f"|format(l2_details.without_skill_avg_pass_rate * 100) }}%
- **Improvement**: {{ "%.2f"|format(l2_details.improvement_percentage) }}%

### L3: Step Adherence
- **Score**: {{ "%.2f"|format(l3_score * 100) }}%
- **Coverage**: {{ "%.2f"|format(l3_details.step_coverage_ratio * 100) }}% of evaluations covered expected steps

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
- {{ result.model_a }} vs {{ result.model_b }}: {{ result.severity }} severity (variance: {{ "%.3f"|format(result.variance) }})
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
| P50 | {{ "%.2f"|format(latency_analysis.with_skill.p50) }}s | {{ "%.2f"|format(latency_analysis.without_skill.p50) }}s | {% if latency_analysis.with_skill.p50 > latency_analysis.without_skill.p50 %}+{{ "%.1f"|format(((latency_analysis.with_skill.p50 - latency_analysis.without_skill.p50) / latency_analysis.without_skill.p50 * 100) if latency_analysis.without_skill.p50 > 0 else 0) }}%{% else %}—{% endif %} |
| P95 | {{ "%.2f"|format(latency_analysis.with_skill.p95) }}s | {{ "%.2f"|format(latency_analysis.without_skill.p95) }}s | {% if latency_analysis.with_skill.p95 > latency_analysis.without_skill.p95 %}+{{ "%.1f"|format(((latency_analysis.with_skill.p95 - latency_analysis.without_skill.p95) / latency_analysis.without_skill.p95 * 100) if latency_analysis.without_skill.p95 > 0 else 0) }}%{% else %}—{% endif %} |
| Mean | {{ "%.2f"|format(latency_analysis.with_skill.mean) }}s | {{ "%.2f"|format(latency_analysis.without_skill.mean) }}s | — |
| Slow (>30s) | {{ latency_analysis.slow_with_skill }} | {{ latency_analysis.slow_without_skill }} | +{{ latency_analysis.slow_with_skill - latency_analysis.slow_without_skill }} |
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
- **Max Testgen Rounds**: {{ config_info.max_testgen_rounds }}
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
⚠️ Average line length exceeds 100 characters: {{ maintainability.readability_details.avg_line_length }}
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
    
    def generate_report(
        self, 
        metrics: Dict[str, Any], 
        drift: Dict[str, Any], 
        config: Dict[str, Any],
        maintainability: Dict[str, Any] | None = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Generate Markdown and JSON reports from metrics and drift analysis.
        
        Args:
            metrics: Metrics calculation results from MetricsCalculator
            drift: Drift analysis results from DriftDetector
            config: Configuration parameters
            
        Returns:
            Tuple of (markdown_report, json_report)
        """
        # Prepare data for the template
        overall_score = metrics.get('overall_score', 0.0)
        l1_score = metrics.get('l1_trigger_accuracy', 0.0)
        l2_score = metrics.get('l2_with_without_skill_delta', 0.0)
        l3_score = metrics.get('l3_step_adherence', 0.0)
        l4_score = metrics.get('l4_execution_stability', 0.0)
        
        l1_details = metrics.get('metrics_breakdown', {}).get('l1_details', {})
        l2_details = metrics.get('metrics_breakdown', {}).get('l2_details', {})
        l3_details = metrics.get('metrics_breakdown', {}).get('l3_details', {})
        l4_details = metrics.get('metrics_breakdown', {}).get('l4_details', {})
        
        # Determine verdict based on overall score and drift analysis
        # If drift analysis indicates failure, use that verdict regardless of score
        drift_verdict = drift.get('overall_verdict', 'PASS')
        if drift_verdict == 'FAIL':
            verdict = 'FAIL'
        elif drift_verdict == 'PASS_WITH_CAVEATS' and overall_score < 0.8:
            verdict = 'PASS_WITH_CAVEATS'
        elif overall_score >= 0.8:
            verdict = "PASS"
        elif overall_score >= 0.6:
            verdict = "PASS_WITH_CAVEATS"
        else:
            verdict = "FAIL"
        
        # Prepare drift data
        drift_detected = drift.get('drift_detected', False)
        highest_severity = drift.get('highest_severity', 'none')
        average_variance = drift.get('average_variance', 0.0)
        max_variance = drift.get('max_variance', 0.0)
        drift_results = drift.get('drift_results', [])  # This would come from drift analysis
        
        # Calculate evaluation coverage stats
        total_evaluations = config.get('total_evaluations', 0)
        avg_pass_rate = config.get('avg_pass_rate', 0.0)
        critical_passed = config.get('critical_passed', 0)
        critical_total = config.get('critical_total', 0)
        important_passed = config.get('important_passed', 0)
        important_total = config.get('important_total', 0)
        normal_passed = config.get('normal_passed', 0)
        normal_total = config.get('normal_total', 0)
        
        # Cost analysis
        cost_analysis = metrics.get('l7_cost_efficiency')
        
        # Latency analysis
        latency_analysis = metrics.get('l8_latency', {})
        
        # Reliability analysis
        reliability = metrics.get('reliability', {})
        
        # Generate improvement suggestions
        suggestions = self._generate_suggestions(
            metrics, drift, verdict, overall_score, cost_analysis, latency_analysis, reliability
        )
        
        # Evaluation coverage
        _results = metrics.get('_results', [])
        total_evaluations = len(_results) or config.get('total_evaluations', 0)
        avg_pass_rate = sum(r.get('pass_rate', 0) for r in _results) / len(_results) if _results else config.get('avg_pass_rate', 0.0)
        
        # Assertion breakdown from results or config fallback
        critical_passed = 0
        critical_total = 0
        important_passed = 0
        important_total = 0
        normal_passed = 0
        normal_total = 0
        
        if _results:
            for r in _results:
                for a in r.get('grade', {}).get('assertion_results', []):
                    weight = a.get('assertion', {}).get('weight', 1)
                    if weight >= 3:
                        critical_total += 1
                        if a.get('passed'):
                            critical_passed += 1
                    elif weight == 2:
                        important_total += 1
                        if a.get('passed'):
                            important_passed += 1
                    else:
                        normal_total += 1
                        if a.get('passed'):
                            normal_passed += 1
        else:
            critical_passed = config.get('critical_passed', 0)
            critical_total = config.get('critical_total', 0)
            important_passed = config.get('important_passed', 0)
            important_total = config.get('important_total', 0)
            normal_passed = config.get('normal_passed', 0)
            normal_total = config.get('normal_total', 0)
        
        # Create summary
        summary = self._create_summary(verdict, overall_score, l1_score, l2_score, l3_score, l4_score)
        
        # Prepare config info for report
        config_info = None
        if config:
            models = config.get('models', [])
            model_names = ', '.join(m.get('model_name', m.get('name', 'unknown')) for m in models) if isinstance(models, list) else str(models)
            config_info = {
                'models': model_names or 'Not specified',
                'max_concurrency': config.get('max_concurrency', 5),
                'rate_limit_rpm': config.get('rate_limit_rpm', 60),
                'request_timeout': config.get('request_timeout', 120),
                'judge_temperature': config.get('judge_temperature', 0.0),
                'max_testgen_rounds': config.get('max_testgen_rounds', 3),
            }
        
        # Prepare benchmark info
        total_tokens = config.get('total_tokens', 0)
        if not total_tokens:
            total_tokens = config.get('total_evaluator_tokens', 0)
        _results = metrics.get('_results', [])
        total_eval_tokens = sum(r.get('tokens_used', 0) for r in _results) if _results else 0
        benchmark_info = {
            'timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
            'spec_version': 'v2.0',
            'total_requirements': 11,
            'total_acceptance_criteria': 74,
            'test_coverage': f'{len(_results)} evals, L1-L7 metrics computed',
            'total_tokens': f'{total_eval_tokens:,}' if total_eval_tokens else 'N/A (local models)',
        }
        
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
            drift_detected=drift_detected,
            highest_severity=highest_severity,
            average_variance=average_variance,
            max_variance=max_variance,
            drift_results=drift_results,
            total_evaluations=total_evaluations,
            avg_pass_rate=avg_pass_rate,
            critical_passed=critical_passed,
            critical_total=critical_total,
            important_passed=important_passed,
            important_total=important_total,
            normal_passed=normal_passed,
            normal_total=normal_total,
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
            "evaluation_coverage": {
                "total_evaluations": total_evaluations,
                "avg_pass_rate": avg_pass_rate,
                "assertion_breakdown": {
                    "critical": {"passed": critical_passed, "total": critical_total},
                    "important": {"passed": important_passed, "total": important_total},
                    "normal": {"passed": normal_passed, "total": normal_total}
                }
            },
            "improvement_suggestions": suggestions,
            "timestamp": config.get("timestamp", ""),
            "config": config,
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
    
    def _generate_suggestions(
        self,
        metrics: Dict[str, Any],
        drift: Dict[str, Any],
        verdict: str,
        overall_score: float,
        cost_analysis: Dict[str, Any] | None = None,
        latency_analysis: Dict[str, Any] | None = None,
        reliability: Dict[str, Any] | None = None,
    ) -> List[str]:
        """Generate improvement suggestions based on metrics and drift analysis."""
        suggestions = []
        
        # L1 suggestions
        l1_score = metrics.get('l1_trigger_accuracy', 0.0)
        if l1_score < 0.7:
            suggestions.append("Improve trigger accuracy - skill may not be properly detecting trigger conditions")
        
        # L2 suggestions
        l2_score = metrics.get('l2_with_without_skill_delta', 0.0)
        if l2_score < 0.5:
            suggestions.append("Skill may not be providing sufficient value - consider enhancing core functionality")
        
        # L3 suggestions
        l3_score = metrics.get('l3_step_adherence', 0.0)
        if l3_score < 0.7:
            suggestions.append("Improve adherence to expected workflow steps")
        
        # L4 suggestions
        l4_score = metrics.get('l4_execution_stability', 0.0)
        if l4_score < 0.8:
            suggestions.append("Address execution instability - results vary significantly across runs")
        
        # Drift suggestions
        if drift.get('drift_detected', False):
            suggestions.append(f"Address cross-model drift (highest severity: {drift.get('highest_severity', 'none')})")
        
        # Overall suggestions
        if overall_score < 0.6:
            suggestions.append("Major improvements needed across multiple areas")
        elif overall_score < 0.8:
            suggestions.append("Several areas need improvement to reach optimal performance")
        
        # Cost suggestions
        if cost_analysis and cost_analysis.get("cost_delta_pct", 0) > 0.5:
            suggestions.append(f"Skill increases costs by {cost_analysis['cost_delta_pct']:.0%} — consider optimizing prompt or reducing verbosity")
        if cost_analysis and cost_analysis.get("cost_efficiency", 0) < 0.1 and cost_analysis.get("cost_delta_pct", 0) > 0:
            suggestions.append("Low cost efficiency — quality gains don't justify cost increase")
        
        # Latency suggestions
        if latency_analysis and latency_analysis.get("overhead_pct", 0) > 50:
            suggestions.append(f"Skill adds {latency_analysis['overhead_pct']}% latency overhead — optimize prompt or reduce steps")
        slow_count = latency_analysis.get("slow_with_skill", 0) if latency_analysis else 0
        if slow_count > 0:
            suggestions.append(f"{slow_count} requests exceeded 30s threshold — consider async processing or timeouts")
        
        # Reliability suggestions
        if reliability and reliability.get("error_rate", 0) > 0.2:
            suggestions.append(f"Error rate is {reliability['error_rate']:.0%} — implement retry logic or fallback models")
        if reliability and reliability.get("retry_stats", {}).get("max_retries", 0) > 2:
            suggestions.append(f"Max retries of {reliability['retry_stats']['max_retries']} detected — consider backoff or circuit breaker")
        if reliability and reliability.get("errors_by_category"):
            cats = list(reliability['errors_by_category'].keys())
            if "timeout" in cats:
                suggestions.append("Timeout errors detected — increase timeout or optimize prompts")
            if "rate_limit" in cats:
                suggestions.append("Rate limit errors detected — reduce concurrency or request rate")
        
        if not suggestions:
            suggestions.append("Performance is strong across all metrics")
        
        return suggestions
    
    def _create_summary(self, verdict: str, overall_score: float, l1: float, l2: float, l3: float, l4: float) -> str:
        """Create executive summary based on results."""
        summary_parts = [f"This skill certification resulted in a {verdict} verdict."]
        
        if overall_score >= 0.8:
            summary_parts.append("The skill performs well across all evaluation dimensions.")
        elif overall_score >= 0.6:
            summary_parts.append("The skill shows promise but needs improvements in certain areas.")
        else:
            summary_parts.append("The skill requires significant improvements before certification.")
        
        summary_parts.append(
            f"L1:{l1:.0%}, L2:{l2:.0%}, L3:{l3:.0%}, L4:{l4:.0%}"
        )
        
        return " ".join(summary_parts)

    def generate_report_with_multi_skill(
        self,
        metrics: Dict[str, Any],
        drift: Dict[str, Any],
        config: Dict[str, Any],
        multi_skill_report: Dict[str, Any],
    ) -> Tuple[str, Dict[str, Any]]:
        safe_metrics = {
            "overall_score": metrics.get("overall_score", 0.5),
            "l1_trigger_accuracy": metrics.get("l1_trigger_accuracy", 0.0),
            "l2_with_without_skill_delta": metrics.get("l2_with_without_skill_delta", 0.0),
            "l3_step_adherence": metrics.get("l3_step_adherence", 0.0),
            "l4_execution_stability": metrics.get("l4_execution_stability", 0.0),
            "metrics_breakdown": metrics.get("metrics_breakdown", {
                "l1_details": {"total_trigger_evals": 0, "passed_trigger_evals": 0, "trigger_accuracy": 0.0},
                "l2_details": {"with_skill_avg_pass_rate": 0.0, "without_skill_avg_pass_rate": 0.0, "improvement_percentage": 0.0},
                "l3_details": {"step_coverage_ratio": 0.0},
                "l4_details": {"execution_stability": 0.0, "stdev_deterministic_pass_rate": 0.0},
            }),
        }
        md_report, json_report = self.generate_report(safe_metrics, drift, config)

        multi_md = self._build_multi_skill_section(multi_skill_report)
        md_report = md_report.replace("\n## Raw Results", f"\n{multi_md}\n## Raw Results")

        json_report["multi_skill_analysis"] = {
            "skill_count": multi_skill_report.get("skill_count", 0),
            "overall_risk": multi_skill_report.get("overall_risk", "none"),
            "summary": multi_skill_report.get("summary", ""),
            "conflicts": [c.to_dict() if hasattr(c, "to_dict") else c for c in multi_skill_report.get("conflicts", [])],
            "trigger_conflicts": multi_skill_report.get("trigger_conflicts", 0),
            "prompt_contamination_conflicts": multi_skill_report.get("prompt_contamination_conflicts", 0),
            "token_overflow_conflicts": multi_skill_report.get("token_overflow_conflicts", 0),
        }

        return md_report, json_report

    def _build_multi_skill_section(self, report: Dict[str, Any]) -> str:
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

    def generate_report_with_stress(
        self,
        metrics: Dict[str, Any],
        drift: Dict[str, Any],
        config: Dict[str, Any],
        stress_result: Dict[str, Any],
    ) -> Tuple[str, Dict[str, Any]]:
        md_report, json_report = self.generate_report(metrics, drift, config)

        stress_section = self._build_stress_section(stress_result)
        md_report = md_report.replace("\n## Raw Results", f"\n{stress_section}\n## Raw Results")

        json_report["scalability"] = stress_result
        return md_report, json_report

    def _build_stress_section(self, result: Dict[str, Any]) -> str:
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