"""'skill-cert harness' subcommand — real-harness skill evaluation.

Runs a skill through a real coding-agent harness (opencode, native progressive
disclosure): N tasks x with/without skill x R repetitions, LLM-judged on
task-completion and instruction-following, reported as deltas.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _positive_int(value: str) -> int:
    """argparse type: reject 0/negatives instead of silently running an empty plan."""
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected an integer, got '{value}'") from None
    if parsed < 1:
        raise argparse.ArgumentTypeError(f"must be >= 1, got {parsed}")
    return parsed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skill-cert harness",
        description="Evaluate a SKILL.md on a real coding-agent harness (double-run delta).",
    )
    parser.add_argument("--skill", required=True, help="Path to SKILL.md")
    parser.add_argument("--harness", choices=["opencode", "dsh"], default="opencode")
    parser.add_argument(
        "--model",
        required=True,
        help="Harness model in provider/model form, e.g. deepseek/deepseek-chat",
    )
    parser.add_argument(
        "--judge-model",
        help="Configured model name for taskgen/judge (default: first configured model)",
    )
    parser.add_argument(
        "--tasks", type=_positive_int, default=6, help="Number of tasks (default: 6)"
    )
    parser.add_argument(
        "--runs", type=_positive_int, default=1, help="Repetitions per condition (default: 1)"
    )
    parser.add_argument("--output", default="./results", help="Output directory")
    parser.add_argument(
        "--serve", action="store_true", help="Reuse a persistent 'opencode serve' instance"
    )
    parser.add_argument(
        "--keep-sandboxes", action="store_true", help="Keep run sandboxes for debugging"
    )
    parser.add_argument(
        "--task-timeout",
        type=_positive_int,
        default=600,
        help="Per-run timeout in seconds (default: 600)",
    )
    return parser


def _resolve_judge(judge_model: str | None):
    """Pick the taskgen/judge model from skill-cert config (setup / models.yaml)."""
    from engine.config import SkillCertConfig
    from skill_cert.cli.helpers import _create_adapter

    config = SkillCertConfig.load()
    if not config.models:
        raise RuntimeError(
            "No LLM configured for task generation / judging — run 'skill-cert setup' first"
        )
    if judge_model:
        chosen = next((m for m in config.models if m.model_name == judge_model), None)
        if chosen is None:
            names = ", ".join(m.model_name for m in config.models)
            raise RuntimeError(f"--judge-model '{judge_model}' not configured (available: {names})")
    else:
        chosen = config.models[0]
    return _create_adapter(chosen), chosen.model_name


def _warn_circularity(model: str, judge_model: str) -> None:
    """Warn (never block) when judge shares a model family with the tested model.

    Heuristic on purpose: the judge name is matched as configured, so the same
    underlying model under two provider prefixes (``openai/gpt-4`` vs an azure
    deployment) is not detected here.
    """
    from engine.runner import infer_model_family

    tested = model.split("/", 1)[-1]
    if infer_model_family(tested) == infer_model_family(judge_model):
        print(
            f"WARNING: judge model '{judge_model}' is in the same family as the tested "
            f"model '{tested}' — circularity risk (proceeding anyway)",
            file=sys.stderr,
        )


def _fmt(value: float | None) -> str:
    return f"{value:+.1f}" if value is not None else "n/a"


def _handle_harness(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv[1:])

    from engine.harness.evaluator import HarnessEvaluator
    from engine.harness.report import write_report
    from skill_cert.cli.helpers import EXIT_ERROR

    try:
        skill_path = Path(args.skill).resolve()
        if not skill_path.is_file():
            raise FileNotFoundError(f"SKILL.md not found: {skill_path}")

        if args.harness == "dsh":
            print(
                "ERROR: dsh harness is not implemented yet (developer preview, no stable "
                "headless CLI) — use --harness opencode with a deepseek model instead.",
                file=sys.stderr,
            )
            return EXIT_ERROR

        from adapters.harness import OpenCodeHarness

        llm_adapter, judge_name = _resolve_judge(args.judge_model)
        _warn_circularity(args.model, judge_name)

        harness = OpenCodeHarness(model=args.model, timeout_s=args.task_timeout, serve=args.serve)
        evaluator = HarnessEvaluator(
            harness=harness,
            llm_adapter=llm_adapter,
            output_dir=Path(args.output),
            runs=args.runs,
            keep_sandboxes=args.keep_sandboxes,
            judge_model_name=judge_name,
        )
        print(f"[harness] skill={skill_path.name} backend=opencode model={args.model}")
        print(f"[harness] judge={judge_name} tasks={args.tasks} runs={args.runs}")
        report = evaluator.evaluate(skill_path, n_tasks=args.tasks, model_label=args.model)
        md_path, json_path = write_report(report, Path(args.output))

        trigger = f"{report.trigger_rate:.0%}" if report.trigger_rate is not None else "n/a"
        print()
        print(f"[harness] report: {md_path}")
        print(f"[harness] data:   {json_path}")
        print(
            f"[harness] deltas: IF={_fmt(report.mean_if_delta)} "
            f"TC={_fmt(report.mean_tc_delta)} | trigger rate: {trigger}"
        )
        for verdict in report.verdicts:
            print(f"[harness] verdict: {verdict}")
        return 0
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return EXIT_ERROR
    except Exception as e:
        import traceback

        # the stack is diagnostic output — it belongs on stderr, next to the
        # one-line summary, so `2>/dev/null` silences both and `| tee` keeps both
        traceback.print_exc(file=sys.stderr)
        print(f"ERROR: {e}", file=sys.stderr)
        return EXIT_ERROR
