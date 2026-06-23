"""Tests for uncovered coverage gaps in skill_cert/cli/single.py."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from skill_cert.cli.single import (
    _generate_fail_fast_report,
    _setup_single_mode,
    run_single_mode,
)


class TestSetupSingleMode:
    """Tests for _setup_single_mode — covers FAILED and degraded paths."""

    def _make_mock_spec(self):
        return {
            "name": "test-skill",
            "parse_method": "regex",
            "parse_confidence": 0.95,
            "workflow_steps": [],
            "anti_patterns": [],
            "output_format": {},
            "triggers": [],
        }

    def test_setup_fail_fast_coverage(self, tmp_path):
        """Covers lines 97-102: coverage FAILED returns early."""
        output_dir = tmp_path / "results"
        args = MagicMock()
        args.skill = "tests/samples/test.md"
        args.output = str(output_dir)

        from unittest.mock import PropertyMock

        config = MagicMock()
        mock_mc = MagicMock()
        type(mock_mc).model_name = PropertyMock(return_value="test-model")
        config.models = [mock_mc]

        with patch("skill_cert.cli.parse_skill_md") as mock_parse:
            mock_parse.return_value = self._make_mock_spec()
            with patch("skill_cert.cli.MaintainabilityScorer") as mock_scorer:
                scorer = MagicMock()
                scorer.score_file.return_value.total_score = 80
                scorer.score_file.return_value.grade = "B"
                scorer.score_file.return_value.readability_score = 85.0
                scorer.score_file.return_value.completeness_score = 75.0
                scorer.score_file.return_value.freshness_score = 80.0
                mock_scorer.return_value = scorer
                with patch("skill_cert.cli._create_adapter") as mock_create:
                    mock_create.return_value = MagicMock()
                    with patch("skill_cert.cli.EvalGenerator") as mock_gen_cls:
                        from engine.testgen import EvalGenerator as _EvalGen

                        mock_gen = MagicMock()
                        mock_gen_cls.return_value = mock_gen
                        mock_gen.generate_evals_with_convergence.return_value = {}
                        mock_gen._calculate_coverage.return_value = 0.3
                        mock_gen.coverage_threshold = 0.7
                        mock_gen.block_threshold = 0.5
                        mock_gen.CoverageResult = _EvalGen.CoverageResult
                        mock_gen.check_coverage_or_abort.return_value = (
                            _EvalGen.CoverageResult.FAILED
                        )

                        result = _setup_single_mode(args, config)
                        spec_path, out_dir, skill_name, spec, evals, adapters = result
                        assert skill_name == "test"
                        assert evals["_coverage"] == 0.3

    def test_setup_coverage_warning(self, tmp_path):
        """Covers line 92-93: coverage below threshold prints warning."""
        from unittest.mock import PropertyMock

        output_dir = tmp_path / "results"
        args = MagicMock()
        args.skill = "tests/samples/test.md"
        args.output = str(output_dir)

        config = MagicMock()
        mock_mc = MagicMock()
        type(mock_mc).model_name = PropertyMock(return_value="test-model")
        config.models = [mock_mc]

        with patch("skill_cert.cli.parse_skill_md") as mock_parse:
            mock_parse.return_value = self._make_mock_spec()
            with patch("skill_cert.cli.MaintainabilityScorer") as mock_scorer:
                scorer = MagicMock()
                scorer.score_file.return_value.total_score = 80
                scorer.score_file.return_value.grade = "B"
                scorer.score_file.return_value.readability_score = 85.0
                scorer.score_file.return_value.completeness_score = 75.0
                scorer.score_file.return_value.freshness_score = 80.0
                mock_scorer.return_value = scorer
                with patch("skill_cert.cli._create_adapter") as mock_create:
                    mock_create.return_value = MagicMock()
                    with patch("skill_cert.cli.EvalGenerator") as mock_gen_cls:
                        mock_gen = MagicMock()
                        mock_gen_cls.return_value = mock_gen
                        mock_gen.generate_evals_with_convergence.return_value = {}
                        mock_gen._calculate_coverage.return_value = 0.65
                        mock_gen.coverage_threshold = 0.7
                        mock_gen.block_threshold = 0.5
                        mock_gen.check_coverage_or_abort.return_value = "PASSED"

                        result = _setup_single_mode(args, config)
                        assert result[2] == "test"

    def test_setup_no_models(self, tmp_path):
        """Covers line 67-72: no config.models returns None tuple."""
        output_dir = tmp_path / "results"
        args = MagicMock()
        args.skill = "tests/samples/test.md"
        args.output = str(output_dir)

        config = MagicMock()
        config.models = []

        with patch("skill_cert.cli.parse_skill_md") as mock_parse:
            mock_parse.return_value = self._make_mock_spec()
            with patch("skill_cert.cli.MaintainabilityScorer") as mock_scorer:
                scorer = MagicMock()
                scorer.score_file.return_value.total_score = 80
                scorer.score_file.return_value.grade = "B"
                scorer.score_file.return_value.readability_score = 85.0
                scorer.score_file.return_value.completeness_score = 75.0
                scorer.score_file.return_value.freshness_score = 80.0
                mock_scorer.return_value = scorer
                result = _setup_single_mode(args, config)
                assert all(x is None for x in result)


class TestGenerateFailFastReport:
    """Tests for _generate_fail_fast_report — covers lines 108-183."""

    def test_fail_fast_report_both_formats(self, tmp_path):
        """Covers lines 108-183: both markdown and json formats."""
        output_dir = tmp_path / "results"
        output_dir.mkdir(parents=True, exist_ok=True)

        args = MagicMock()
        args.format = "both"

        with patch("engine.reporter.Reporter") as mock_reporter_cls:
            mock_reporter = MagicMock()
            mock_reporter_cls.return_value = mock_reporter
            mock_reporter.generate_report.return_value = ("# md report", {"verdict": "FAIL"})

            result = _generate_fail_fast_report(
                args,
                spec_path=Path("tests/samples/test.md"),
                output_dir=output_dir,
                skill_name="test-skill",
                spec={"name": "test-skill"},
                coverage=0.3,
            )

        assert result["verdict"] == "FAIL"
        assert result["fail_fast"] is True
        assert result["coverage_at_abort"] == 0.3
        assert "below block threshold" in result["fail_reason"]

        assert (output_dir / "test-skill-report.md").exists()
        assert (output_dir / "test-skill-result.json").exists()

        import json

        json_data = json.loads((output_dir / "test-skill-result.json").read_text())
        assert json_data["fail_fast"] is True

    def test_fail_fast_report_markdown_only(self, tmp_path):
        """Covers lines 163-174: markdown format only."""
        output_dir = tmp_path / "results"
        output_dir.mkdir(parents=True, exist_ok=True)

        args = MagicMock()
        args.format = "markdown"

        with patch("engine.reporter.Reporter") as mock_reporter_cls:
            mock_reporter = MagicMock()
            mock_reporter_cls.return_value = mock_reporter
            mock_reporter.generate_report.return_value = ("# md report", {"verdict": "FAIL"})

            result = _generate_fail_fast_report(
                args,
                spec_path=Path("tests/samples/test.md"),
                output_dir=output_dir,
                skill_name="test-skill",
                spec={"name": "test-skill"},
                coverage=0.3,
            )

        assert result["verdict"] == "FAIL"
        assert (output_dir / "test-skill-report.md").exists()
        assert not (output_dir / "test-skill-result.json").exists()

    def test_fail_fast_report_json_only(self, tmp_path):
        """Covers lines 176-181: json format only."""
        output_dir = tmp_path / "results"
        output_dir.mkdir(parents=True, exist_ok=True)

        args = MagicMock()
        args.format = "json"

        with patch("engine.reporter.Reporter") as mock_reporter_cls:
            mock_reporter = MagicMock()
            mock_reporter_cls.return_value = mock_reporter
            mock_reporter.generate_report.return_value = ("# md report", {"verdict": "FAIL"})

            result = _generate_fail_fast_report(
                args,
                spec_path=Path("tests/samples/test.md"),
                output_dir=output_dir,
                skill_name="test-skill",
                spec={"name": "test-skill"},
                coverage=0.3,
            )

        assert result["verdict"] == "FAIL"
        assert not (output_dir / "test-skill-report.md").exists()
        assert (output_dir / "test-skill-result.json").exists()


class TestRunSingleMode:
    """Tests for run_single_mode — covers fail-fast and degraded paths."""

    def test_run_single_mode_fail_fast(self, tmp_path):
        """Covers lines 204-215: evals.get('failed') triggers fail-fast."""
        output_dir = tmp_path / "results"
        output_dir.mkdir(parents=True, exist_ok=True)

        args = MagicMock()
        args.skill = "tests/samples/test.md"
        args.output = str(output_dir)
        args.format = "both"

        config = MagicMock()
        config.max_total_time = None

        with patch("skill_cert.cli.single._setup_single_mode") as mock_setup:
            mock_setup.return_value = (
                Path("tests/samples/test.md"),
                output_dir,
                "test-skill",
                {"name": "test-skill"},
                {"failed": True, "_coverage": 0.3},
                {"model1": MagicMock()},
            )
            with patch("skill_cert.cli.single._generate_fail_fast_report") as mock_report:
                mock_report.return_value = {"verdict": "FAIL"}

                from skill_cert.cli import EXIT_ERROR

                exit_code = run_single_mode(args, config)
                assert exit_code == EXIT_ERROR

    def test_run_single_mode_degraded(self, tmp_path):
        """Covers lines 218-219: evals.get('degraded') prints warning."""
        output_dir = tmp_path / "results"
        output_dir.mkdir(parents=True, exist_ok=True)

        args = MagicMock()
        args.skill = "tests/samples/test.md"
        args.output = str(output_dir)
        args.runs = 1
        args.trace_export = "none"
        args.format = "json"
        args.json_schema_validate = False

        config = MagicMock()
        config.max_total_time = None

        with patch("skill_cert.cli.single._setup_single_mode") as mock_setup:
            mock_setup.return_value = (
                Path("tests/samples/test.md"),
                output_dir,
                "test-skill",
                {"name": "test-skill", "evals": {}},
                {"degraded": True, "_coverage": 0.65},
                {"model1": MagicMock()},
            )
            with patch("skill_cert.cli._run_single_phase") as mock_phase:
                from skill_cert.cli import EXIT_PASS

                mock_phase.return_value = EXIT_PASS
                exit_code = run_single_mode(args, config)
                assert exit_code == EXIT_PASS
