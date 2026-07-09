"""Tests for engine/report_models.py — StructuredReport and related models."""

from typing import Any, cast

from engine.report_models import (
    AssertionResult,
    EvalDetail,
    ImprovementSuggestion,
    MetricAnalysis,
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

    def test_models_rejects_dict_config(self):
        import pytest

        invalid_models = cast(list[str], cast(Any, [{"model_name": "gpt-4", "api_key": "secret"}]))
        with pytest.raises(Exception):
            ReportMetadata(skill_name="test", models=invalid_models)

        meta = ReportMetadata(
            skill_name="test",
            models=["gpt-4", "claude-3"],
        )
        assert all(isinstance(m, str) for m in meta.models)


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

    def test_pass_with_caveats_verdict(self):
        verdict = VerdictSummary(verdict="PASS_WITH_CAVEATS", confidence=0.65)
        assert verdict.verdict == "PASS_WITH_CAVEATS"


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
                AssertionResult(
                    type="contains", expected="hello", actual="hello world", passed=True
                ),
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
            ImprovementSuggestion(
                category="general", priority="medium", title="Test", description="Test description"
            ),
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


class TestMetricAnalysis:
    """Tests for MetricAnalysis model."""

    def test_default_values(self):
        ma = MetricAnalysis()
        assert ma.metric_name == ""
        assert ma.purpose == ""
        assert ma.method == ""
        assert ma.result_summary == ""
        assert ma.analysis == ""
        assert ma.suggestions == []

    def test_full_model(self):
        ma = MetricAnalysis(
            metric_name="L1",
            purpose="验证模型是否在正确场景触发该Skill，而非误触发或遗漏触发",
            method="生成正例和反例触发用例，通过混淆矩阵（TP/TN/FP/FN）计算综合准确率",
            result_summary="触发准确率 95.0%，PASS",
            analysis="模型对正面触发场景识别良好，但存在少量误判",
            suggestions=["增加边界触发用例", "优化触发条件描述"],
        )
        assert ma.metric_name == "L1"
        assert "混淆矩阵" in ma.method
        assert ma.result_summary == "触发准确率 95.0%，PASS"
        assert len(ma.suggestions) == 2
        assert "边界触发" in ma.suggestions[0]

    def test_model_dump(self):
        ma = MetricAnalysis(
            metric_name="L2",
            purpose="验证Skill是否确实提升了模型表现",
            method="计算归一化增益Δ=(with-without)/without，增益≥20%为PASS",
            result_summary="增益 25%，PASS",
            analysis="Skill对代码生成任务有明显提升",
            suggestions=["优化上下文使用"],
        )
        data = ma.model_dump()
        assert data["metric_name"] == "L2"
        assert data["purpose"] == "验证Skill是否确实提升了模型表现"
        assert "Δ" in data["method"]
        assert data["suggestions"] == ["优化上下文使用"]

    def test_model_dump_json(self):
        ma = MetricAnalysis(
            metric_name="drift",
            purpose="验证Skill在不同模型上的表现一致性",
            method="在至少2个不同provider的模型上执行相同评测集，计算通过率方差",
            result_summary="drift severity: none",
            analysis="跨模型表现一致",
            suggestions=[],
        )
        json_str = ma.model_dump_json()
        assert '"metric_name"' in json_str
        assert '"drift"' in json_str
        assert "跨模型" in json_str

    def test_suggestions_default_to_empty_list(self):
        ma = MetricAnalysis(metric_name="cost")
        assert ma.suggestions == []

    def test_fields_are_all_strings_except_suggestions(self):
        ma = MetricAnalysis(
            metric_name="L8",
            purpose="验证Skill是否引入不可接受的延迟",
            method="统计P50/P95/P99延迟，计算开销百分比",
            result_summary="P50: 2.3s, P95: 5.1s",
            analysis="延迟在可接受范围内",
        )
        assert isinstance(ma.metric_name, str)
        assert isinstance(ma.purpose, str)
        assert isinstance(ma.method, str)
        assert isinstance(ma.result_summary, str)
        assert isinstance(ma.analysis, str)
        assert isinstance(ma.suggestions, list)
