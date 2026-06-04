"""Tests for engine/report_models.py — StructuredReport and related models."""

import pytest

from engine.report_models import (
    AssertionResult,
    EvalDetail,
    ImprovementSuggestion,
    MetricsSection,
    ObservabilitySection,
    ReportMetadata,
    StructuredReport,
    TokenAnalysisSection,
    TokenBreakdown,
    VerdictSummary,
)


class TestReportMetadata:
    """Tests for ReportMetadata model."""

    def test_default_values(self):
        meta = ReportMetadata()
        assert meta.skill_name == ""
        assert meta.schema_version == "1.0"

    def test_custom_values(self):
        meta = ReportMetadata(
            skill_name="test-skill",
            skill_path="/path/to/SKILL.md",
            models=["gpt-4", "claude-3"],
        )
        assert meta.skill_name == "test-skill"
        assert len(meta.models) == 2


class TestVerdictSummary:
    """Tests for VerdictSummary model."""

    def test_default_values(self):
        verdict = VerdictSummary()
        assert verdict.verdict == "FAIL"
        assert verdict.confidence == 0.0

    def test_pass_verdict(self):
        verdict = VerdictSummary(
            verdict="PASS",
            confidence=0.95,
            reasons=["L1: 95%", "L2: 25%"],
        )
        assert verdict.verdict == "PASS"
        assert len(verdict.reasons) == 2


class TestMetricsSection:
    """Tests for MetricsSection model."""

    def test_default_values(self):
        metrics = MetricsSection()
        assert metrics.l1_trigger_accuracy == 0.0
        assert metrics.l8_latency_p50 == 0.0

    def test_custom_values(self):
        metrics = MetricsSection(
            l1_trigger_accuracy=95.0,
            l2_output_delta=25.0,
            l3_step_adherence=90.0,
            l4_stability_std=0.05,
        )
        assert metrics.l1_trigger_accuracy == 95.0


class TestEvalDetail:
    """Tests for EvalDetail model."""

    def test_default_values(self):
        detail = EvalDetail()
        assert detail.eval_id == 0
        assert detail.passed is False
        assert detail.assertions == []

    def test_with_assertions(self):
        detail = EvalDetail(
            eval_id=1,
            eval_name="test-eval",
            assertions=[
                AssertionResult(type="contains", expected="hello", actual="hello world", passed=True),
                AssertionResult(type="regex", expected=r"\d+", actual="abc", passed=False),
            ],
        )
        assert len(detail.assertions) == 2
        assert detail.assertions[0].passed is True
        assert detail.assertions[1].passed is False


class TestTokenAnalysisSection:
    """Tests for TokenAnalysisSection model."""

    def test_default_values(self):
        section = TokenAnalysisSection()
        assert section.total_tokens == 0
        assert section.by_phase == {}

    def test_with_data(self):
        section = TokenAnalysisSection(
            total_tokens=1000,
            total_cost=0.05,
            by_phase={
                "with_skill": TokenBreakdown(total_tokens=600, cost=0.03),
                "without_skill": TokenBreakdown(total_tokens=400, cost=0.02),
            },
        )
        assert section.total_tokens == 1000
        assert "with_skill" in section.by_phase


class TestObservabilitySection:
    """Tests for ObservabilitySection model."""

    def test_default_values(self):
        section = ObservabilitySection()
        assert section.trace_count == 0
        assert section.trace_format == "jsonl"

    def test_with_data(self):
        section = ObservabilitySection(
            trace_count=10,
            total_events=50,
            total_duration_ms=5000.0,
            trace_export_path="/path/to/traces.jsonl",
        )
        assert section.trace_count == 10


class TestImprovementSuggestion:
    """Tests for ImprovementSuggestion model."""

    def test_default_values(self):
        suggestion = ImprovementSuggestion()
        assert suggestion.category == ""
        assert suggestion.priority == "medium"

    def test_str_representation(self):
        suggestion = ImprovementSuggestion(
            category="prompt",
            priority="high",
            title="Improve trigger",
            description="The trigger detection needs improvement",
        )
        s = str(suggestion)
        assert "HIGH" in s
        assert "prompt" in s
        assert "Improve trigger" in s

    def test_backward_compat(self):
        """Test that str(suggestion) works like the old list[str] format."""
        suggestions = [
            ImprovementSuggestion(category="general", priority="medium", title="Test", description="Test description"),
        ]
        # Old code expects list[str], str() should work
        str_list = [str(s) for s in suggestions]
        assert len(str_list) == 1
        assert "Test" in str_list[0]


class TestStructuredReport:
    """Tests for StructuredReport model."""

    def test_default_values(self):
        report = StructuredReport()
        assert report.verdict.verdict == "FAIL"
        assert report.eval_details == []
        assert report.improvements == []

    def test_full_report(self):
        report = StructuredReport(
            metadata=ReportMetadata(skill_name="test-skill"),
            verdict=VerdictSummary(verdict="PASS", confidence=0.9),
            metrics=MetricsSection(l1_trigger_accuracy=95.0),
            token_analysis=TokenAnalysisSection(total_tokens=1000),
            observability=ObservabilitySection(trace_count=5),
        )
        assert report.metadata.skill_name == "test-skill"
        assert report.verdict.verdict == "PASS"
        assert report.metrics.l1_trigger_accuracy == 95.0

    def test_verdict_str_property(self):
        report = StructuredReport(verdict=VerdictSummary(verdict="PASS"))
        assert report.verdict_str == "PASS"

    def test_overall_score_property(self):
        report = StructuredReport(
            metrics=MetricsSection(
                l1_trigger_accuracy=0.95,
                l2_output_delta=25.0,
                l3_step_adherence=0.90,
                l4_stability_std=0.05,
                l5_step_efficiency=0.85,
                l6_trajectory_quality=0.80,
            )
        )
        score = report.overall_score
        assert 0 <= score <= 100

    def test_model_dump(self):
        report = StructuredReport(
            metadata=ReportMetadata(skill_name="test"),
            verdict=VerdictSummary(verdict="PASS"),
        )
        data = report.model_dump()
        assert data["metadata"]["skill_name"] == "test"
        assert data["verdict"]["verdict"] == "PASS"

    def test_model_dump_json(self):
        report = StructuredReport(
            metadata=ReportMetadata(skill_name="test"),
        )
        json_str = report.model_dump_json()
        assert '"skill_name":"test"' in json_str

    def test_model_validate(self):
        data = {
            "metadata": {"skill_name": "test"},
            "verdict": {"verdict": "PASS"},
        }
        report = StructuredReport.model_validate(data)
        assert report.metadata.skill_name == "test"
        assert report.verdict.verdict == "PASS"
