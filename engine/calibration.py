"""Calibration module — measures agreement between automated eval and human ground truth."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GoldenEvalCase:
    """A single golden evaluation case with human-annotated ground truth."""

    eval_id: str
    prompt: str
    model_output: str
    human_passed: bool
    assertion_results: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CalibrationReport:
    """Report from calibrating automated eval against golden set."""

    agreement_rate: float
    false_positive_rate: float  # Auto=pass, Human=fail
    false_negative_rate: float  # Auto=fail, Human=pass
    cohens_kappa: float
    total_cases: int
    true_positives: int
    true_negatives: int
    false_positives: int
    false_negatives: int


class GoldenEvalSet:
    """Manages a collection of human-annotated golden evaluation cases."""

    def __init__(self, cases: list[GoldenEvalCase] | None = None):
        self._cases: list[GoldenEvalCase] = cases or []

    def add_case(self, case: GoldenEvalCase) -> None:
        """Add a golden eval case."""
        self._cases.append(case)

    def get_cases(self) -> list[GoldenEvalCase]:
        """Return all golden eval cases."""
        return list(self._cases)

    def __len__(self) -> int:
        return len(self._cases)

    @classmethod
    def from_dicts(cls, data: list[dict[str, Any]]) -> "GoldenEvalSet":
        """Create GoldenEvalSet from list of dicts."""
        cases = []
        for d in data:
            cases.append(
                GoldenEvalCase(
                    eval_id=d.get("eval_id", ""),
                    prompt=d.get("prompt", ""),
                    model_output=d.get("model_output", ""),
                    human_passed=d.get("human_passed", False),
                    assertion_results=d.get("assertion_results", []),
                )
            )
        return cls(cases)


class CalibrationRunner:
    """Runs calibration analysis comparing automated eval to golden set."""

    def __init__(self, grader=None):
        """Initialize with optional grader for automated evaluation."""
        self.grader = grader

    def _build_confusion_matrix(
        self, cases: list[GoldenEvalCase], auto_results: list[bool]
    ) -> dict[str, int]:
        """Build confusion matrix from human and automated results."""
        n = min(len(cases), len(auto_results))
        tp = tn = fp = fn = 0

        for i in range(n):
            human = cases[i].human_passed
            auto = auto_results[i]
            if auto and human:
                tp += 1
            elif not auto and not human:
                tn += 1
            elif auto and not human:
                fp += 1
            elif not auto and human:
                fn += 1

        return {"tp": tp, "tn": tn, "fp": fp, "fn": fn}

    def _calculate_metrics(
        self, tp: int, tn: int, fp: int, fn: int, n: int
    ) -> tuple[float, float, float, float]:
        """Calculate agreement rate, FPR, FNR, and kappa."""
        agreement_rate = (tp + tn) / n if n > 0 else 0.0
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
        fnr = fn / (fn + tp) if (fn + tp) > 0 else 0.0
        kappa = self._cohens_kappa(tp, tn, fp, fn)
        return agreement_rate, fpr, fnr, kappa

    def _build_calibration_report(
        self, tp: int, tn: int, fp: int, fn: int, n: int
    ) -> CalibrationReport:
        """Build CalibrationReport from confusion matrix."""
        agreement_rate, fpr, fnr, kappa = self._calculate_metrics(tp, tn, fp, fn, n)
        return CalibrationReport(
            agreement_rate=round(agreement_rate, 4),
            false_positive_rate=round(fpr, 4),
            false_negative_rate=round(fnr, 4),
            cohens_kappa=round(kappa, 4),
            total_cases=n,
            true_positives=tp,
            true_negatives=tn,
            false_positives=fp,
            false_negatives=fn,
        )

    def calibrate(
        self,
        golden_set: GoldenEvalSet,
        auto_results: list[bool] | None = None,
    ) -> CalibrationReport:
        """Compare automated results against golden set.

        Args:
            golden_set: The human-annotated ground truth
            auto_results: List of booleans (True=pass, False=fail) from automated eval.
                         If None, uses grader to evaluate golden cases.

        Returns:
            CalibrationReport with agreement metrics.
        """
        cases = golden_set.get_cases()
        if not cases:
            return CalibrationReport(
                agreement_rate=0.0,
                false_positive_rate=0.0,
                false_negative_rate=0.0,
                cohens_kappa=0.0,
                total_cases=0,
                true_positives=0,
                true_negatives=0,
                false_positives=0,
                false_negatives=0,
            )

        # Get automated results
        if auto_results is None:
            auto_results = self._evaluate_cases(cases)

        # Build confusion matrix
        n = min(len(cases), len(auto_results))
        matrix = self._build_confusion_matrix(cases, auto_results)

        # Build and return report
        return self._build_calibration_report(
            matrix["tp"], matrix["tn"], matrix["fp"], matrix["fn"], n
        )

    def _evaluate_cases(self, cases: list[GoldenEvalCase]) -> list[bool]:
        """Evaluate cases using the grader if available, else use assertion_results."""
        results = []
        for case in cases:
            if case.assertion_results:
                # Use provided assertion results
                passed = all(ar.get("passed", False) for ar in case.assertion_results)
                results.append(passed)
            elif self.grader is not None:
                # Use grader to evaluate
                from engine.grader import EvalAssertion, EvalCase

                assertions = []
                for ar in case.assertion_results:
                    assertions.append(
                        EvalAssertion(
                            name=ar.get("name", ""),
                            type=ar.get("type", "contains"),
                            value=ar.get("value", ""),
                        )
                    )
                eval_case = EvalCase(
                    id=0,
                    name=case.eval_id,
                    category="normal",
                    prompt=case.prompt,
                    assertions=assertions,
                )
                grade = self.grader.grade_output(eval_case, case.model_output)
                results.append(grade.get("passed", False))
            else:
                results.append(False)
        return results

    @staticmethod
    def _cohens_kappa(tp: int, tn: int, fp: int, fn: int) -> float:
        """Calculate Cohen's Kappa statistic.

        κ = (p_o - p_e) / (1 - p_e)
        where p_o = observed agreement, p_e = expected agreement by chance.
        """
        n = tp + tn + fp + fn
        if n == 0:
            return 0.0

        p_o = (tp + tn) / n

        # Marginal probabilities
        auto_pos = (tp + fp) / n  # P(auto=positive)
        auto_neg = (tn + fn) / n  # P(auto=negative)
        human_pos = (tp + fn) / n  # P(human=positive)
        human_neg = (tn + fp) / n  # P(human=negative)

        p_e = auto_pos * human_pos + auto_neg * human_neg

        if p_e == 1.0:
            return 1.0 if p_o == 1.0 else 0.0

        return (p_o - p_e) / (1 - p_e)
