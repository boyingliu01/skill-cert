"""Harness-based evaluation domain layer (models, taskgen, judge, evaluator, report)."""

from .evaluator import (
    HarnessEvaluator,
    SecurityBlockedError,
    compute_deltas,
    compute_trigger_rate,
    compute_verdicts,
    condition_mean,
    dimension_score,
)
from .models import (
    Condition,
    HarnessEvalReport,
    InputFile,
    JudgeItemResult,
    JudgeResult,
    Rubric,
    RubricItem,
    RunRecord,
    Task,
    TaskDelta,
    TaskGenResult,
)
from .report import render_report, write_report

__all__ = [
    "HarnessEvaluator",
    "SecurityBlockedError",
    "compute_deltas",
    "compute_trigger_rate",
    "compute_verdicts",
    "condition_mean",
    "dimension_score",
    "render_report",
    "write_report",
    "Condition",
    "HarnessEvalReport",
    "InputFile",
    "JudgeItemResult",
    "JudgeResult",
    "Rubric",
    "RubricItem",
    "RunRecord",
    "Task",
    "TaskDelta",
    "TaskGenResult",
]
