"""Tests for engine/reporter.py — report generation functionality."""

from engine.reporter import Reporter


class TestReporter:
    """Test the Reporter class and its report generation functionality."""

    def test_generate_report_basic(self):
        """Test basic report generation."""
        reporter = Reporter()

        # Sample metrics data
        metrics = {
            "overall_score": 0.85,
            "l1_trigger_accuracy": 0.90,
            "l2_with_without_skill_delta": 0.75,
            "l3_step_adherence": 0.80,
            "l4_execution_stability": 0.95,
            "metrics_breakdown": {
                "l1_details": {
                    "total_trigger_evals": 10,
                    "passed_trigger_evals": 9,
                    "trigger_accuracy": 0.90,
                },
                "l2_details": {
                    "with_skill_avg_pass_rate": 0.85,
                    "without_skill_avg_pass_rate": 0.60,
                    "delta": 0.25,
                    "improvement_percentage": 41.67,
                },
                "l3_details": {
                    "total_evaluations": 20,
                    "passing_evaluations": 16,
                    "step_coverage_ratio": 0.80,
                },
                "l4_details": {
                    "deterministic_evals_count": 15,
                    "avg_deterministic_pass_rate": 0.90,
                    "stdev_deterministic_pass_rate": 0.05,
                    "execution_stability": 0.95,
                },
            },
        }

        # Sample drift data
        drift = {
            "drift_detected": False,
            "highest_severity": "none",
            "average_variance": 0.05,
            "max_variance": 0.10,
            "model_pairs_compared": 1,
            "severity_distribution": {"none": 1, "low": 0, "moderate": 0, "high": 0},
            "overall_verdict": "PASS",
            "summary": "No significant drift detected",
        }

        # Sample config data
        config = {
            "total_evaluations": 20,
            "avg_pass_rate": 0.85,
            "critical_passed": 8,
            "critical_total": 10,
            "important_passed": 15,
            "important_total": 18,
            "normal_passed": 45,
            "normal_total": 50,
            "timestamp": "2023-10-01T12:00:00Z",
        }

        markdown_report, json_report = reporter.generate_report(metrics, drift, config)

        # Check that markdown contains expected elements
        assert "# Skill Certification Report" in markdown_report
        assert "**Verdict**: PASS" in markdown_report
        assert "**Overall Score**: 85.00%" in markdown_report
        assert "L1:90%, L2:75%, L3:80%, L4:95%" in markdown_report

        # Check that JSON report has expected structure
        assert json_report["verdict"] == "PASS"
        assert json_report["overall_score"] == 0.85
        assert json_report["metrics"]["l1_trigger_accuracy"] == 0.90
        assert json_report["drift_analysis"]["drift_detected"] is False
        assert json_report["evaluation_coverage"]["total_evaluations"] == 20
        assert len(json_report["improvement_suggestions"]) > 0

    def test_generate_report_with_drift(self):
        """Test report generation with drift detected."""
        reporter = Reporter()

        metrics = {
            "overall_score": 0.60,
            "l1_trigger_accuracy": 0.50,
            "l2_with_without_skill_delta": 0.65,
            "l3_step_adherence": 0.70,
            "l4_execution_stability": 0.55,
            "metrics_breakdown": {
                "l1_details": {
                    "total_trigger_evals": 10,
                    "passed_trigger_evals": 5,
                    "trigger_accuracy": 0.50,
                },
                "l2_details": {
                    "with_skill_avg_pass_rate": 0.70,
                    "without_skill_avg_pass_rate": 0.65,
                    "delta": 0.05,
                    "improvement_percentage": 7.69,
                },
                "l3_details": {
                    "total_evaluations": 20,
                    "passing_evaluations": 14,
                    "step_coverage_ratio": 0.70,
                },
                "l4_details": {
                    "deterministic_evals_count": 10,
                    "avg_deterministic_pass_rate": 0.60,
                    "stdev_deterministic_pass_rate": 0.15,
                    "execution_stability": 0.85,
                },
            },
        }

        drift = {
            "drift_detected": True,
            "highest_severity": "high",
            "average_variance": 0.40,
            "max_variance": 0.50,
            "model_pairs_compared": 2,
            "severity_distribution": {"none": 0, "low": 0, "moderate": 1, "high": 1},
            "overall_verdict": "FAIL",
            "summary": "Significant drift detected between models",
            "drift_results": [
                {
                    "model_a": "model_x",
                    "model_b": "model_y",
                    "severity": "moderate",
                    "variance": 0.30,
                },
                {"model_a": "model_x", "model_b": "model_z", "severity": "high", "variance": 0.50},
            ],
        }

        config = {
            "total_evaluations": 20,
            "avg_pass_rate": 0.60,
            "critical_passed": 5,
            "critical_total": 10,
            "important_passed": 10,
            "important_total": 15,
            "normal_passed": 30,
            "normal_total": 40,
            "timestamp": "2023-10-01T12:00:00Z",
        }

        markdown_report, json_report = reporter.generate_report(metrics, drift, config)

        # Check that markdown reflects the lower score and drift detection
        assert "**Verdict**: FAIL" in markdown_report
        assert "Cross-Model Drift Detected" in markdown_report
        assert "**Highest Severity**: high" in markdown_report
        assert "model_x vs model_y" in markdown_report
        assert "model_x vs model_z" in markdown_report

        # Check JSON report
        assert json_report["verdict"] == "FAIL"
        assert json_report["drift_analysis"]["drift_detected"] is True
        assert json_report["drift_analysis"]["highest_severity"] == "high"

    def test_generate_report_low_score(self):
        """Test report generation with low overall score."""
        reporter = Reporter()

        metrics = {
            "overall_score": 0.40,
            "l1_trigger_accuracy": 0.30,
            "l2_with_without_skill_delta": 0.45,
            "l3_step_adherence": 0.35,
            "l4_execution_stability": 0.50,
            "metrics_breakdown": {
                "l1_details": {
                    "total_trigger_evals": 10,
                    "passed_trigger_evals": 3,
                    "trigger_accuracy": 0.30,
                },
                "l2_details": {
                    "with_skill_avg_pass_rate": 0.50,
                    "without_skill_avg_pass_rate": 0.45,
                    "delta": 0.05,
                    "improvement_percentage": 11.11,
                },
                "l3_details": {
                    "total_evaluations": 20,
                    "passing_evaluations": 7,
                    "step_coverage_ratio": 0.35,
                },
                "l4_details": {
                    "deterministic_evals_count": 8,
                    "avg_deterministic_pass_rate": 0.45,
                    "stdev_deterministic_pass_rate": 0.20,
                    "execution_stability": 0.80,
                },
            },
        }

        drift = {
            "drift_detected": False,
            "highest_severity": "none",
            "average_variance": 0.02,
            "max_variance": 0.05,
            "model_pairs_compared": 1,
            "severity_distribution": {"none": 1, "low": 0, "moderate": 0, "high": 0},
            "overall_verdict": "PASS",
            "summary": "No significant drift detected",
        }

        config = {
            "total_evaluations": 20,
            "avg_pass_rate": 0.40,
            "critical_passed": 2,
            "critical_total": 10,
            "important_passed": 6,
            "important_total": 15,
            "normal_passed": 20,
            "normal_total": 35,
            "timestamp": "2023-10-01T12:00:00Z",
        }

        markdown_report, json_report = reporter.generate_report(metrics, drift, config)

        # Check that markdown reflects the low score
        assert "**Verdict**: FAIL" in markdown_report  # Score < 0.6 should result in FAIL
        assert "Major improvements needed across multiple areas" in markdown_report
        assert "The skill requires significant improvements before certification" in markdown_report

    def test_generate_report_medium_score(self):
        """Test report generation with medium overall score."""
        reporter = Reporter()

        metrics = {
            "overall_score": 0.70,
            "l1_trigger_accuracy": 0.65,
            "l2_with_without_skill_delta": 0.75,
            "l3_step_adherence": 0.70,
            "l4_execution_stability": 0.70,
            "metrics_breakdown": {
                "l1_details": {
                    "total_trigger_evals": 10,
                    "passed_trigger_evals": 6,
                    "trigger_accuracy": 0.65,
                },
                "l2_details": {
                    "with_skill_avg_pass_rate": 0.80,
                    "without_skill_avg_pass_rate": 0.75,
                    "delta": 0.05,
                    "improvement_percentage": 6.67,
                },
                "l3_details": {
                    "total_evaluations": 20,
                    "passing_evaluations": 14,
                    "step_coverage_ratio": 0.70,
                },
                "l4_details": {
                    "deterministic_evals_count": 12,
                    "avg_deterministic_pass_rate": 0.75,
                    "stdev_deterministic_pass_rate": 0.10,
                    "execution_stability": 0.90,
                },
            },
        }

        drift = {
            "drift_detected": False,
            "highest_severity": "none",
            "average_variance": 0.03,
            "max_variance": 0.06,
            "model_pairs_compared": 1,
            "severity_distribution": {"none": 1, "low": 0, "moderate": 0, "high": 0},
            "overall_verdict": "PASS",
            "summary": "No significant drift detected",
        }

        config = {
            "total_evaluations": 20,
            "avg_pass_rate": 0.70,
            "critical_passed": 6,
            "critical_total": 10,
            "important_passed": 12,
            "important_total": 15,
            "normal_passed": 25,
            "normal_total": 30,
            "timestamp": "2023-10-01T12:00:00Z",
        }

        markdown_report, json_report = reporter.generate_report(metrics, drift, config)

        # Check that markdown reflects the medium score
        assert "**Verdict**: PASS_WITH_CAVEATS" in markdown_report  # 0.6 <= score < 0.8
        assert "Several areas need improvement to reach optimal performance" in markdown_report
        assert "skill shows promise but needs improvements" in markdown_report

    def test_generate_suggestions(self):
        """Test improvement suggestion generation."""
        reporter = Reporter()

        metrics = {
            "l1_trigger_accuracy": 0.5,
            "l2_with_without_skill_delta": 0.4,
            "l3_step_adherence": 0.6,
            "l4_execution_stability": 0.7,
        }

        drift = {"drift_detected": True, "highest_severity": "moderate"}

        suggestions = reporter._generate_suggestions(metrics, drift, "PASS_WITH_CAVEATS", 0.65)

        # Check that appropriate suggestions are generated
        assert any("trigger accuracy" in s.lower() for s in suggestions)
        assert any("skill may not be providing sufficient value" in s.lower() for s in suggestions)
        assert any("address cross-model drift" in s.lower() for s in suggestions)

    def test_create_summary(self):
        """Test executive summary creation."""
        reporter = Reporter()

        summary = reporter._create_summary("PASS", 0.85, 0.9, 0.8, 0.85, 0.85)
        assert "PASS" in summary
        assert "L1:90%, L2:80%, L3:85%, L4:85%" in summary
        assert "performs well" in summary.lower()

        summary_low = reporter._create_summary("FAIL", 0.4, 0.3, 0.4, 0.5, 0.4)
        assert "FAIL" in summary_low
        assert "requires significant improvements" in summary_low.lower()

    # ── Suggestions: cost, latency, reliability branches ───

    def test_suggestions_cost_high_delta(self):
        """Suggestions warn when cost_delta_pct > 50%."""
        reporter = Reporter()
        metrics = {
            "l1_trigger_accuracy": 0.9,
            "l2_with_without_skill_delta": 0.9,
            "l3_step_adherence": 0.9,
            "l4_execution_stability": 0.9,
        }
        drift = {"drift_detected": False}
        cost = {"cost_delta_pct": 0.8, "cost_efficiency": 0.05}
        suggestions = reporter._generate_suggestions(
            metrics, drift, "PASS", 0.9, cost_analysis=cost
        )
        assert any("cost" in s.lower() for s in suggestions)
        assert any("low cost efficiency" in s.lower() for s in suggestions)

    def test_suggestions_latency_overhead(self):
        """Suggestions warn when latency overhead > 50%."""
        reporter = Reporter()
        metrics = {
            "l1_trigger_accuracy": 0.9,
            "l2_with_without_skill_delta": 0.9,
            "l3_step_adherence": 0.9,
            "l4_execution_stability": 0.9,
        }
        drift = {"drift_detected": False}
        latency = {"overhead_pct": 60, "slow_with_skill": 3}
        suggestions = reporter._generate_suggestions(
            metrics, drift, "PASS", 0.9, latency_analysis=latency
        )
        assert any("latency" in s.lower() for s in suggestions)
        assert any("30s threshold" in s for s in suggestions)

    def test_suggestions_reliability_errors(self):
        """Suggestions warn on high error rate and specific categories."""
        reporter = Reporter()
        metrics = {
            "l1_trigger_accuracy": 0.9,
            "l2_with_without_skill_delta": 0.9,
            "l3_step_adherence": 0.9,
            "l4_execution_stability": 0.9,
        }
        drift = {"drift_detected": False}
        reliability = {
            "error_rate": 0.25,
            "retry_stats": {"max_retries": 5},
            "errors_by_category": {"timeout": 3, "rate_limit": 2},
        }
        suggestions = reporter._generate_suggestions(
            metrics, drift, "PASS", 0.9, reliability=reliability
        )
        assert any("error rate" in s.lower() for s in suggestions)
        assert any("max retries" in s.lower() for s in suggestions)
        assert any("timeout" in s.lower() for s in suggestions)
        assert any("rate limit" in s.lower() for s in suggestions)

    def test_suggestions_all_good(self):
        """When all metrics are good, suggest strong performance."""
        reporter = Reporter()
        metrics = {
            "l1_trigger_accuracy": 0.95,
            "l2_with_without_skill_delta": 0.9,
            "l3_step_adherence": 0.95,
            "l4_execution_stability": 0.95,
        }
        drift = {"drift_detected": False}
        suggestions = reporter._generate_suggestions(metrics, drift, "PASS", 0.95)
        assert any("strong" in s.lower() for s in suggestions)

    # ── Verdict with drift_verdict=PASS_WITH_CAVEATS ────────

    def test_verdict_drift_caveats(self):
        """Verdict is PASS_WITH_CAVEATS when drift says so and score < 0.8."""
        reporter = Reporter()
        metrics = {
            "overall_score": 0.70,
            "l1_trigger_accuracy": 0.70,
            "l2_with_without_skill_delta": 0.70,
            "l3_step_adherence": 0.70,
            "l4_execution_stability": 0.70,
            "metrics_breakdown": {
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
                "l4_details": {"execution_stability": 0.0, "stdev_deterministic_pass_rate": 0.0},
            },
        }
        drift = {
            "drift_detected": False,
            "highest_severity": "none",
            "average_variance": 0.0,
            "max_variance": 0.0,
            "overall_verdict": "PASS_WITH_CAVEATS",
        }
        config = {"total_evaluations": 0, "avg_pass_rate": 0.0, "timestamp": ""}
        _, json_report = reporter.generate_report(metrics, drift, config)
        assert json_report["verdict"] == "PASS_WITH_CAVEATS"

    # ── JSON report includes cost/latency/reliability/maintainability ──

    def test_json_report_includes_optional_sections(self):
        """JSON report includes cost, latency, reliability, maintainability when present."""
        reporter = Reporter()
        metrics = {
            "overall_score": 0.85,
            "l1_trigger_accuracy": 0.9,
            "l2_with_without_skill_delta": 0.8,
            "l3_step_adherence": 0.85,
            "l4_execution_stability": 0.9,
            "l7_cost_efficiency": {
                "cost_per_eval": 0.01,
                "total_cost": 0.10,
                "cost_with_skill": 0.06,
                "cost_without_skill": 0.04,
                "cost_delta_pct": 0.5,
                "cost_efficiency": 0.4,
            },
            "l8_latency": {
                "with_skill": {"p50": 5.0, "p95": 8.0, "mean": 5.5},
                "without_skill": {"p50": 3.0, "p95": 6.0, "mean": 3.5},
                "overhead_pct": 50,
                "slow_with_skill": 0,
                "slow_without_skill": 0,
            },
            "reliability": {
                "total_evals": 10,
                "success_rate": 0.9,
                "error_rate": 0.1,
                "retry_stats": {"avg_retries": 0.5, "max_retries": 2},
                "errors_by_category": {},
            },
            "metrics_breakdown": {
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
                "l4_details": {"execution_stability": 0.0, "stdev_deterministic_pass_rate": 0.0},
            },
        }
        maintainability = {
            "total_score": 80,
            "grade": "B",
            "readability_score": 25,
            "completeness_score": 30,
            "freshness_score": 25,
            "readability_details": {"avg_line_length": 80, "max_depth": 2, "todo_count": 0},
            "completeness_details": {
                "has_workflow": True,
                "has_anti_patterns": True,
                "has_triggers": True,
            },
            "freshness_details": {"outdated_refs": 0},
        }
        drift = {
            "drift_detected": False,
            "highest_severity": "none",
            "average_variance": 0.0,
            "max_variance": 0.0,
            "overall_verdict": "PASS",
        }
        config = {
            "total_evaluations": 10,
            "avg_pass_rate": 0.85,
            "models": "model-a",
            "timestamp": "",
        }
        _, json_report = reporter.generate_report(
            metrics, drift, config, maintainability=maintainability
        )
        assert "cost_analysis" in json_report
        assert "latency_analysis" in json_report
        assert "reliability" in json_report
        assert "maintainability" in json_report

    # ── Multi-skill report ──────────────────────────────────

    def test_multi_skill_with_conflicts(self):
        """Multi-skill report includes conflict details."""
        reporter = Reporter()
        metrics = {
            "overall_score": 0.8,
            "l1_trigger_accuracy": 0.9,
            "l2_with_without_skill_delta": 0.8,
            "l3_step_adherence": 0.85,
            "l4_execution_stability": 0.9,
            "metrics_breakdown": {
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
                "l4_details": {"execution_stability": 0.0, "stdev_deterministic_pass_rate": 0.0},
            },
        }
        drift = {
            "drift_detected": False,
            "highest_severity": "none",
            "average_variance": 0.0,
            "max_variance": 0.0,
            "overall_verdict": "PASS",
        }
        config = {"total_evaluations": 10, "avg_pass_rate": 0.8, "timestamp": ""}
        multi = {
            "skill_count": 3,
            "overall_risk": "moderate",
            "summary": "Some conflicts detected",
            "trigger_conflicts": 2,
            "prompt_contamination_conflicts": 1,
            "token_overflow_conflicts": 0,
            "conflicts": [
                {
                    "severity": "moderate",
                    "conflict_type": "trigger_overlap",
                    "skill_a": "skill-a",
                    "skill_b": "skill-b",
                    "description": "Overlapping triggers",
                },
            ],
        }
        md, json_r = reporter.generate_report_with_multi_skill(metrics, drift, config, multi)
        assert "Multi-Skill Analysis" in md
        assert "MODERATE" in md
        assert json_r["multi_skill_analysis"]["skill_count"] == 3

    def test_multi_skill_without_conflicts(self):
        """Multi-skill report with no conflicts."""
        reporter = Reporter()
        metrics = {
            "overall_score": 0.9,
            "l1_trigger_accuracy": 0.9,
            "l2_with_without_skill_delta": 0.9,
            "l3_step_adherence": 0.9,
            "l4_execution_stability": 0.9,
            "metrics_breakdown": {
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
                "l4_details": {"execution_stability": 0.0, "stdev_deterministic_pass_rate": 0.0},
            },
        }
        drift = {
            "drift_detected": False,
            "highest_severity": "none",
            "average_variance": 0.0,
            "max_variance": 0.0,
            "overall_verdict": "PASS",
        }
        config = {"total_evaluations": 10, "avg_pass_rate": 0.9, "timestamp": ""}
        multi = {
            "skill_count": 2,
            "overall_risk": "none",
            "summary": "No conflicts",
            "trigger_conflicts": 0,
            "prompt_contamination_conflicts": 0,
            "token_overflow_conflicts": 0,
            "conflicts": [],
        }
        md, json_r = reporter.generate_report_with_multi_skill(metrics, drift, config, multi)
        assert "Multi-Skill Analysis" in md
        assert "No conflicts" in md

    # ── Stress report ──────────────────────────────────────

    def test_stress_report(self):
        """Stress test report generates correctly."""
        reporter = Reporter()
        metrics = {
            "overall_score": 0.85,
            "l1_trigger_accuracy": 0.9,
            "l2_with_without_skill_delta": 0.8,
            "l3_step_adherence": 0.85,
            "l4_execution_stability": 0.9,
            "metrics_breakdown": {
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
                "l4_details": {"execution_stability": 0.0, "stdev_deterministic_pass_rate": 0.0},
            },
        }
        drift = {
            "drift_detected": False,
            "highest_severity": "none",
            "average_variance": 0.0,
            "max_variance": 0.0,
            "overall_verdict": "PASS",
        }
        config = {"total_evaluations": 10, "avg_pass_rate": 0.85, "timestamp": ""}
        stress = {
            "verdict": "PASS",
            "scalability_score": 85.0,
            "total_evals": 100,
            "completed": 98,
            "failed": 2,
            "timed_out": 0,
            "errored": 2,
            "completion_rate": 0.98,
            "fairness_ratio": 0.95,
            "latency": {"avg": 3.5, "min": 1.0, "max": 8.0, "median": 3.2, "p95": 7.0, "p99": 8.0},
            "memory_mb_peak": 256.0,
            "model_exec_counts": {"model-a": 50, "model-b": 50},
        }
        md, json_r = reporter.generate_report_with_stress(metrics, drift, config, stress)
        assert "Scalability" in md
        assert "85.0/100" in md
        assert "model-a: 50" in md
        assert json_r["scalability"]["verdict"] == "PASS"

    def test_stress_report_no_model_counts(self):
        """Stress report works without model_exec_counts."""
        reporter = Reporter()
        metrics = {
            "overall_score": 0.85,
            "l1_trigger_accuracy": 0.9,
            "l2_with_without_skill_delta": 0.8,
            "l3_step_adherence": 0.85,
            "l4_execution_stability": 0.9,
            "metrics_breakdown": {
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
                "l4_details": {"execution_stability": 0.0, "stdev_deterministic_pass_rate": 0.0},
            },
        }
        drift = {
            "drift_detected": False,
            "highest_severity": "none",
            "average_variance": 0.0,
            "max_variance": 0.0,
            "overall_verdict": "PASS",
        }
        config = {"total_evaluations": 10, "avg_pass_rate": 0.85, "timestamp": ""}
        stress = {
            "verdict": "FAIL",
            "scalability_score": 30.0,
            "total_evals": 100,
            "completed": 50,
            "failed": 50,
            "timed_out": 10,
            "errored": 40,
            "completion_rate": 0.5,
            "fairness_ratio": 0.3,
            "latency": {
                "avg": 15.0,
                "min": 1.0,
                "max": 60.0,
                "median": 12.0,
                "p95": 55.0,
                "p99": 60.0,
            },
            "memory_mb_peak": 512.0,
            "model_exec_counts": {},
        }
        md, json_r = reporter.generate_report_with_stress(metrics, drift, config, stress)
        assert "Scalability" in md
        assert "Model execution counts" not in md

    # ── Assertion breakdown from _results ───────────────────

    def test_assertion_breakdown_from_results(self):
        """Assertion breakdown computed from metrics._results instead of config."""
        reporter = Reporter()
        metrics = {
            "overall_score": 0.85,
            "l1_trigger_accuracy": 0.9,
            "l2_with_without_skill_delta": 0.8,
            "l3_step_adherence": 0.85,
            "l4_execution_stability": 0.9,
            "metrics_breakdown": {
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
                "l4_details": {"execution_stability": 0.0, "stdev_deterministic_pass_rate": 0.0},
            },
            "_results": [
                {
                    "pass_rate": 0.9,
                    "grade": {
                        "assertion_results": [
                            {"passed": True, "assertion": {"weight": 3}},
                            {"passed": True, "assertion": {"weight": 2}},
                            {"passed": False, "assertion": {"weight": 1}},
                        ]
                    },
                },
                {
                    "pass_rate": 0.7,
                    "grade": {
                        "assertion_results": [
                            {"passed": False, "assertion": {"weight": 3}},
                            {"passed": True, "assertion": {"weight": 2}},
                            {"passed": True, "assertion": {"weight": 1}},
                        ]
                    },
                },
            ],
        }
        drift = {
            "drift_detected": False,
            "highest_severity": "none",
            "average_variance": 0.0,
            "max_variance": 0.0,
            "overall_verdict": "PASS",
        }
        config = {"timestamp": ""}
        _, json_r = reporter.generate_report(metrics, drift, config)
        ab = json_r["evaluation_coverage"]["assertion_breakdown"]
        assert ab["critical"] == {"passed": 1, "total": 2}
        assert ab["important"] == {"passed": 2, "total": 2}
        assert ab["normal"] == {"passed": 1, "total": 2}

    # ── Multi-skill with to_dict conflict ───────────────────

    def test_multi_skill_with_to_dict_conflicts(self):
        """Conflict objects with to_dict() method are serialized correctly."""

        class MockConflict:
            def to_dict(self):
                return {
                    "severity": "high",
                    "conflict_type": "token_overflow",
                    "skill_a": "A",
                    "skill_b": "B",
                    "description": "Overflow",
                }

        reporter = Reporter()
        metrics = {
            "overall_score": 0.8,
            "l1_trigger_accuracy": 0.9,
            "l2_with_without_skill_delta": 0.8,
            "l3_step_adherence": 0.85,
            "l4_execution_stability": 0.9,
            "metrics_breakdown": {
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
                "l4_details": {"execution_stability": 0.0, "stdev_deterministic_pass_rate": 0.0},
            },
        }
        drift = {
            "drift_detected": False,
            "highest_severity": "none",
            "average_variance": 0.0,
            "max_variance": 0.0,
            "overall_verdict": "PASS",
        }
        config = {"total_evaluations": 5, "avg_pass_rate": 0.8, "timestamp": ""}
        multi = {
            "skill_count": 2,
            "overall_risk": "high",
            "summary": "Token overflow",
            "trigger_conflicts": 0,
            "prompt_contamination_conflicts": 0,
            "token_overflow_conflicts": 1,
            "conflicts": [MockConflict()],
        }
        md, json_r = reporter.generate_report_with_multi_skill(metrics, drift, config, multi)
        assert "token_overflow" in md
        assert json_r["multi_skill_analysis"]["conflicts"][0]["severity"] == "high"
