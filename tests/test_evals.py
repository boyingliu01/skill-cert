"""Tests for skill_cert.cli.evals — coverage for uncovered lines."""

import json
from unittest.mock import MagicMock, patch

from engine.grader import EvalAssertion, EvalCase
from engine.observability import TelemetrySummary
from engine.report_models import StructuredReport
from engine.token_ledger import TokenLedger
from skill_cert.cli.evals import (
    _aggregate_token_data,
    _build_eval_case_from_dict,
    _build_structured_report_context,
    _export_traces,
    _generate_and_write_reports,
    _grade_single_result,
    _run_single_phase,
    _write_json_report,
    _write_markdown_report,
)


def _mock_reporter_class():
    """Build a mock Reporter class whose generate_report returns (# md, {verdict: PASS})."""
    mr = MagicMock()
    mr.generate_report.return_value = ("# md", json.dumps({"verdict": "PASS"}))
    mr.build_structured_report.return_value = StructuredReport()
    mr.generate_json_report.return_value = json.dumps({"verdict": "PASS"})
    return mr


class TestBuildEvalCaseFromDict:
    """Cover lines 23 and 38."""

    def test_line23_passes_through_existing_evalcase(self):
        case = EvalCase(
            id=1,
            name="test",
            category="trigger",
            prompt="hello",
            assertions=[EvalAssertion(name="d", type="contains", value=".", weight=1)],
        )
        result = _build_eval_case_from_dict(case)
        assert result is case

    def test_line38_json_dumps_dict_prompt(self):
        d = {
            "id": 1,
            "name": "test",
            "category": "normal",
            "input": {"key": "val"},
            "assertions": [{"name": "d", "type": "contains", "value": ".", "weight": 1}],
        }
        result = _build_eval_case_from_dict(d)
        assert isinstance(result.prompt, str)
        parsed = json.loads(result.prompt)
        assert parsed == {"key": "val"}

    def test_line38_json_dumps_list_prompt(self):
        d = {
            "id": 2,
            "name": "list",
            "category": "normal",
            "input": [1, 2, 3],
            "assertions": [{"name": "d", "type": "contains", "value": ".", "weight": 1}],
        }
        result = _build_eval_case_from_dict(d)
        assert isinstance(result.prompt, str)
        parsed = json.loads(result.prompt)
        assert parsed == [1, 2, 3]


class TestGradeSingleResult:
    """Cover lines 91 and 94."""

    def test_line91_error_returns_none(self):
        grader = MagicMock()
        result = _grade_single_result({}, grader, {"error": "some error"}, "with_skill")
        assert result is None
        grader.grade_output.assert_not_called()

    def test_line94_no_case_returns_none(self):
        grader = MagicMock()
        case_map = {}
        result = _grade_single_result(
            case_map, grader, {"eval_id": 999, "output": "hey"}, "with_skill"
        )
        assert result is None
        grader.grade_output.assert_not_called()


class TestAggregateTokenData:
    """Cover lines 232-237: by_phase token summary."""

    def test_lines232_237_by_phase_token_summary(self):
        runner = MagicMock()
        token_ledger = MagicMock(spec=TokenLedger)
        token_ledger.get_summary.return_value = {
            "total_tokens": 5000,
            "total_cost": 0.05,
            "by_phase": {
                "with_skill": {"total_tokens": 3000},
                "without_skill": {"total_tokens": 2000},
            },
        }
        metrics = {}
        _aggregate_token_data(runner, token_ledger, metrics)
        assert metrics["token_analysis"] == {
            "total_tokens": 5000,
            "total_cost": 0.05,
            "by_phase": {
                "with_skill": {"total_tokens": 3000},
                "without_skill": {"total_tokens": 2000},
            },
        }


class TestBuildStructuredReportContext:
    """Cover lines 305-306 and 316."""

    def test_lines305_306_with_telemetry_get_summary(self, tmp_path):
        args = MagicMock()
        args.trace_export = "jsonl"
        telemetry = MagicMock()
        telemetry.get_summary.return_value = {
            "trace_count": 10,
            "total_events": 50,
            "total_duration_ms": 5000,
            "total_tool_calls": 30,
            "session_duration_s": 30,
            "export_path": str(tmp_path / "traces"),
            "export_format": "jsonl",
        }
        token_analysis, obs = _build_structured_report_context(
            {"token_analysis": {"total_tokens": 100}}, args, [], telemetry
        )
        assert obs["trace_count"] == 10
        assert obs["total_events"] == 50
        assert obs["total_duration_ms"] == 5000

    def test_line316_elif_all_traces(self):
        args = MagicMock()
        args.trace_export = "jsonl"

        class FakeTrace:
            events = [1, 2]
            duration_ms = 100
            tool_call_count = 3

        traces = [FakeTrace(), FakeTrace()]
        token_analysis, obs = _build_structured_report_context(
            {"token_analysis": {"total_tokens": 100}}, args, traces, telemetry=None
        )
        assert obs["trace_count"] == 2
        assert obs["total_events"] == 4
        assert obs["total_duration_ms"] == 200
        assert obs["total_tool_calls"] == 6

    def test_line316_no_traces_no_telemetry(self):
        args = MagicMock()
        token_analysis, obs = _build_structured_report_context(
            {"token_analysis": {"total_tokens": 100}}, args, [], telemetry=None
        )
        assert obs is None


class TestWriteMarkdownReport:
    """Cover lines 334-337."""

    def test_lines334_337_happy_path(self, tmp_path):
        path = _write_markdown_report(tmp_path, "test-skill", "# Report\n", "markdown")
        assert path == tmp_path / "test-skill-report.md"
        assert path.exists()
        assert path.read_text(encoding="utf-8") == "# Report\n"

    def test_skip_on_json_format(self, tmp_path):
        path = _write_markdown_report(tmp_path, "test-skill", "# Report\n", "json")
        assert path is None
        assert not (tmp_path / "test-skill-report.md").exists()


class TestWriteJsonReport:
    """Cover lines 360-369: schema validation PASS and FAIL."""

    @patch("skill_cert.cli.Reporter")
    def test_lines360_369_schema_validation_pass(self, mock_reporter_class, tmp_path):
        args = MagicMock()
        args.json_schema_validate = True
        args.format = "json"

        mock_reporter = mock_reporter_class.return_value
        mock_reporter.generate_json_report.return_value = '{"metadata": {"skill_name": "test"}}'

        structured_report = StructuredReport()
        json_path, json_str = _write_json_report(
            args, tmp_path, "test-skill", structured_report, "json"
        )
        assert json_path is not None
        assert json_str is not None

    @patch("skill_cert.cli.Reporter")
    def test_lines360_369_schema_validation_fail(self, mock_reporter_class, tmp_path):
        args = MagicMock()
        args.json_schema_validate = True
        args.format = "json"

        mock_reporter = mock_reporter_class.return_value
        mock_reporter.generate_json_report.return_value = '{"bad": "data"}'

        structured_report = StructuredReport()
        json_path, json_str = _write_json_report(
            args, tmp_path, "test-skill", structured_report, "json"
        )
        assert json_path is not None
        assert json_str is not None


class TestExportTraces:
    """Cover lines 388-395."""

    def test_lines388_395_exports_traces_with_default_dir(self, tmp_path):
        args = MagicMock()
        args.trace_export = "jsonl"
        args.trace_dir = str(tmp_path / "traces")

        class FakeTrace:
            def model_dump_json(self):
                return '{"trace": "data"}'

        path = _export_traces(args, tmp_path, "test-skill", [FakeTrace(), FakeTrace()])
        assert path == tmp_path / "traces" / "test-skill-traces.jsonl"
        assert path.exists()
        content = path.read_text(encoding="utf-8").strip().split("\n")
        assert len(content) == 2
        assert json.loads(content[0]) == {"trace": "data"}

    def test_lines388_395_exports_traces_with_none_dir_falls_back_to_output(self, tmp_path):
        args = MagicMock()
        args.trace_export = "jsonl"
        args.trace_dir = None

        class FakeTrace:
            def model_dump_json(self):
                return '{"trace": "x"}'

        path = _export_traces(args, tmp_path, "test-skill", [FakeTrace()])
        assert path == tmp_path / "test-skill-traces.jsonl"
        assert path.exists()

    def test_trace_export_none_returns_none(self, tmp_path):
        args = MagicMock()
        args.trace_export = "none"
        path = _export_traces(args, tmp_path, "test-skill", [MagicMock()])
        assert path is None


class TestGenerateAndWriteReports:
    """Cover line 427: session_telemetry_summaries from telemetry.get_all_summaries()."""

    def test_line427_telemetry_summaries(self, tmp_path):
        args = MagicMock()
        args.format = "both"
        args.trace_export = "none"
        args.json_schema_validate = False

        mock_reporter = _mock_reporter_class()
        config = MagicMock()
        config.model_dump.return_value = {"max_concurrency": 1}

        telemetry = MagicMock()
        telemetry.get_summary.return_value = {"trace_count": 1}
        telemetry.get_all_summaries.return_value = [
            TelemetrySummary(total=100),
            TelemetrySummary(total=200),
        ]

        with patch("skill_cert.cli.Reporter", return_value=mock_reporter):
            md_report, json_report_val = _generate_and_write_reports(
                args,
                tmp_path,
                "test-skill",
                {"evals": {"test": 1}},
                "/fake/path",
                {"m1": MagicMock()},
                {"overall": 0.9},
                {},
                config,
                telemetry,
            )
        call_kwargs = mock_reporter.build_structured_report.call_args[1]
        summaries = call_kwargs["session_telemetry"]
        assert summaries is not None
        assert len(summaries) == 2
        assert summaries[0]["total"] == 100
        assert summaries[1]["total"] == 200

    def test_line427_telemetry_no_summaries(self, tmp_path):
        args = MagicMock()
        args.format = "both"
        args.trace_export = "none"
        args.json_schema_validate = False

        mock_reporter = _mock_reporter_class()
        config = MagicMock()
        config.model_dump.return_value = {"max_concurrency": 1}

        telemetry = MagicMock()
        telemetry.get_summary.return_value = {"trace_count": 1}
        telemetry.get_all_summaries.return_value = []

        with patch("skill_cert.cli.Reporter", return_value=mock_reporter):
            md_report, json_report_val = _generate_and_write_reports(
                args,
                tmp_path,
                "test-skill",
                {"evals": {"test": 1}},
                "/fake/path",
                {"m1": MagicMock()},
                {"overall": 0.9},
                {},
                config,
                telemetry,
            )
        call_kwargs = mock_reporter.build_structured_report.call_args[1]
        assert call_kwargs["session_telemetry"] is None


class TestRunSinglePhaseDegraded:
    """Cover lines 507-509: degraded flag."""

    def test_lines507_509_degraded_mode(self, tmp_path):
        mock_run_all = MagicMock(return_value=[])
        mock_calc_metrics = MagicMock(return_value={"overall": 0.9})
        mock_tracker_report = MagicMock()
        mock_tracker_report.generate_report.return_value = {
            "success_rate": 1.0,
            "error_rate": 0.0,
            "errors_by_category": {},
            "retry_stats": {"total_retries": 0},
        }
        mock_gen_reports = MagicMock(return_value=("# mock", {"verdict": "PASS"}))

        args = MagicMock()
        args.runs = 1
        args.format = "both"
        args.ci_history = False  # Disable CI history for this test
        args.ci_history_path = ".skill-cert-ci-history.json"

        config = MagicMock()
        config.max_concurrency = 1
        config.rate_limit_rpm = 60
        config.request_timeout = 30

        spec_path = tmp_path / "SKILL.md"
        spec_path.write_text("")
        spec = {
            "evals": {
                "eval_cases": [],
                "degraded": True,
                "_coverage": 0.75,
            }
        }

        with (
            patch("skill_cert.cli.evals._run_all_evals", mock_run_all),
            patch("skill_cert.cli.ReliabilityTracker", return_value=mock_tracker_report),
            patch("skill_cert.cli.evals._calculate_metrics_with_stability", mock_calc_metrics),
            patch("skill_cert.cli.evals._print_reliability_report"),
            patch("skill_cert.cli.evals._aggregate_token_data"),
            patch("skill_cert.cli.evals._print_metrics_summary"),
            patch("skill_cert.cli.evals._detect_and_print_drift"),
            patch("skill_cert.cli.evals._generate_and_write_reports", mock_gen_reports),
        ):
            exit_code = _run_single_phase(
                args,
                config,
                str(spec_path),
                tmp_path,
                "test-degraded",
                spec,
                {"m1": MagicMock()},
            )
            assert exit_code == 0


class TestWriteJsonReportSchemaFail:
    """Cover lines 368-369: schema validation FAIL in _write_json_report."""

    def test_schema_validation_fail(self, tmp_path):
        from unittest.mock import patch

        from engine.report_models import (
            MetricsSection,
            StructuredReport,
            VerdictSummary,
        )
        from skill_cert.cli.evals import _write_json_report

        args = MagicMock()
        args.json_schema_validate = True

        structured_report = StructuredReport(
            verdict=VerdictSummary(verdict="PASS", confidence=0.8),
            metrics=MetricsSection(),
        )

        with patch.object(
            StructuredReport,
            "model_validate",
            side_effect=ValueError("invalid schema"),
        ):
            path, json_str = _write_json_report(args, tmp_path, "test", structured_report, "json")

        assert path is not None
        assert json_str is not None


class TestEvalDetailsIntegration:
    """Integration tests: eval_details flows from metrics['_results']
    through _generate_and_write_reports → build_structured_report → JSON."""

    def _make_graded_result_dicts(self) -> list[dict]:
        """Build result dicts matching the output of _flatten_grade_result."""
        return [
            {
                "eval_id": 1,
                "eval_name": "trigger positive test",
                "eval_category": "trigger",
                "model": "gpt-4",
                "run": "with-skill",
                "mode": "with_skill",
                "input": "review this PR",
                "output": "Looking at the code changes...",
                "execution_time": 1.23,
                "error": None,
                "tokens_used": 150,
                "cost": 0.003,
                "grade": {
                    "assertion_results": [
                        {
                            "assertion": {
                                "name": "has_review",
                                "type": "contains",
                                "value": "changes",
                                "weight": 1,
                            },
                            "passed": True,
                            "confidence": 1.0,
                            "reason": "'changes' found in output",
                        }
                    ],
                    "pass_rate": 1.0,
                    "final_passed": True,
                },
                "final_passed": True,
                "pass_rate": 1.0,
            },
            {
                "eval_id": 1,
                "eval_name": "trigger positive test",
                "eval_category": "trigger",
                "model": "gpt-4",
                "run": "without-skill",
                "mode": "without_skill",
                "input": "review this PR",
                "output": "I can help with that",
                "execution_time": 0.8,
                "error": None,
                "tokens_used": 100,
                "cost": 0.002,
                "grade": {
                    "assertion_results": [
                        {
                            "assertion": {
                                "name": "has_review",
                                "type": "contains",
                                "value": "changes",
                                "weight": 1,
                            },
                            "passed": False,
                            "confidence": 0.8,
                            "reason": "'changes' NOT found in output",
                        }
                    ],
                    "pass_rate": 0.0,
                    "final_passed": False,
                },
                "final_passed": False,
                "pass_rate": 0.0,
            },
        ]

    def test_generate_and_write_reports_threads_eval_results(self, tmp_path):
        """_generate_and_write_reports calls build_structured_report
        with eval_results populated from metrics['_results']."""
        args = MagicMock()
        args.format = "both"
        args.trace_export = "none"
        args.json_schema_validate = False

        config = MagicMock()
        config.model_dump.return_value = {"max_concurrency": 1}

        graded_results = self._make_graded_result_dicts()
        metrics = {
            "overall_score": 0.85,
            "l1_trigger_accuracy": 0.90,
            "l2_with_without_skill_delta": 0.75,
            "l3_step_adherence": 0.80,
            "l4_execution_stability": 0.95,
            "_results": graded_results,
            "metrics_breakdown": {
                "l1_details": {},
                "l2_details": {},
                "l3_details": {},
                "l4_details": {},
            },
        }

        mock_reporter = _mock_reporter_class()
        with patch("skill_cert.cli.Reporter", return_value=mock_reporter):
            _generate_and_write_reports(
                args,
                tmp_path,
                "test-skill",
                {"evals": {}},
                "/fake/path",
                {"m1": MagicMock()},
                metrics,
                {},
                config,
                telemetry=None,
            )

        call_kwargs = mock_reporter.build_structured_report.call_args[1]
        eval_results = call_kwargs.get("eval_results")
        assert eval_results is not None, "eval_results should be passed to build_structured_report"
        assert len(eval_results) == 2, f"Expected 2 eval results, got {len(eval_results)}"
        assert eval_results[0]["eval_id"] == 1
        assert eval_results[0]["mode"] == "with_skill"
        assert eval_results[1]["mode"] == "without_skill"

    def test_eval_results_empty_when_no_results_key(self, tmp_path):
        """When metrics has no '_results', build_structured_report
        receives eval_results=None and eval_details stays empty."""
        args = MagicMock()
        args.format = "both"
        args.trace_export = "none"
        args.json_schema_validate = False

        config = MagicMock()
        config.model_dump.return_value = {"max_concurrency": 1}

        metrics = {"overall_score": 0.85}

        mock_reporter = _mock_reporter_class()
        with patch("skill_cert.cli.Reporter", return_value=mock_reporter):
            _generate_and_write_reports(
                args,
                tmp_path,
                "test-skill",
                {"evals": {}},
                "/fake/path",
                {"m1": MagicMock()},
                metrics,
                {},
                config,
                telemetry=None,
            )

        call_kwargs = mock_reporter.build_structured_report.call_args[1]
        eval_results = call_kwargs.get("eval_results")
        assert eval_results is None, (
            "eval_results should be None when _results is missing from metrics"
        )

    def test_structured_report_json_contains_eval_details(self):
        """build_structured_report with eval_results produces
        StructuredReport with non-empty eval_details."""
        from engine.reporter import Reporter

        graded_results = self._make_graded_result_dicts()

        report = Reporter().build_structured_report(
            metrics={
                "overall_score": 0.85,
            },
            drift=None,
            config={"models": ["gpt-4"], "skill_name": "test"},
            eval_results=graded_results,
        )
        assert len(report.eval_details) == 2
        detail = report.eval_details[0]
        assert detail.eval_id == 1
        assert detail.model == "gpt-4"
        assert detail.phase == "with_skill"
        assert detail.passed is True
        assert detail.execution_time == 1.23
        assert detail.tokens_used == 150
        assert detail.cost == 0.003

        detail2 = report.eval_details[1]
        assert detail2.phase == "without_skill"
        assert detail2.passed is False
        assert detail2.tokens_used == 100
