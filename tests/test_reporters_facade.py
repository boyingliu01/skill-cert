"""Tests for engine/reporters/ package facade re-exports.

Verifies that the refactored package structure maintains backward compatibility:
- engine.reporter.Reporter still works (facade re-export)
- engine.reporters submodules are importable
- Reporter from facade is the same class as from generator
"""



class TestFacadeReExports:
    """Verify engine.reporter facade re-exports work correctly."""

    def test_reporter_importable_from_facade(self):
        """Reporter class is importable from engine.reporter (backward compat)."""
        from engine.reporter import Reporter

        assert Reporter is not None
        assert callable(Reporter)

    def test_reporter_is_class(self):
        """Reporter from facade is a class."""
        from engine.reporter import Reporter

        assert isinstance(Reporter, type)

    def test_reporter_instantiable(self):
        """Reporter can be instantiated from facade import."""
        from engine.reporter import Reporter

        reporter = Reporter()
        assert reporter is not None

    def test_reporter_has_generate_report(self):
        """Reporter has generate_report method."""
        from engine.reporter import Reporter

        reporter = Reporter()
        assert hasattr(reporter, "generate_report")
        assert callable(reporter.generate_report)

    def test_reporter_has_build_structured_report(self):
        """Reporter has build_structured_report method."""
        from engine.reporter import Reporter

        reporter = Reporter()
        assert hasattr(reporter, "build_structured_report")
        assert callable(reporter.build_structured_report)

    def test_reporter_has_generate_report_with_multi_skill(self):
        """Reporter has generate_report_with_multi_skill method."""
        from engine.reporter import Reporter

        reporter = Reporter()
        assert hasattr(reporter, "generate_report_with_multi_skill")

    def test_reporter_has_generate_report_with_stress(self):
        """Reporter has generate_report_with_stress method."""
        from engine.reporter import Reporter

        reporter = Reporter()
        assert hasattr(reporter, "generate_report_with_stress")

    def test_reporter_has_generate_json_report(self):
        """Reporter has generate_json_report method."""
        from engine.reporter import Reporter

        reporter = Reporter()
        assert hasattr(reporter, "generate_json_report")

    def test_reporter_has_validate_json_report(self):
        """Reporter has validate_json_report method."""
        from engine.reporter import Reporter

        reporter = Reporter()
        assert hasattr(reporter, "validate_json_report")


class TestSubmoduleImports:
    """Verify engine.reporters submodules are importable."""

    def test_reporters_package_importable(self):
        """engine.reporters package is importable."""
        import engine.reporters

        assert engine.reporters is not None

    def test_formatters_importable(self):
        """engine.reporters.formatters is importable."""
        from engine.reporters import formatters

        assert formatters is not None

    def test_builders_importable(self):
        """engine.reporters.builders is importable."""
        from engine.reporters import builders

        assert builders is not None

    def test_generator_importable(self):
        """engine.reporters.generator is importable."""
        from engine.reporters import generator

        assert generator is not None


class TestReporterIdentity:
    """Verify Reporter from facade is the same as from generator."""

    def test_facade_reporter_is_generator_reporter(self):
        """Reporter from engine.reporter is the same class as engine.reporters.generator."""
        from engine.reporter import Reporter as FacadeReporter
        from engine.reporters.generator import Reporter as GeneratorReporter

        assert FacadeReporter is GeneratorReporter

    def test_reporters_init_reexports_reporter(self):
        """engine.reporters.__init__ re-exports Reporter."""
        from engine.reporter import Reporter as FacadeReporter
        from engine.reporters import Reporter as PackageReporter

        assert PackageReporter is FacadeReporter


class TestFormattersModuleContents:
    """Verify formatters module has expected utility functions."""

    def test_has_num_function(self):
        """formatters module has num() utility function."""
        from engine.reporters.formatters import num

        assert callable(num)
        assert num(None) == 0.0
        assert num(0.85) == 0.85
        assert num(None, 1.0) == 1.0

    def test_has_redact_config_function(self):
        """formatters module has redact_config() function."""
        from engine.reporters.formatters import redact_config

        assert callable(redact_config)
        config = {"models": [{"model_name": "m1", "api_key": "secret"}]}
        redacted = redact_config(config)
        assert "api_key" not in str(redacted["models"])
        assert redacted["models"][0]["model_name"] == "m1"


class TestBuildersModuleContents:
    """Verify builders module has expected builder functions."""

    def test_has_prepare_drift_data(self):
        """builders module has prepare_drift_data() function."""
        from engine.reporters.builders import prepare_drift_data

        assert callable(prepare_drift_data)
        result = prepare_drift_data(None)
        assert result["drift_detected"] is False

    def test_has_prepare_coverage_data(self):
        """builders module has prepare_coverage_data() function."""
        from engine.reporters.builders import prepare_coverage_data

        assert callable(prepare_coverage_data)

    def test_has_prepare_config_info(self):
        """builders module has prepare_config_info() function."""
        from engine.reporters.builders import prepare_config_info

        assert callable(prepare_config_info)

    def test_has_prepare_benchmark_info(self):
        """builders module has prepare_benchmark_info() function."""
        from engine.reporters.builders import prepare_benchmark_info

        assert callable(prepare_benchmark_info)

    def test_has_generate_suggestions(self):
        """builders module has generate_suggestions() function."""
        from engine.reporters.builders import generate_suggestions

        assert callable(generate_suggestions)

    def test_has_create_summary(self):
        """builders module has create_summary() function."""
        from engine.reporters.builders import create_summary

        assert callable(create_summary)
        result = create_summary("PASS", 0.85, 0.9, 0.8, 0.85, 0.85)
        assert "PASS" in result

    def test_has_determine_verdict(self):
        """builders module has determine_verdict() function."""
        from engine.reporters.builders import determine_verdict

        assert callable(determine_verdict)
        assert determine_verdict(0.85, None) == "PASS"
        assert determine_verdict(0.5, None) == "FAIL"

    def test_has_build_eval_details(self):
        """builders module has build_eval_details() function."""
        from engine.reporters.builders import build_eval_details

        assert callable(build_eval_details)
        assert build_eval_details(None) == []
        assert build_eval_details([]) == []

    def test_has_build_metrics_section(self):
        """builders module has build_metrics_section() function."""
        from engine.reporters.builders import build_metrics_section

        assert callable(build_metrics_section)

    def test_has_build_token_section(self):
        """builders module has build_token_section() function."""
        from engine.reporters.builders import build_token_section

        assert callable(build_token_section)

    def test_has_build_observability_section(self):
        """builders module has build_observability_section() function."""
        from engine.reporters.builders import build_observability_section

        assert callable(build_observability_section)

    def test_has_convert_suggestions(self):
        """builders module has convert_suggestions() function."""
        from engine.reporters.builders import convert_suggestions

        assert callable(convert_suggestions)

    def test_has_build_stress_section(self):
        """builders module has build_stress_section() function."""
        from engine.reporters.builders import build_stress_section

        assert callable(build_stress_section)

    def test_has_build_multi_skill_section(self):
        """builders module has build_multi_skill_section() function."""
        from engine.reporters.builders import build_multi_skill_section

        assert callable(build_multi_skill_section)
