"""Tests for engine/drift.py — cross-model drift detection."""

from engine.drift import DriftDetector, DriftResult
from engine.grader import EvalAssertion, EvalCase, Grader


class MockModelAdapter:
    """Mock model adapter for testing."""

    def __init__(self, responses):
        self.responses = responses
        self.call_count = 0
        self.chat_called = []

    def chat(self, messages):
        """Return predefined response based on prompt."""
        prompt = messages[0].get("content", "") if messages else ""
        self.chat_called.append(prompt)
        if "hello" in prompt.lower():
            return self.responses.get("hello", "Hello response")
        elif "goodbye" in prompt.lower():
            return self.responses.get("goodbye", "Goodbye response")
        else:
            return self.responses.get("default", "Default response")


class TestDriftDetector:
    def test_detect_drift_basic(self):
        detector = DriftDetector()
        grader = Grader()

        eval_cases = [
            EvalCase(
                id=1,
                name="hello_test",
                category="normal",
                prompt="Say hello",
                assertions=[
                    EvalAssertion(name="contains_hello", type="contains", value="hello", weight=1)
                ],
            ),
            EvalCase(
                id=2,
                name="goodbye_test",
                category="normal",
                prompt="Say goodbye",
                assertions=[
                    EvalAssertion(
                        name="contains_goodbye", type="contains", value="goodbye", weight=1
                    )
                ],
            ),
        ]

        model_adapters = {
            "model_a": MockModelAdapter({"hello": "Hello there!", "goodbye": "Goodbye!"}),
            "model_b": MockModelAdapter({"hello": "Hi there!", "goodbye": "Bye!"}),
        }

        results = detector.detect_drift(eval_cases, model_adapters, grader)

        assert len(results) == 1
        result = results[0]

        assert result.model_a == "model_a"
        assert result.model_b == "model_b"
        assert isinstance(result.pass_rate_a, float)
        assert isinstance(result.pass_rate_b, float)
        assert isinstance(result.variance, float)
        assert result.severity in ["none", "low", "moderate", "high"]
        assert result.verdict in ["PASS", "PASS_WITH_CAVEATS", "FAIL"]

    def test_detect_drift_no_variance(self):
        detector = DriftDetector()
        grader = Grader()

        eval_cases = [
            EvalCase(
                id=1,
                name="identical_test",
                category="normal",
                prompt="Say hello",
                assertions=[
                    EvalAssertion(name="contains_hello", type="contains", value="hello", weight=1)
                ],
            )
        ]

        model_adapters = {
            "model_a": MockModelAdapter({"hello": "Hello world"}),
            "model_b": MockModelAdapter({"hello": "Hello world"}),
        }

        results = detector.detect_drift(eval_cases, model_adapters, grader)

        assert len(results) == 1
        result = results[0]

        assert result.pass_rate_a == result.pass_rate_b
        assert result.variance == 0.0
        assert result.severity == "none"
        assert result.verdict == "PASS"

    def test_detect_drift_high_variance(self):
        detector = DriftDetector()
        grader = Grader()

        eval_cases = [
            EvalCase(
                id=1,
                name="different_test",
                category="normal",
                prompt="Say hello",
                assertions=[
                    EvalAssertion(name="contains_hello", type="contains", value="hello", weight=1)
                ],
            )
        ]

        model_adapters = {
            "model_a": MockModelAdapter({"hello": "Hello world"}),
            "model_b": MockModelAdapter({"hello": "Goodbye world"}),
        }

        results = detector.detect_drift(eval_cases, model_adapters, grader)

        assert len(results) == 1
        result = results[0]

        assert result.pass_rate_a == 1.0
        assert result.pass_rate_b == 0.0
        assert result.variance == 1.0
        assert result.severity == "high"
        assert result.verdict == "FAIL"

    def test_determine_severity_thresholds(self):
        detector = DriftDetector()

        assert detector._determine_severity(0.05) == "none"
        assert detector._determine_severity(0.10) == "none"
        assert detector._determine_severity(0.15) == "low"
        assert detector._determine_severity(0.20) == "low"
        assert detector._determine_severity(0.25) == "moderate"
        assert detector._determine_severity(0.30) == "moderate"
        assert detector._determine_severity(0.35) == "moderate"
        assert detector._determine_severity(0.40) == "high"
        assert detector._determine_severity(0.50) == "high"

    def test_map_verdict(self):
        detector = DriftDetector()

        assert detector._map_verdict("none") == "PASS"
        assert detector._map_verdict("low") == "PASS"
        assert detector._map_verdict("moderate") == "PASS_WITH_CAVEATS"
        assert detector._map_verdict("high") == "FAIL"

    def test_aggregate_drift_report_empty(self):
        detector = DriftDetector()

        report = detector.aggregate_drift_report([])

        assert report["drift_detected"] is False
        assert report["highest_severity"] == "none"
        assert report["average_variance"] == 0.0
        assert report["model_pairs_compared"] == 0
        assert "No drift analysis performed" in report["summary"]

    def test_aggregate_drift_report_single_result(self):
        detector = DriftDetector()

        results = [
            DriftResult(
                model_a="model_a",
                model_b="model_b",
                pass_rate_a=0.8,
                pass_rate_b=0.6,
                variance=0.2,
                severity="low",
                verdict="PASS",
            )
        ]

        report = detector.aggregate_drift_report(results)

        assert report["drift_detected"] is False  # Low severity doesn't count as detected
        assert report["highest_severity"] == "low"
        assert report["average_variance"] == 0.2
        assert report["max_variance"] == 0.2
        assert report["model_pairs_compared"] == 1
        assert report["severity_distribution"]["low"] == 1
        assert report["overall_verdict"] == "PASS"

    def test_aggregate_drift_report_multiple_results(self):
        detector = DriftDetector()

        results = [
            DriftResult(
                model_a="model_a",
                model_b="model_b",
                pass_rate_a=0.8,
                pass_rate_b=0.6,
                variance=0.2,
                severity="low",
                verdict="PASS_WITH_CAVEATS",
            ),
            DriftResult(
                model_a="model_a",
                model_b="model_c",
                pass_rate_a=0.8,
                pass_rate_b=0.3,
                variance=0.5,
                severity="high",
                verdict="FAIL",
            ),
        ]

        report = detector.aggregate_drift_report(results)

        assert report["drift_detected"] is True
        assert report["highest_severity"] == "high"
        assert report["average_variance"] == 0.35
        assert report["max_variance"] == 0.5
        assert report["model_pairs_compared"] == 2
        assert report["severity_distribution"]["low"] == 1
        assert report["severity_distribution"]["high"] == 1
        assert report["overall_verdict"] == "FAIL"

    def test_get_highest_severity(self):
        detector = DriftDetector()

        results = [
            DriftResult(
                model_a="a",
                model_b="b",
                pass_rate_a=0.5,
                pass_rate_b=0.5,
                variance=0.0,
                severity="none",
                verdict="PASS",
            ),
            DriftResult(
                model_a="a",
                model_b="c",
                pass_rate_a=0.5,
                pass_rate_b=0.5,
                variance=0.15,
                severity="low",
                verdict="PASS",
            ),
            DriftResult(
                model_a="a",
                model_b="d",
                pass_rate_a=0.5,
                pass_rate_b=0.5,
                variance=0.3,
                severity="moderate",
                verdict="PASS_WITH_CAVEATS",
            ),
            DriftResult(
                model_a="a",
                model_b="e",
                pass_rate_a=0.5,
                pass_rate_b=0.5,
                variance=0.4,
                severity="high",
                verdict="FAIL",
            ),
        ]

        highest = detector._get_highest_severity(results)

        assert highest == "high"

    def test_aggregate_verdict(self):
        detector = DriftDetector()

        results_all_pass = [
            DriftResult(
                model_a="a",
                model_b="b",
                pass_rate_a=0.5,
                pass_rate_b=0.5,
                variance=0.05,
                severity="none",
                verdict="PASS",
            ),
            DriftResult(
                model_a="a",
                model_b="c",
                pass_rate_a=0.5,
                pass_rate_b=0.5,
                variance=0.08,
                severity="none",
                verdict="PASS",
            ),
        ]
        assert detector._aggregate_verdict(results_all_pass) == "PASS"

        results_with_caveats = [
            DriftResult(
                model_a="a",
                model_b="b",
                pass_rate_a=0.5,
                pass_rate_b=0.5,
                variance=0.05,
                severity="none",
                verdict="PASS",
            ),
            DriftResult(
                model_a="a",
                model_b="c",
                pass_rate_a=0.5,
                pass_rate_b=0.5,
                variance=0.25,
                severity="moderate",
                verdict="PASS_WITH_CAVEATS",
            ),
        ]
        assert detector._aggregate_verdict(results_with_caveats) == "PASS_WITH_CAVEATS"

        results_with_fail = [
            DriftResult(
                model_a="a",
                model_b="b",
                pass_rate_a=0.5,
                pass_rate_b=0.5,
                variance=0.05,
                severity="none",
                verdict="PASS",
            ),
            DriftResult(
                model_a="a",
                model_b="c",
                pass_rate_a=0.5,
                pass_rate_b=0.5,
                variance=0.4,
                severity="high",
                verdict="FAIL",
            ),
        ]
        assert detector._aggregate_verdict(results_with_fail) == "FAIL"


class TestCrossModelUncertainty:
    """Tests for CMP and CME metrics."""

    def test_calculate_cmp_empty(self):
        """Empty drift results → agreement_rate = 1.0."""
        detector = DriftDetector()
        cmp = detector.calculate_cmp([])
        assert cmp["agreement_rate"] == 1.0
        assert cmp["pairwise_agreements"] == []

    def test_calculate_cmp_all_agree(self):
        """All pairs have low severity → agreement_rate = 1.0."""
        detector = DriftDetector()
        results = [
            DriftResult("a", "b", 0.8, 0.85, 0.05, "none", "PASS"),
            DriftResult("a", "c", 0.8, 0.75, 0.05, "low", "PASS"),
        ]
        cmp = detector.calculate_cmp(results)
        assert cmp["agreement_rate"] == 1.0
        assert len(cmp["pairwise_agreements"]) == 2
        assert all(p["agrees"] for p in cmp["pairwise_agreements"])

    def test_calculate_cmp_partial_agreement(self):
        """Some pairs disagree → agreement_rate < 1.0."""
        detector = DriftDetector()
        results = [
            DriftResult("a", "b", 0.8, 0.85, 0.05, "none", "PASS"),
            DriftResult("a", "c", 0.8, 0.3, 0.5, "high", "FAIL"),
        ]
        cmp = detector.calculate_cmp(results)
        assert cmp["agreement_rate"] == 0.5

    def test_calculate_cme_empty(self):
        """Empty pass rates → all zeros."""
        detector = DriftDetector()
        cme = detector.calculate_cme([])
        assert cme["coefficient_of_variation"] == 0.0
        assert cme["max_min_spread"] == 0.0
        assert cme["mean_pass_rate"] == 0.0

    def test_calculate_cme_single_value(self):
        """Single value → zero spread and CV."""
        detector = DriftDetector()
        cme = detector.calculate_cme([0.8])
        assert cme["coefficient_of_variation"] == 0.0
        assert cme["max_min_spread"] == 0.0
        assert cme["mean_pass_rate"] == 0.8

    def test_calculate_cme_uniform_values(self):
        """All same values → zero CV and spread."""
        detector = DriftDetector()
        cme = detector.calculate_cme([0.8, 0.8, 0.8])
        assert cme["coefficient_of_variation"] == 0.0
        assert cme["max_min_spread"] == 0.0
        assert cme["mean_pass_rate"] == 0.8

    def test_calculate_cme_variable_values(self):
        """Variable values → non-zero CV and spread."""
        detector = DriftDetector()
        cme = detector.calculate_cme([0.6, 0.8, 0.9])
        assert cme["coefficient_of_variation"] > 0
        assert cme["max_min_spread"] == 0.3
        assert cme["mean_pass_rate"] > 0.7

    def test_calculate_cme_zero_mean(self):
        """Zero mean → CV = 0.0."""
        detector = DriftDetector()
        cme = detector.calculate_cme([0.0, 0.0])
        assert cme["coefficient_of_variation"] == 0.0

    def test_aggregate_report_includes_uncertainty(self):
        """aggregate_drift_report includes cross_model_uncertainty section."""
        detector = DriftDetector()
        results = [
            DriftResult("a", "b", 0.8, 0.85, 0.05, "none", "PASS"),
            DriftResult("a", "c", 0.8, 0.6, 0.2, "low", "PASS"),
        ]
        report = detector.aggregate_drift_report(results)
        assert "cross_model_uncertainty" in report
        cmp = report["cross_model_uncertainty"]["cmp_agreement_rate"]
        cme = report["cross_model_uncertainty"]["cme_variation"]
        assert "agreement_rate" in cmp
        assert "coefficient_of_variation" in cme
        assert "max_min_spread" in cme


class TestDriftDictEvalCases:
    """Tests for drift with dict-based eval cases (covers lines 33, 38-75, 82, 116)."""

    def test_extract_prompt_from_dict_with_prompt(self):
        detector = DriftDetector()
        assert detector._extract_prompt({"prompt": "hello"}) == "hello"

    def test_extract_prompt_from_dict_with_input(self):
        detector = DriftDetector()
        assert detector._extract_prompt({"input": "world"}) == "world"

    def test_extract_prompt_from_dict_empty(self):
        detector = DriftDetector()
        assert detector._extract_prompt({}) == ""

    def test_calculate_pass_rate_empty_results(self):
        detector = DriftDetector()
        assert detector._calculate_model_pass_rate([]) == 0.0

    def test_build_assertions_from_dict(self):
        detector = DriftDetector()
        eval_case = {
            "id": 1,
            "name": "dict_test",
            "category": "normal",
            "assertions": [
                {"name": "has_hello", "type": "contains", "value": "hello", "weight": "1"}
            ],
        }
        assertions = detector._build_assertions(eval_case)
        assert len(assertions) == 1
        assert assertions[0].name == "has_hello"
        assert assertions[0].value == "hello"

    def test_build_assertions_empty(self):
        detector = DriftDetector()
        assert detector._build_assertions({}) == []

    def test_convert_to_eval_case_from_dict(self):
        detector = DriftDetector()
        eval_case = {
            "id": 1,
            "name": "dict_case",
            "category": "normal",
            "assertions": [
                {"name": "test", "type": "contains", "value": "x", "weight": 1}
            ],
        }
        result = detector._convert_to_eval_case(eval_case, "test prompt")
        assert isinstance(result, EvalCase)
        assert result.id == 1
        assert result.prompt == "test prompt"
        assert result.name == "dict_case"

    def test_convert_to_eval_case_passthrough(self):
        detector = DriftDetector()
        existing_case = EvalCase(id=2, name="existing", category="normal", prompt="p", assertions=[])
        result = detector._convert_to_eval_case(existing_case, "ignored")
        assert result is existing_case
