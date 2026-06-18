"""Tests for engine/trigger_accuracy_eval.py — TriggerAccuracyEval (Issue #43)."""

from engine.trigger_accuracy_eval import TriggerAccuracyEval


class TestTriggerAccuracyEval:
    """Test the TriggerAccuracyEval class."""

    def test_evaluate_all_correct(self):
        evaluator = TriggerAccuracyEval()
        results = [
            {"category": "trigger", "negative_case": False, "final_passed": True},
            {"category": "trigger", "negative_case": False, "final_passed": True},
            {"category": "trigger", "negative_case": True, "final_passed": True},
            {"category": "trigger", "negative_case": True, "final_passed": True},
        ]
        r = evaluator.evaluate(results)
        assert r.accuracy == 1.0
        assert r.passed is True
        assert r.tp == 2
        assert r.tn == 2
        assert r.fp == 0
        assert r.fn == 0

    def test_evaluate_some_failures(self):
        evaluator = TriggerAccuracyEval()
        results = [
            {"category": "trigger", "negative_case": False, "final_passed": True},   # TP
            {"category": "trigger", "negative_case": False, "final_passed": False},  # FN
            {"category": "trigger", "negative_case": True, "final_passed": True},    # TN
            {"category": "trigger", "negative_case": True, "final_passed": False},   # FP
        ]
        r = evaluator.evaluate(results)
        assert r.tp == 1
        assert r.fn == 1
        assert r.tn == 1
        assert r.fp == 1
        assert r.accuracy == 0.5
        assert r.passed is False
        assert r.precision == 0.5
        assert r.recall == 0.5
        assert r.f1_score == 0.5

    def test_evaluate_no_trigger_results(self):
        evaluator = TriggerAccuracyEval()
        results = [
            {"category": "normal", "final_passed": True},
        ]
        r = evaluator.evaluate(results)
        assert r.accuracy == 0.0
        assert r.passed is False
        assert r.total == 0

    def test_evaluate_empty(self):
        evaluator = TriggerAccuracyEval()
        r = evaluator.evaluate([])
        assert r.accuracy == 0.0
        assert r.passed is False

    def test_evaluate_positive_only(self):
        evaluator = TriggerAccuracyEval()
        results = [
            {"category": "trigger", "negative_case": False, "final_passed": True},
            {"category": "trigger", "negative_case": False, "final_passed": False},
        ]
        r = evaluator.evaluate(results)
        assert r.tp == 1
        assert r.fn == 1
        assert r.tn == 0
        assert r.fp == 0
        assert r.accuracy == 0.5
        assert r.precision == 1.0
        assert r.recall == 0.5
        assert r.positive_cases == 2
        assert r.negative_cases == 0

    def test_evaluate_negative_only(self):
        evaluator = TriggerAccuracyEval()
        results = [
            {"category": "trigger", "negative_case": True, "final_passed": True},
            {"category": "trigger", "negative_case": True, "final_passed": False},
        ]
        r = evaluator.evaluate(results)
        assert r.tp == 0
        assert r.fn == 0
        assert r.tn == 1
        assert r.fp == 1
        assert r.accuracy == 0.5
        assert r.recall == 0.0
        assert r.positive_cases == 0
        assert r.negative_cases == 2

    def test_check_threshold_passes(self):
        evaluator = TriggerAccuracyEval()
        results = [
            {"category": "trigger", "negative_case": False, "final_passed": True},
            {"category": "trigger", "negative_case": True, "final_passed": True},
        ]
        assert evaluator.check_threshold(results) is True

    def test_check_threshold_fails(self):
        evaluator = TriggerAccuracyEval()
        results = [
            {"category": "trigger", "negative_case": False, "final_passed": False},
        ]
        assert evaluator.check_threshold(results) is False

    def test_custom_threshold(self):
        evaluator = TriggerAccuracyEval(threshold=0.50)
        results = [
            {"category": "trigger", "negative_case": False, "final_passed": True},
            {"category": "trigger", "negative_case": False, "final_passed": False},
        ]
        r = evaluator.evaluate(results)
        assert r.accuracy == 0.5
        assert r.passed is True  # 0.5 >= 0.50 threshold

    def test_to_dict_structure(self):
        evaluator = TriggerAccuracyEval()
        results = [
            {
                "category": "trigger", "negative_case": False,
                "final_passed": True, "eval_id": "e1", "eval_name": "test",
            },
            {
                "category": "trigger", "negative_case": True,
                "final_passed": False, "eval_id": "e2", "eval_name": "neg",
            },
        ]
        r = evaluator.evaluate(results)
        d = r.to_dict()
        assert "accuracy" in d
        assert "confusion_matrix" in d
        assert "precision" in d
        assert "recall" in d
        assert "f1_score" in d
        assert len(d["case_results"]) == 2
