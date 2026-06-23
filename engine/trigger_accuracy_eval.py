"""TriggerAccuracyEval module — dedicated L1 trigger accuracy evaluator (Issue #43)."""

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

L1_THRESHOLD = 0.90  # L1 trigger accuracy must be >= 90%


@dataclass
class TriggerCaseResult:
    """Result of a single trigger case evaluation."""

    eval_id: str | None
    eval_name: str | None
    negative_case: bool
    with_skill_triggered: bool
    without_skill_triggered: bool | None
    expected_to_trigger: bool
    with_skill_passed: bool | None
    without_skill_passed: bool | None


@dataclass
class TriggerAccuracyResult:
    """Overall trigger accuracy evaluation result."""

    accuracy: float
    threshold: float = L1_THRESHOLD
    passed: bool = False
    tp: int = 0
    tn: int = 0
    fp: int = 0
    fn: int = 0
    total: int = 0
    positive_cases: int = 0
    negative_cases: int = 0
    case_results: list[TriggerCaseResult] = field(default_factory=list)

    @property
    def precision(self) -> float:
        if self.tp + self.fp == 0:
            return 0.0
        return self.tp / (self.tp + self.fp)

    @property
    def recall(self) -> float:
        if self.tp + self.fn == 0:
            return 0.0
        return self.tp / (self.tp + self.fn)

    @property
    def f1_score(self) -> float:
        prec = self.precision
        rec = self.recall
        if prec + rec == 0.0:
            return 0.0
        return 2 * prec * rec / (prec + rec)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accuracy": self.accuracy,
            "threshold": self.threshold,
            "passed": self.passed,
            "confusion_matrix": {
                "true_positives": self.tp,
                "true_negatives": self.tn,
                "false_positives": self.fp,
                "false_negatives": self.fn,
            },
            "precision": self.precision,
            "recall": self.recall,
            "f1_score": self.f1_score,
            "total": self.total,
            "positive_cases": self.positive_cases,
            "negative_cases": self.negative_cases,
            "case_results": [
                {
                    "eval_id": c.eval_id,
                    "eval_name": c.eval_name,
                    "negative_case": c.negative_case,
                    "with_skill_triggered": c.with_skill_triggered,
                    "without_skill_triggered": c.without_skill_triggered,
                    "expected_to_trigger": c.expected_to_trigger,
                    "with_skill_passed": c.with_skill_passed,
                    "without_skill_passed": c.without_skill_passed,
                }
                for c in self.case_results
            ],
        }


class TriggerAccuracyEval:
    """Dedicated L1 trigger accuracy evaluator.

    Evaluates whether a skill triggers correctly on positive cases
    and correctly does NOT trigger on negative (should_not_trigger) cases.
    Applies a >= 90% accuracy threshold gate.
    """

    def __init__(self, threshold: float = L1_THRESHOLD):
        self.threshold = threshold

    def evaluate(self, graded_results: list[dict[str, Any]]) -> TriggerAccuracyResult:
        """Evaluate L1 trigger accuracy from graded eval results.

        Args:
            graded_results: List of graded result dicts from Grader.

        Returns:
            TriggerAccuracyResult with accuracy, confusion matrix, and pass/fail.
        """
        trigger_results = [r for r in graded_results if r.get("category") == "trigger"]

        if not trigger_results:
            return TriggerAccuracyResult(
                accuracy=0.0, threshold=self.threshold, passed=False, total=0
            )

        positive = [r for r in trigger_results if not r.get("negative_case", False)]
        negative = [r for r in trigger_results if r.get("negative_case", False)]

        tp = sum(1 for r in positive if r.get("final_passed", False))
        fn = sum(1 for r in positive if not r.get("final_passed", False))
        tn = sum(1 for r in negative if r.get("final_passed", False))
        fp = sum(1 for r in negative if not r.get("final_passed", False))

        total = tp + tn + fp + fn
        accuracy = (tp + tn) / total if total > 0 else 0.0

        case_results = []
        for r in trigger_results:
            case_results.append(
                TriggerCaseResult(
                    eval_id=r.get("eval_id"),
                    eval_name=r.get("eval_name"),
                    negative_case=r.get("negative_case", False),
                    with_skill_triggered=r.get("final_passed", False),
                    without_skill_triggered=r.get("final_passed", False),
                    expected_to_trigger=not r.get("negative_case", False),
                    with_skill_passed=r.get("final_passed"),
                    without_skill_passed=r.get("final_passed"),
                )
            )

        return TriggerAccuracyResult(
            accuracy=accuracy,
            threshold=self.threshold,
            passed=accuracy >= self.threshold,
            tp=tp,
            tn=tn,
            fp=fp,
            fn=fn,
            total=total,
            positive_cases=len(positive),
            negative_cases=len(negative),
            case_results=case_results,
        )

    def check_threshold(self, graded_results: list[dict[str, Any]]) -> bool:
        """Check if L1 trigger accuracy meets threshold.

        Returns True if accuracy >= threshold, False otherwise.
        Logs a warning when threshold is not met.
        """
        result = self.evaluate(graded_results)
        if not result.passed:
            logger.warning(
                "L1 trigger accuracy %.1f%% < %d%% threshold — blocking evaluation",
                result.accuracy * 100,
                self.threshold * 100,
            )
        return result.passed
