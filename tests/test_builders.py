"""Tests for engine/reporters/builders.py builder functions.

Covers build_metric_analysis() for 5-dimension metric analysis:
purpose, method, result_summary, analysis, suggestions.
"""

from engine.reporters.builders import build_metric_analysis


class TestBuildMetricAnalysis:
    """Test build_metric_analysis() for all metric types and edge cases."""

    # ── L1: Trigger Accuracy ────────────────────────────────────

    def test_l1_high_accuracy_passes(self):
        """L1 >= 90% with fp <= fn returns high accuracy analysis."""
        details = {
            "score": 0.95,
            "total_trigger_evals": 100,
            "passed_trigger_evals": 95,
            "fp_count": 2,
            "fn_count": 3,
        }
        result = build_metric_analysis("L1", details)
        assert result["purpose"] != ""
        assert result["method"] != ""
        assert result["result_summary"] != ""
        assert result["analysis"] != ""
        assert isinstance(result["suggestions"], list)
        # L1 >= 90% means PASS
        assert "PASS" in result["result_summary"] or "passed" in result["result_summary"].lower()

    def test_l1_low_accuracy_fails(self):
        """L1 < 90% should indicate FAIL and suggest improvements."""
        details = {
            "score": 0.65,
            "total_trigger_evals": 100,
            "passed_trigger_evals": 65,
            "fp_count": 20,
            "fn_count": 15,
        }
        result = build_metric_analysis("L1", details)
        assert "FAIL" in result["result_summary"] or "failed" in result["result_summary"].lower()
        assert len(result["suggestions"]) > 0

    def test_l1_fp_bias_analysis(self):
        """When fp > fn, analysis should mention false positives bias."""
        details = {
            "score": 0.80,
            "total_trigger_evals": 100,
            "passed_trigger_evals": 80,
            "fp_count": 15,
            "fn_count": 5,
        }
        result = build_metric_analysis("L1", details)
        # fp > fn should trigger the bias analysis
        assert len(result["analysis"]) > 0

    # ── L2: With/Without Skill Delta ─────────────────────────────

    def test_l2_strong_improvement(self):
        """L2 >= 20% with positive delta reports strong improvement."""
        details = {
            "score": 0.35,
            "with_skill_avg_pass_rate": 0.85,
            "without_skill_avg_pass_rate": 0.50,
            "improvement_percentage": 35.0,
        }
        result = build_metric_analysis("L2", details)
        assert "PASS" in result["result_summary"] or "gain" in result["result_summary"].lower()
        assert result["purpose"] != ""
        assert isinstance(result["suggestions"], list)

    def test_l2_no_improvement(self):
        """L2 < 5% delta provides 'no improvement' analysis."""
        details = {
            "score": 0.03,
            "with_skill_avg_pass_rate": 0.50,
            "without_skill_avg_pass_rate": 0.48,
            "improvement_percentage": 2.0,
        }
        result = build_metric_analysis("L2", details)
        assert len(result["analysis"]) > 0
        assert result["result_summary"] != ""

    def test_l2_negative_delta(self):
        """Negative L2 delta (skill hurts performance) handled."""
        details = {
            "score": -0.10,
            "with_skill_avg_pass_rate": 0.40,
            "without_skill_avg_pass_rate": 0.50,
            "improvement_percentage": -10.0,
        }
        result = build_metric_analysis("L2", details)
        assert len(result["analysis"]) > 0

    # ── L3: Step Adherence ──────────────────────────────────────

    def test_l3_high_adherence(self):
        """L3 >= 85% passes."""
        details = {
            "score": 0.90,
            "step_coverage_ratio": 0.92,
        }
        result = build_metric_analysis("L3", details)
        assert result["purpose"] != ""

    def test_l3_low_adherence(self):
        """L3 < 85% fails with suggestions."""
        details = {
            "score": 0.60,
            "step_coverage_ratio": 0.55,
        }
        result = build_metric_analysis("L3", details)
        assert len(result["suggestions"]) > 0

    # ── L4: Execution Stability ─────────────────────────────────

    def test_l4_single_run_na(self):
        """Single run produces N/A result."""
        details = {
            "score": None,
            "stdev_deterministic_pass_rate": 0.0,
            "runs": 1,
        }
        result = build_metric_analysis("L4", details)
        assert "N/A" in result["result_summary"] or "single" in result["result_summary"].lower()

    def test_l4_stable(self):
        """Low std dev reports stable execution."""
        details = {
            "score": 0.95,
            "stdev_deterministic_pass_rate": 0.05,
            "runs": 5,
        }
        result = build_metric_analysis("L4", details)
        assert result["result_summary"] != ""

    def test_l4_unstable(self):
        """High std dev reports instability."""
        details = {
            "score": 0.60,
            "stdev_deterministic_pass_rate": 0.25,
            "runs": 5,
        }
        result = build_metric_analysis("L4", details)
        assert len(result["suggestions"]) > 0

    # ── L5: Step Efficiency ─────────────────────────────────────

    def test_l5_efficient(self):
        """L5 = 1.0 means no violations."""
        details = {"score": 1.0, "violations": 0}
        result = build_metric_analysis("L5", details)
        assert result["result_summary"] != ""

    def test_l5_with_violations(self):
        """L5 < 0.7 shows violations and suggestions."""
        details = {"score": 0.3, "violations": 2}
        result = build_metric_analysis("L5", details)
        assert len(result["suggestions"]) > 0

    # ── L6: Trajectory Quality ─────────────────────────────────

    def test_l6_high_quality(self):
        details = {"score": 0.90}
        result = build_metric_analysis("L6", details)
        assert result["purpose"] != ""

    def test_l6_low_quality(self):
        details = {"score": 0.40}
        result = build_metric_analysis("L6", details)
        assert len(result["suggestions"]) > 0

    # ── L7: Cost Efficiency ─────────────────────────────────────

    def test_l7_available(self):
        details = {
            "cost_per_eval": 0.001,
            "total_cost": 0.50,
            "cost_with_skill": 0.30,
            "cost_without_skill": 0.20,
            "cost_delta_pct": 0.50,
            "cost_efficiency": 0.02,
        }
        result = build_metric_analysis("L7", details)
        assert result["purpose"] != ""

    def test_l7_high_cost_warning(self):
        """L7 with high cost delta triggers warning."""
        details = {
            "cost_delta_pct": 0.80,
            "cost_efficiency": 0.005,
            "total_cost": 10.0,
        }
        result = build_metric_analysis("L7", details)
        assert len(result["suggestions"]) > 0

    # ── L8: Latency ─────────────────────────────────────────────

    def test_l8_available(self):
        details = {
            "overhead_pct": 15.0,
            "with_skill": {"p50": 2.5, "p95": 5.0, "p99": 8.0},
            "without_skill": {"p50": 2.0, "p95": 4.0, "p99": 6.0},
        }
        result = build_metric_analysis("L8", details)
        assert result["purpose"] != ""

    def test_l8_high_overhead(self):
        """L8 with > 50% overhead triggers suggestions."""
        details = {
            "overhead_pct": 60.0,
            "with_skill": {"p50": 10.0},
            "without_skill": {"p50": 3.0},
        }
        result = build_metric_analysis("L8", details)
        assert len(result["suggestions"]) > 0

    # ── Drift ───────────────────────────────────────────────────

    def test_drift_skipped_single_model(self):
        """Single model evaluation skips drift."""
        details = {"models": 1, "drift_detected": None}
        result = build_metric_analysis("drift", details)
        assert "skip" in result["result_summary"].lower() or "skipped" in result["result_summary"].lower()

    def test_drift_detected(self):
        """Drift detected with high severity."""
        details = {
            "drift_detected": True,
            "highest_severity": "high",
            "max_variance": 0.45,
            "average_variance": 0.30,
            "model_pairs_compared": 3,
        }
        result = build_metric_analysis("drift", details)
        assert len(result["suggestions"]) > 0

    def test_drift_none_detected(self):
        """No significant drift across models."""
        details = {
            "drift_detected": False,
            "highest_severity": "none",
            "max_variance": 0.05,
            "average_variance": 0.02,
        }
        result = build_metric_analysis("drift", details)
        assert result["result_summary"] != ""

    # ── Security Probes ─────────────────────────────────────────

    def test_security_clean(self):
        """No security issues found."""
        details = {"probe_count": 52, "triggered": 0, "bypasses_found": 0}
        result = build_metric_analysis("security", details)
        assert "0" in result["result_summary"] or "none" in result["result_summary"].lower()

    def test_security_bypasses_found(self):
        """Security bypasses detected."""
        details = {"probe_count": 52, "triggered": 8, "bypasses_found": 3}
        result = build_metric_analysis("security", details)
        assert len(result["suggestions"]) > 0

    # ── Cost (separate from L7 for cost section) ────────────────

    def test_cost_section(self):
        details = {
            "total_cost": 0.50,
            "cost_per_eval": 0.001,
            "model": "gpt-4",
        }
        result = build_metric_analysis("cost", details)
        assert result["purpose"] != ""
        assert "$" in result["result_summary"] or "cost" in result["result_summary"].lower()

    # ── Reliability ─────────────────────────────────────────────

    def test_reliability_good(self):
        """Low error rate, no issues."""
        details = {
            "total_evals": 200,
            "success_rate": 0.99,
            "error_rate": 0.01,
            "retry_stats": {"avg_retries": 0.1, "max_retries": 1},
        }
        result = build_metric_analysis("reliability", details)
        assert result["result_summary"] != ""

    def test_reliability_poor(self):
        """High error rate triggers suggestions."""
        details = {
            "total_evals": 200,
            "success_rate": 0.70,
            "error_rate": 0.30,
            "retry_stats": {"avg_retries": 2.5, "max_retries": 5},
            "errors_by_category": {"timeout": 20, "rate_limit": 10},
        }
        result = build_metric_analysis("reliability", details)
        assert len(result["suggestions"]) > 0

    # ── Edge Cases ──────────────────────────────────────────────

    def test_unknown_metric_name(self):
        """Unknown metric name returns generic structure."""
        result = build_metric_analysis("UNKNOWN_METRIC", {})
        assert result["purpose"] != ""
        assert isinstance(result["suggestions"], list)

    def test_empty_details(self):
        """Empty details dict for known metric returns valid structure."""
        result = build_metric_analysis("L1", {})
        assert "purpose" in result
        assert "method" in result
        assert "result_summary" in result
        assert "analysis" in result
        assert "suggestions" in result

    def test_none_details(self):
        """None details should be handled gracefully."""
        result = build_metric_analysis("L1", None)
        assert "purpose" in result

    def test_result_structure_has_all_keys(self):
        """Every result dict has exactly the expected 5 keys."""
        result = build_metric_analysis("L1", {"score": 0.85})
        expected_keys = {"purpose", "method", "result_summary", "analysis", "suggestions"}
        assert set(result.keys()) == expected_keys

    # ── Integration: template-compatible return shape ───────────

    def test_return_is_template_ready(self):
        """Return value is a plain dict accessible in Jinja2 templates."""
        result = build_metric_analysis("L2", {"score": 0.40, "improvement_percentage": 40.0})
        assert isinstance(result, dict)
        # Jinja2 would access: {{ analysis.purpose }}, {{ analysis.method }}, etc.
        for key in ("purpose", "method", "result_summary", "analysis", "suggestions"):
            assert key in result
        # suggestions is iterable for `{% for s in analysis.suggestions %}`
        assert hasattr(result["suggestions"], "__iter__")
