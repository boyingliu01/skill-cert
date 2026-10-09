"""Markdown + JSON report rendering for harness evaluations."""

from __future__ import annotations

import json
from pathlib import Path

from .evaluator import condition_mean
from .models import HarnessEvalReport


def _fmt(value: float | None, digits: int = 1) -> str:
    return f"{value:.{digits}f}" if value is not None else "n/a"


def _fmt_pct(value: float | None) -> str:
    return f"{value * 100:.0f}%" if value is not None else "n/a"


def _cell(text: str) -> str:
    """Make a string safe for a Markdown table cell."""
    return text.replace("|", "/").replace("\n", " ")


def render_report(report: HarnessEvalReport) -> str:
    lines: list[str] = []
    add = lines.append

    add(f"# Harness Evaluation Report — {report.skill_name}")
    add("")
    add(f"Generated: {report.generated_at}")
    add("")
    add("| | |")
    add("|---|---|")
    add(f"| Skill | `{_cell(report.skill_path)}` |")
    add(f"| Harness / Model | `{report.harness}` / `{report.model}` |")
    add(f"| Judge model | `{report.judge_model or '(unspecified)'}` |")
    add(f"| Scale | {len(report.tasks)} tasks × 2 conditions × {report.runs_per_task} runs |")
    add("")

    add("## Verdicts")
    add("")
    if report.verdicts:
        for verdict in report.verdicts:
            add(f"- **{verdict}**")
    else:
        add("- (no verdict triggered)")
    add("")
    add(
        "_Advisory only (MVP rules): IF delta >= +5 -> SKILL_EFFECTIVE; "
        "|IF delta| < 3 and TC delta < 3 -> SKILL_REDUNDANT; "
        "trigger rate < 50% -> TRIGGER_WEAK._"
    )
    add("")

    add("## Summary")
    add("")
    add("| Metric | Value |")
    add("|---|---|")
    add(
        f"| Instruction-following delta (mean ± std) | "
        f"{_fmt(report.mean_if_delta)} ± {_fmt(report.std_if_delta)} |"
    )
    add(
        f"| Task-completion delta (mean ± std) | "
        f"{_fmt(report.mean_tc_delta)} ± {_fmt(report.std_tc_delta)} |"
    )
    add(f"| Skill trigger rate (with-runs) | {_fmt_pct(report.trigger_rate)} |")
    add(f"| Total cost (harness-reported) | {_fmt(report.total_cost, 4)} |")
    add(f"| Total duration | {report.total_duration_s:.0f}s |")
    add("")

    add("## Per-task deltas")
    add("")
    add("| Task | TC with | TC without | TC delta | IF with | IF without | IF delta |")
    add("|---|---|---|---|---|---|---|")
    delta_by_id = {d.task_id: d for d in report.deltas}
    for task in report.tasks:
        delta = delta_by_id.get(task.id)
        tc_w = condition_mean(task, report.runs, "with_skill", "task_completion")
        tc_wo = condition_mean(task, report.runs, "without_skill", "task_completion")
        if_w = condition_mean(task, report.runs, "with_skill", "instruction_following")
        if_wo = condition_mean(task, report.runs, "without_skill", "instruction_following")
        tc_d = delta.task_completion_delta if delta else None
        if_d = delta.instruction_following_delta if delta else None
        sign = lambda v: "n/a" if v is None else f"{v:+.1f}"  # noqa: E731
        add(
            f"| {task.id} | {_fmt(tc_w)} | {_fmt(tc_wo)} | {sign(tc_d)} "
            f"| {_fmt(if_w)} | {_fmt(if_wo)} | {sign(if_d)} |"
        )
    add("")

    add("## Run details")
    add("")
    add(
        "| Task | Condition | Run | Skill loaded | Tools | Tokens in/out "
        "| Cost | Duration | Error |"
    )
    add("|---|---|---|---|---|---|---|---|---|")
    for rec in report.runs:
        tools = " -> ".join(rec.tool_sequence) if rec.tool_sequence else "-"
        tokens_in = "-" if rec.tokens_in is None else str(rec.tokens_in)
        tokens_out = "-" if rec.tokens_out is None else str(rec.tokens_out)
        add(
            f"| {rec.task_id} | {rec.condition} | {rec.run_index + 1} "
            f"| {'yes' if rec.skill_loaded else 'no'} | {_cell(tools)} "
            f"| {tokens_in}/{tokens_out} | {_fmt(rec.cost, 4)} "
            f"| {rec.duration_s:.0f}s | {_cell(rec.error or '')} |"
        )
    add("")

    add("## Task-generation leakage self-check")
    add("")
    add(f"> {_cell(report.leakage_check or '(not provided)')}")
    add("")
    return "\n".join(lines)


def write_report(report: HarnessEvalReport, output_dir: Path) -> tuple[Path, Path]:
    """Write Markdown + JSON reports; returns (md_path, json_path)."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / f"{report.skill_name}-harness-report.md"
    json_path = output_dir / f"{report.skill_name}-harness-report.json"
    md_path.write_text(render_report(report), encoding="utf-8")
    json_path.write_text(
        json.dumps(report.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return md_path, json_path
