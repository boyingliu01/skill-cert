"""Tests for engine/calibration.py — golden eval set and calibration."""

from engine.calibration import (
    CalibrationReport,
    CalibrationRunner,
    GoldenEvalCase,
    GoldenEvalSet,
)

# ─── GoldenEvalCase / GoldenEvalSet ──────────────────────────────────────


class TestGoldenEvalCase:
    def test_creation(self):
        case = GoldenEvalCase(
            eval_id="test-1",
            prompt="Say hello",
            model_output="Hello!",
            human_passed=True,
        )
        assert case.eval_id == "test-1"
        assert case.human_passed is True
        assert case.assertion_results == []

    def test_with_assertion_results(self):
        case = GoldenEvalCase(
            eval_id="test-2",
            prompt="test",
            model_output="output",
            human_passed=False,
            assertion_results=[{"name": "a1", "passed": True}],
        )
        assert len(case.assertion_results) == 1


class TestGoldenEvalSet:
    def test_empty_set(self):
        gs = GoldenEvalSet()
        assert len(gs) == 0
        assert gs.get_cases() == []

    def test_add_case(self):
        gs = GoldenEvalSet()
        case = GoldenEvalCase("1", "p", "o", True)
        gs.add_case(case)
        assert len(gs) == 1

    def test_from_dicts(self):
        data = [
            {"eval_id": "1", "prompt": "p1", "model_output": "o1", "human_passed": True},
            {"eval_id": "2", "prompt": "p2", "model_output": "o2", "human_passed": False},
        ]
        gs = GoldenEvalSet.from_dicts(data)
        assert len(gs) == 2
        cases = gs.get_cases()
        assert cases[0].eval_id == "1"
        assert cases[0].human_passed is True
        assert cases[1].human_passed is False


# ─── CalibrationRunner ────────────────────────────────────────────────────


class TestCalibrationRunner:
    def test_calibrate_empty_set(self):
        runner = CalibrationRunner()
        report = runner.calibrate(GoldenEvalSet())
        assert report.total_cases == 0
        assert report.agreement_rate == 0.0

    def test_calibrate_perfect_agreement(self):
        """All auto results match human → agreement_rate = 1.0."""
        gs = GoldenEvalSet(
            [
                GoldenEvalCase("1", "p", "o", True),
                GoldenEvalCase("2", "p", "o", False),
                GoldenEvalCase("3", "p", "o", True),
            ]
        )
        auto = [True, False, True]
        runner = CalibrationRunner()
        report = runner.calibrate(gs, auto)

        assert report.agreement_rate == 1.0
        assert report.false_positive_rate == 0.0
        assert report.false_negative_rate == 0.0
        assert report.true_positives == 2
        assert report.true_negatives == 1
        assert report.false_positives == 0
        assert report.false_negatives == 0
        assert report.cohens_kappa == 1.0

    def test_calibrate_all_disagree(self):
        """All auto results disagree with human → agreement_rate = 0.0."""
        gs = GoldenEvalSet(
            [
                GoldenEvalCase("1", "p", "o", True),
                GoldenEvalCase("2", "p", "o", False),
            ]
        )
        auto = [False, True]
        runner = CalibrationRunner()
        report = runner.calibrate(gs, auto)

        assert report.agreement_rate == 0.0
        assert report.false_negatives == 1
        assert report.false_positives == 1

    def test_calibrate_with_false_positives(self):
        """Auto passes when human fails → FPR > 0."""
        gs = GoldenEvalSet(
            [
                GoldenEvalCase("1", "p", "o", False),  # human=fail
                GoldenEvalCase("2", "p", "o", False),
            ]
        )
        auto = [True, False]  # first is FP
        runner = CalibrationRunner()
        report = runner.calibrate(gs, auto)

        assert report.false_positives == 1
        assert report.false_positive_rate == 0.5  # 1/(1+1)

    def test_calibrate_with_false_negatives(self):
        """Auto fails when human passes → FNR > 0."""
        gs = GoldenEvalSet(
            [
                GoldenEvalCase("1", "p", "o", True),  # human=pass
                GoldenEvalCase("2", "p", "o", True),
            ]
        )
        auto = [False, True]  # first is FN
        runner = CalibrationRunner()
        report = runner.calibrate(gs, auto)

        assert report.false_negatives == 1
        assert report.false_negative_rate == 0.5  # 1/(1+1)

    def test_cohens_kappa_random(self):
        """Kappa near 0 when agreement is by chance."""
        # 50/50 agreement expected by chance
        gs = GoldenEvalSet(
            [
                GoldenEvalCase("1", "p", "o", True),
                GoldenEvalCase("2", "p", "o", False),
                GoldenEvalCase("3", "p", "o", True),
                GoldenEvalCase("4", "p", "o", False),
            ]
        )
        auto = [True, True, False, False]  # 2 agree, 2 disagree
        runner = CalibrationRunner()
        report = runner.calibrate(gs, auto)

        assert report.agreement_rate == 0.5
        # Kappa should be near 0 for chance-level agreement
        assert report.cohens_kappa <= 0.1

    def test_calibrate_uses_assertion_results(self):
        """When no auto_results, uses assertion_results from cases."""
        gs = GoldenEvalSet(
            [
                GoldenEvalCase("1", "p", "o", True, [{"passed": True}]),
                GoldenEvalCase("2", "p", "o", False, [{"passed": False}]),
            ]
        )
        runner = CalibrationRunner()
        report = runner.calibrate(gs)

        assert report.agreement_rate == 1.0
        assert report.total_cases == 2

    def test_calibrate_no_grader_no_assertions(self):
        """Without grader or assertion_results, all auto=False."""
        gs = GoldenEvalSet(
            [
                GoldenEvalCase("1", "p", "o", False),  # human=fail → TN
                GoldenEvalCase("2", "p", "o", True),  # human=pass → FN
            ]
        )
        runner = CalibrationRunner()
        report = runner.calibrate(gs)

        assert report.false_negatives == 1
        assert report.true_negatives == 1


# ─── Cohen's Kappa Edge Cases ────────────────────────────────────────────


class TestCohensKappa:
    def test_zero_cases(self):
        kappa = CalibrationRunner._cohens_kappa(0, 0, 0, 0)
        assert kappa == 0.0

    def test_perfect_agreement(self):
        kappa = CalibrationRunner._cohens_kappa(5, 5, 0, 0)
        assert kappa == 1.0

    def test_perfect_disagreement(self):
        kappa = CalibrationRunner._cohens_kappa(0, 0, 5, 5)
        assert kappa < 0  # Worse than chance

    def test_all_positive_agreement(self):
        """Both always say positive → p_e = 1.0, p_o = 1.0 → kappa = 1.0."""
        kappa = CalibrationRunner._cohens_kappa(10, 0, 0, 0)
        assert kappa == 1.0


# ─── CalibrationReport ───────────────────────────────────────────────────


class TestCalibrationReport:
    def test_report_fields(self):
        report = CalibrationReport(
            agreement_rate=0.95,
            false_positive_rate=0.02,
            false_negative_rate=0.03,
            cohens_kappa=0.90,
            total_cases=100,
            true_positives=80,
            true_negatives=15,
            false_positives=2,
            false_negatives=3,
        )
        assert report.agreement_rate == 0.95
        assert report.total_cases == 100
        assert (
            report.true_positives
            + report.true_negatives
            + report.false_positives
            + report.false_negatives
            == 100
        )


# ─── Calibration CLI integration (slice-7) ────────────────────────────


class TestCalibrationCLIIntegration:
    def test_load_calibration_set_from_json_file(self, tmp_path):
        """--calibration-set loads a golden eval set from a JSON file."""
        import json

        from engine.calibration import GoldenEvalSet

        calibration_data = [
            {"eval_id": "1", "prompt": "p1", "model_output": "o1", "human_passed": True},
            {"eval_id": "2", "prompt": "p2", "model_output": "o2", "human_passed": False},
        ]
        cal_file = tmp_path / "golden.json"
        cal_file.write_text(json.dumps(calibration_data))

        raw = json.loads(cal_file.read_text())
        gs = GoldenEvalSet.from_dicts(raw)
        assert len(gs) == 2
        assert gs.get_cases()[0].human_passed is True

    def test_run_calibration_after_grading(self):
        """CalibrationRunner.calibrate() can be called with auto_results from grading."""
        gs = GoldenEvalSet(
            [
                GoldenEvalCase("1", "p", "o", True),
                GoldenEvalCase("2", "p", "o", False),
                GoldenEvalCase("3", "p", "o", True),
            ]
        )
        auto_results = [True, False, True]
        runner = CalibrationRunner()
        report = runner.calibrate(gs, auto_results)
        assert report.agreement_rate == 1.0
        assert report.cohens_kappa == 1.0

    def test_calibration_report_to_dict_for_structured_report(self):
        """CalibrationReport can be converted to dict for StructuredReport.extras."""
        report = CalibrationReport(
            agreement_rate=0.95,
            false_positive_rate=0.02,
            false_negative_rate=0.03,
            cohens_kappa=0.90,
            total_cases=100,
            true_positives=80,
            true_negatives=15,
            false_positives=2,
            false_negatives=3,
        )
        from dataclasses import asdict

        data = asdict(report)
        assert data["agreement_rate"] == 0.95
        assert data["total_cases"] == 100
        assert isinstance(data, dict)
