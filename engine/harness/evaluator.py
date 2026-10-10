"""Double-run orchestration for harness-based skill evaluation.

Pipeline (P0 Harness MVP):
  Phase 0  security scan (reuse SecurityScanner — BLOCK aborts)
  Phase 1  parse SKILL.md (reuse analyzer — name/description/content feed prompts)
  Phase 2  task generation (TaskGenerator, LLM structured output)
  Phase 3  double runs: task x {with_skill, without_skill} x R, isolated sandboxes
  Phase 4  LLM-judge every run (trajectory summary + skill definition as input)
  Phase 5  aggregate deltas, trigger rate, verdicts -> HarnessEvalReport
"""

from __future__ import annotations

import logging
import shutil
import statistics
import time
from pathlib import Path
from typing import Any

from engine.analyzer import parse_skill_md
from engine.security_probes import SecurityScanner

from .judge import HarnessJudge
from .models import (
    Condition,
    HarnessEvalReport,
    JudgeResult,
    RunRecord,
    Task,
    TaskDelta,
    TaskGenResult,
)
from .taskgen import TaskGenerator
from .util import safe_path_component

logger = logging.getLogger(__name__)

CONDITIONS: tuple[Condition, ...] = ("with_skill", "without_skill")


class SecurityBlockedError(RuntimeError):
    """Phase 0 security scan returned BLOCK — evaluation aborted."""


# ---------- pure scoring functions (unit-tested) ----------


def dimension_score(task: Task, judge: JudgeResult | None, dimension: str) -> float | None:
    """Weighted rubric score normalized to 0-100.

    Missing judge items count as 0 (conservative); a dimension without rubric
    items yields None (not measurable).
    """
    if judge is None:
        return None
    items = getattr(task.rubrics, dimension)
    if not items:
        return None
    scores = judge.score_map()
    total_points = sum(item.points for item in items)
    earned = sum(scores.get(item.id, 0.0) * item.points for item in items)
    return earned / total_points * 10.0


def condition_mean(
    task: Task, records: list[RunRecord], condition: str, dimension: str
) -> float | None:
    """Mean dimension score over one condition's runs of a task."""
    values = [
        score
        for rec in records
        if rec.task_id == task.id and rec.condition == condition
        if (score := dimension_score(task, rec.judge, dimension)) is not None
    ]
    return statistics.mean(values) if values else None


def _pair_delta(task: Task, records: list[RunRecord], dimension: str) -> float | None:
    with_mean = condition_mean(task, records, "with_skill", dimension)
    without_mean = condition_mean(task, records, "without_skill", dimension)
    if with_mean is None or without_mean is None:
        return None
    return with_mean - without_mean


def compute_deltas(tasks: list[Task], records: list[RunRecord]) -> list[TaskDelta]:
    """Per-task delta = mean(with) - mean(without) per dimension."""
    return [
        TaskDelta(
            task_id=task.id,
            task_completion_delta=_pair_delta(task, records, "task_completion"),
            instruction_following_delta=_pair_delta(task, records, "instruction_following"),
        )
        for task in tasks
    ]


def compute_trigger_rate(records: list[RunRecord]) -> float | None:
    """Share of with-runs where the native skill tool fired (real L1)."""
    with_runs = [r for r in records if r.condition == "with_skill"]
    if not with_runs:
        return None
    return sum(1 for r in with_runs if r.skill_loaded) / len(with_runs)


def compute_verdicts(
    mean_if_delta: float | None,
    mean_tc_delta: float | None,
    trigger_rate: float | None,
) -> list[str]:
    """MVP decision rules — advisory hints only, no hard PASS/FAIL."""
    verdicts: list[str] = []
    if mean_if_delta is not None and mean_if_delta >= 5:
        verdicts.append("SKILL_EFFECTIVE")
    if (
        mean_if_delta is not None
        and abs(mean_if_delta) < 3
        and mean_tc_delta is not None
        and mean_tc_delta < 3
    ):
        verdicts.append("SKILL_REDUNDANT")
    if trigger_rate is not None and trigger_rate < 0.5:
        verdicts.append("TRIGGER_WEAK")
    return verdicts


def _mean_std(values: list[float]) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    return statistics.mean(values), (statistics.pstdev(values) if len(values) > 1 else 0.0)


# ---------- orchestrator ----------


class HarnessEvaluator:
    """Orchestrates the double-run harness evaluation pipeline."""

    def __init__(
        self,
        harness: Any,  # HarnessAdapter (structural protocol, adapters layer)
        llm_adapter: Any,  # used for taskgen + judge
        output_dir: Path,
        runs: int = 1,
        keep_sandboxes: bool = False,
        judge_model_name: str = "",
        harness_label: str = "opencode",
    ):
        self.harness = harness
        self.taskgen = TaskGenerator(llm_adapter)
        self.judge = HarnessJudge(llm_adapter)
        self.output_dir = Path(output_dir)
        self.runs = max(1, runs)
        self.keep_sandboxes = keep_sandboxes
        self.judge_model_name = judge_model_name
        self.harness_label = harness_label
        self.sandbox_root = self.output_dir / ".harness-runs"

    def evaluate(
        self,
        skill_path: Path,
        n_tasks: int = 6,
        model_label: str = "",
    ) -> HarnessEvalReport:
        skill_path = Path(skill_path)
        skill_content = skill_path.read_text(encoding="utf-8", errors="replace")

        # Phase 1 — parse SKILL.md (name/description feed the prompts)
        spec = parse_skill_md(str(skill_path))
        skill_name = str(spec.get("name") or skill_path.parent.name)
        description = str(spec.get("description") or "")

        # Phase 0 — security scan (BLOCK aborts)
        scan = SecurityScanner().scan(skill_content, skill_name=skill_name)
        if scan.verdict == "BLOCK":
            raise SecurityBlockedError(
                f"security scan BLOCK for '{skill_name}' — evaluation aborted"
            )
        if scan.verdict == "WARN":
            logger.warning("security scan WARN for '%s' — proceeding", skill_name)

        # Phase 2 — task generation
        gen: TaskGenResult = self.taskgen.generate(skill_name, description, skill_content, n_tasks)
        logger.info(
            "generated %d tasks (leakage_check: %s)", len(gen.tasks), gen.leakage_check[:80]
        )

        # Phase 3 + 4 — double runs, each judged immediately
        # eval_id feeds sandbox paths and the harness session title: keep it one
        # traversal-free path component
        eval_id = f"{safe_path_component(skill_name)}-{time.strftime('%Y%m%d-%H%M%S')}"
        records: list[RunRecord] = []
        skill_dir = skill_path.parent
        try:
            for task in gen.tasks:
                for condition in CONDITIONS:
                    for run_index in range(self.runs):
                        record = self._run_once(task, condition, run_index, skill_dir, eval_id)
                        record.judge = self._judge_run(record, task, skill_name, skill_content)
                        records.append(record)
                        status = "ok" if record.error is None else f"ERR: {record.error[:60]}"
                        logger.info(
                            "run %s/%s/r%d -> %s", task.id, condition, run_index + 1, status
                        )
        finally:
            if not self.keep_sandboxes:
                shutil.rmtree(self.sandbox_root / eval_id, ignore_errors=True)

        # Phase 5 — aggregate
        return self._aggregate(
            tasks=gen.tasks,
            records=records,
            skill_name=skill_name,
            skill_path=str(skill_path),
            model_label=model_label,
            leakage_check=gen.leakage_check,
        )

    # -- Phase 3 -------------------------------------------------------------

    def _run_once(
        self,
        task: Task,
        condition: Condition,
        run_index: int,
        skill_dir: Path,
        eval_id: str,
    ) -> RunRecord:
        # task.id is LLM-authored — sanitize before it becomes a path component
        run_id = f"{eval_id}/{safe_path_component(task.id)}-{condition}-r{run_index + 1}"
        sandbox = self.sandbox_root / run_id
        if sandbox.exists():
            shutil.rmtree(sandbox)
        sandbox.mkdir(parents=True)

        self.harness.title = f"skill-cert/{eval_id}/{condition}"
        try:
            self.harness.prepare(sandbox, skill_dir if condition == "with_skill" else None)
            for input_file in task.input_files:
                self._write_input_file(sandbox, input_file.path, input_file.content)
            result = self.harness.run_task(task.description, sandbox)
            tool_sequence = [
                str((ev.get("part") or {}).get("tool") or "?")
                for ev in result.events
                if ev.get("type") == "tool_use"
            ]
            return RunRecord(
                task_id=task.id,
                condition=condition,
                run_index=run_index,
                session_id=result.session_id,
                final_output=result.final_output,
                skill_loaded=result.skill_loaded,
                tool_call_count=result.tool_call_count,
                tool_sequence=tool_sequence,
                tokens_in=result.tokens_in,
                tokens_out=result.tokens_out,
                cost=result.cost,
                duration_s=result.duration_s,
                error=result.error,
            )
        finally:
            # the eval-id directory itself is dropped once in evaluate()
            if not self.keep_sandboxes:
                shutil.rmtree(sandbox, ignore_errors=True)

    @staticmethod
    def _write_input_file(sandbox: Path, rel_path: str, content: str) -> None:
        """Write an input file into the sandbox, rejecting path traversal."""
        target = (sandbox / rel_path).resolve()
        if not target.is_relative_to(sandbox.resolve()):
            logger.warning("input file escapes sandbox, skipped: %s", rel_path)
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    # -- Phase 4 -------------------------------------------------------------

    def _judge_run(
        self, record: RunRecord, task: Task, skill_name: str, skill_content: str
    ) -> JudgeResult | None:
        try:
            return self.judge.judge(
                task=task,
                skill_name=skill_name,
                skill_content=skill_content,
                final_output=record.final_output,
                trajectory_summary=self._trajectory_summary(record),
            )
        except Exception as e:  # judge failure must not abort the whole evaluation
            logger.warning("judge failed for %s/%s: %s", record.task_id, record.condition, e)
            return None

    @staticmethod
    def _trajectory_summary(record: RunRecord) -> str:
        tools = " → ".join(record.tool_sequence) if record.tool_sequence else "(none)"
        lines = [
            f"tool_call_count: {record.tool_call_count}",
            f"tool_sequence: {tools}",
            f"skill_loaded: {record.skill_loaded}",
            f"tokens_in: {record.tokens_in}, tokens_out: {record.tokens_out}",
            f"duration_s: {record.duration_s:.1f}",
        ]
        if record.error:
            lines.append(f"error: {record.error}")
        return "\n".join(lines)

    # -- Phase 5 -------------------------------------------------------------

    def _aggregate(
        self,
        tasks: list[Task],
        records: list[RunRecord],
        skill_name: str,
        skill_path: str,
        model_label: str,
        leakage_check: str,
    ) -> HarnessEvalReport:
        deltas = compute_deltas(tasks, records)
        tc_values = [d.task_completion_delta for d in deltas if d.task_completion_delta is not None]
        if_values = [
            d.instruction_following_delta
            for d in deltas
            if d.instruction_following_delta is not None
        ]
        mean_tc, std_tc = _mean_std(tc_values)
        mean_if, std_if = _mean_std(if_values)
        trigger = compute_trigger_rate(records)
        costs = [r.cost for r in records if r.cost is not None]

        return HarnessEvalReport(
            skill_name=skill_name,
            skill_path=skill_path,
            model=model_label,
            judge_model=self.judge_model_name,
            harness=self.harness_label,
            tasks=tasks,
            runs=records,
            runs_per_task=self.runs,
            leakage_check=leakage_check,
            deltas=deltas,
            trigger_rate=trigger,
            mean_tc_delta=mean_tc,
            mean_if_delta=mean_if,
            std_tc_delta=std_tc,
            std_if_delta=std_if,
            verdicts=compute_verdicts(mean_if, mean_tc, trigger),
            total_cost=sum(costs) if costs else None,
            total_duration_s=sum(r.duration_s for r in records),
        )
