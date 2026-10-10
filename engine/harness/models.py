"""Domain models for harness-based skill evaluation (Pydantic v2)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Condition = Literal["with_skill", "without_skill"]


class InputFile(BaseModel):
    """File written into the sandbox before a task runs."""

    path: str
    content: str


class RubricItem(BaseModel):
    id: str
    criterion: str
    # ge=1 keeps a dimension's total points non-zero — dimension_score divides by it
    points: int = Field(1, ge=1)


class Rubric(BaseModel):
    task_completion: list[RubricItem] = Field(default_factory=list)
    instruction_following: list[RubricItem] = Field(default_factory=list)

    def all_items(self) -> list[RubricItem]:
        return self.task_completion + self.instruction_following

    @model_validator(mode="after")
    def _deduplicate_item_ids(self) -> Rubric:
        # JudgeResult.score_map() keys on rubric_id: one duplicate id would
        # silently drop the other item's score from the dimension totals.
        seen: set[str] = set()
        for item in self.all_items():
            unique = item.id
            suffix = 2
            while unique in seen:
                unique = f"{item.id}-{suffix}"
                suffix += 1
            item.id = unique
            seen.add(unique)
        return self


class Task(BaseModel):
    id: str
    description: str
    input_files: list[InputFile] = Field(default_factory=list)
    rubrics: Rubric = Field(default_factory=Rubric)


class TaskGenResult(BaseModel):
    tasks: list[Task] = Field(default_factory=list)
    leakage_check: str = ""  # LLM self-check: does any description leak rubric wording?


class JudgeItemResult(BaseModel):
    rubric_id: str
    score: float  # 0-10
    evidence: str = ""


class JudgeResult(BaseModel):
    items: list[JudgeItemResult] = Field(default_factory=list)
    reasoning: str = ""

    def score_map(self) -> dict[str, float]:
        return {item.rubric_id: item.score for item in self.items}


class RunRecord(BaseModel):
    """Snapshot of one harness run (task x condition x repetition) plus judge verdict."""

    task_id: str
    condition: Condition
    run_index: int = 0
    session_id: str = ""
    final_output: str = ""
    skill_loaded: bool = False
    tool_call_count: int = 0
    tool_sequence: list[str] = Field(default_factory=list)  # ordered tool names
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost: float | None = None
    duration_s: float = 0.0
    error: str | None = None
    # Generated input files rejected by the sandbox escape check: the run spoke
    # about a fixture that was never there, so the report must say so.
    skipped_inputs: list[str] = Field(default_factory=list)
    judge: JudgeResult | None = None


class TaskDelta(BaseModel):
    task_id: str
    task_completion_delta: float | None = None
    instruction_following_delta: float | None = None
    # The raw quantities the advisory verdicts are derived from are published
    # alongside the labels: per task here, in aggregate on HarnessEvalReport.
    trigger_rate: float | None = None


class HarnessEvalReport(BaseModel):
    """Full result of one harness evaluation (N tasks x 2 conditions x R runs)."""

    skill_name: str
    skill_path: str
    # One evaluation round: the same traversal-free component the sandboxes are
    # keyed by, so a report can be traced back to the runs that produced it.
    eval_id: str = ""
    model: str
    judge_model: str = ""
    harness: str = "opencode"
    # UTC ISO-8601 with explicit offset, second resolution
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    tasks: list[Task] = Field(default_factory=list)
    runs: list[RunRecord] = Field(default_factory=list)
    runs_per_task: int = 1
    leakage_check: str = ""
    deltas: list[TaskDelta] = Field(default_factory=list)
    trigger_rate: float | None = None  # share of with-runs where the skill tool fired
    mean_tc_delta: float | None = None
    mean_if_delta: float | None = None
    std_tc_delta: float | None = None
    std_if_delta: float | None = None
    verdicts: list[str] = Field(default_factory=list)  # SKILL_EFFECTIVE / SKILL_REDUNDANT / ...
    # Non-empty when the judge model shares a family with the tested model — the
    # scores may be self-referential. Set by the evaluator, echoed in both reports.
    judge_circularity: str = ""
    total_cost: float | None = None
    total_duration_s: float = 0.0
