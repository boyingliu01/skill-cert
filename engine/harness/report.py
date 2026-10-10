"""Markdown + JSON report rendering for harness evaluations."""

from __future__ import annotations

import json
from pathlib import Path

from .evaluator import condition_mean
from .models import HarnessEvalReport
from .util import safe_path_component


def _fmt(value: float | None, digits: int = 1) -> str:
    return f"{value:.{digits}f}" if value is not None else "n/a"


def _fmt_pct(value: float | None) -> str:
    return f"{value * 100:.0f}%" if value is not None else "n/a"


def _fmt_delta(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.1f}"


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
    add(f"| Eval id | `{_cell(report.eval_id or '(not recorded)')}` |")
    add(f"| Harness / Model | `{report.harness}` / `{report.model}` |")
    add(f"| Judge model | `{report.judge_model or '(unspecified)'}` |")
    add(f"| Scale | {len(report.tasks)} tasks × 2 conditions × {report.runs_per_task} runs |")
    add("")

    add("## Verdicts (advisory)")
    add("")
    if report.verdicts:
        for verdict in report.verdicts:
            add(f"- **{verdict}**")
    else:
        add("- (no verdict triggered)")
    add("")
    add(
        f"_Quantities they were derived from: IF delta {_fmt_delta(report.mean_if_delta)}, "
        f"TC delta {_fmt_delta(report.mean_tc_delta)}, "
        f"trigger rate {_fmt_pct(report.trigger_rate)}._"
    )
    add(
        "_Advisory only (MVP rules): IF delta >= +5 -> SKILL_EFFECTIVE; "
        "|IF delta| < 3 and TC delta < 3 -> SKILL_REDUNDANT; "
        "trigger rate < 50% -> TRIGGER_WEAK. These thresholds are a recommendation, "
        "not a policy — nothing gates on them, and the same quantities are published "
        "per task below and in the JSON report so a reader can set its own bar._"
    )
    add("")
    if report.judge_circularity:
        add(f"> **Circularity warning:** {_cell(report.judge_circularity)}")
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
    add("| Task | TC with | TC without | TC delta | IF with | IF without | IF delta | Trigger |")
    add("|---|---|---|---|---|---|---|---|")
    delta_by_id = {d.task_id: d for d in report.deltas}
    for task in report.tasks:
        delta = delta_by_id.get(task.id)
        tc_w = condition_mean(task, report.runs, "with_skill", "task_completion")
        tc_wo = condition_mean(task, report.runs, "without_skill", "task_completion")
        if_w = condition_mean(task, report.runs, "with_skill", "instruction_following")
        if_wo = condition_mean(task, report.runs, "without_skill", "instruction_following")
        tc_d = delta.task_completion_delta if delta else None
        if_d = delta.instruction_following_delta if delta else None
        trig = delta.trigger_rate if delta else None
        add(
            f"| {task.id} | {_fmt(tc_w)} | {_fmt(tc_wo)} | {_fmt_delta(tc_d)} "
            f"| {_fmt(if_w)} | {_fmt(if_wo)} | {_fmt_delta(if_d)} | {_fmt_pct(trig)} |"
        )
    add("")

    add("## Run details")
    add("")
    add(
        "| Task | Condition | Run | Skill loaded | Tools | Tokens in/out "
        "| Cost | Duration | Skipped inputs | Error |"
    )
    add("|---|---|---|---|---|---|---|---|---|---|")
    for rec in report.runs:
        tools = " -> ".join(rec.tool_sequence) if rec.tool_sequence else "-"
        tokens_in = "-" if rec.tokens_in is None else str(rec.tokens_in)
        tokens_out = "-" if rec.tokens_out is None else str(rec.tokens_out)
        add(
            f"| {rec.task_id} | {rec.condition} | {rec.run_index + 1} "
            f"| {'yes' if rec.skill_loaded else 'no'} | {_cell(tools)} "
            f"| {tokens_in}/{tokens_out} | {_fmt(rec.cost, 4)} "
            f"| {rec.duration_s:.0f}s | {_cell(', '.join(rec.skipped_inputs) or '-')} "
            f"| {_cell(rec.error or '')} |"
        )
    add("")
    if any(rec.skipped_inputs for rec in report.runs):
        add(
            "_Skipped inputs are generated fixture files the sandbox escape check refused; "
            "those runs were judged without them._"
        )
        add("")

    add("## Task-generation leakage self-check")
    add("")
    add(f"> {_cell(report.leakage_check or '(not provided)')}")
    add("")
    return "\n".join(lines)


def write_report(
    report: HarnessEvalReport, output_dir: Path, keep_history: bool = False
) -> tuple[Path, Path]:
    """Write Markdown + JSON reports; returns (md_path, json_path).

    By default the pair lands at the deterministic ``{skill}-harness-report.*``
    path, so rerunning one skill can be diffed against the previous result —
    which means the previous result is overwritten. ``keep_history`` instead
    writes each run into its own ``{eval_id}/`` subdirectory (the default names
    are kept inside it); the run is always identifiable afterwards through the
    ``eval_id`` field of the JSON body.
    """
    output_dir = Path(output_dir)
    if keep_history:
        # eval_id is built by safe_path_component, but reports can be assembled
        # from other sources — re-sanitize rather than trust it.
        output_dir = output_dir / safe_path_component(report.eval_id or report.skill_name)
    output_dir.mkdir(parents=True, exist_ok=True)
    # skill_name comes from the SKILL.md frontmatter — never a raw filename
    stem = f"{safe_path_component(report.skill_name)}-harness-report"
    md_path = output_dir / f"{stem}.md"
    json_path = output_dir / f"{stem}.json"
    md_path.write_text(render_report(report), encoding="utf-8")
    json_path.write_text(
        json.dumps(report.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return md_path, json_path
