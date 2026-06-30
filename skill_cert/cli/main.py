"""CLI entry point — argument parsing and mode dispatch."""

import argparse
import sys
from importlib.metadata import version as get_version


def _handle_setup(argv: list[str]) -> int:
    """Handle 'skill-cert setup' subcommand.

    Parses setup-specific arguments and delegates to run_setup().
    Supports both interactive (no flags) and non-interactive modes.
    """
    from skill_cert.cli.setup import run_setup

    setup_parser = argparse.ArgumentParser(
        prog="skill-cert setup",
        description="Configure LLM models for skill-cert evaluation.",
    )
    setup_parser.add_argument("--model-name", help="Model name (non-interactive mode)")
    setup_parser.add_argument("--base-url", default="", help="API base URL (non-interactive mode)")
    setup_parser.add_argument("--api-key", default="", help="API key (non-interactive mode)")
    setup_parser.add_argument("--fallback-model", default="", help="Fallback model name")
    setup_parser.add_argument("--skip-test", action="store_true", help="Skip connectivity test")

    setup_args = setup_parser.parse_args(argv[1:])  # skip 'setup'
    return run_setup(setup_args)


def _build_argument_parser() -> argparse.ArgumentParser:
    """Build and configure the argument parser."""

    from engine.constants import (  # noqa: F811
        ConcurrencyLimits,
        StabilityThresholds,
        TimingLimits,
        TokenLimits,
    )

    parser = argparse.ArgumentParser(
        description="Skill-Cert: AI Skill Evaluation Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Subcommands:
  setup                          Configure LLM models interactively

Examples:
  skill-cert setup
  skill-cert setup --model-name qwen3.6-plus --base-url https://api.example.com/v1 --api-key $KEY
  skill-cert --skill path/to/SKILL.md --models "claude=https://api.openai.com/v1,$KEY"
  skill-cert --skill path/to/SKILL.md --mode dialogue --max-turns 10
  skill-cert --skill path/to/SKILL.md --mode replay --session session.jsonl
  skill-cert --skill path/to/SKILL.md --models "m1=url,key|m2=url,key" --output ./results/
""",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"skill-cert {get_version('skill-cert')}",
    )
    parser.add_argument(
        "--skill",
        required=True,
        action="append",
        help="Path to SKILL.md file (can be repeated for --multi-skill)",
    )
    parser.add_argument(
        "--models",
        default="",
        help="Models: 'name=url,key[,fallback]|name2=url,key'",
    )
    parser.add_argument(
        "--output",
        default="./results",
        help="Output directory (default: ./results)",
    )
    parser.add_argument(
        "--mode",
        choices=["single", "dialogue", "replay"],
        default="single",
        help="Evaluation mode (default: single)",
    )
    parser.add_argument(
        "--multi-skill",
        action="store_true",
        help="Enable multi-skill conflict analysis (requires --skill repeated)",
    )
    parser.add_argument(
        "--token-budget",
        type=int,
        default=TokenLimits.DEFAULT_TOKEN_BUDGET,
        help=f"Token budget for multi-skill analysis (default: {TokenLimits.DEFAULT_TOKEN_BUDGET})",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=10,
        help="Max turns for dialogue mode (default: 10)",
    )
    parser.add_argument("--session", help="Session JSONL file for replay mode")
    parser.add_argument("--max-concurrency", type=int, help="Max concurrent requests")
    parser.add_argument("--rate-limit-rpm", type=int, help="Rate limit (requests per minute)")
    parser.add_argument("--request-timeout", type=int, help="Request timeout in seconds")
    parser.add_argument(
        "--max-total-time",
        type=int,
        default=TimingLimits.GLOBAL_TIMEOUT,
        help=f"Global timeout in seconds (default: {TimingLimits.GLOBAL_TIMEOUT})",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=StabilityThresholds.DEFAULT_RUNS,
        help=(
            f"Number of evaluation runs for stability (default: {StabilityThresholds.DEFAULT_RUNS})"
        ),
    )
    parser.add_argument(
        "--stress",
        action="store_true",
        help="Run scalability stress test",
    )
    parser.add_argument(
        "--stress-concurrency",
        type=int,
        default=ConcurrencyLimits.DEFAULT_STRESS_CONCURRENCY,
        help=(
            f"Concurrency for stress test (default: {ConcurrencyLimits.DEFAULT_STRESS_CONCURRENCY})"
        ),
    )
    parser.add_argument(
        "--stress-evals",
        type=int,
        default=ConcurrencyLimits.DEFAULT_STRESS_EVALS,
        help=f"Number of evals for stress test (default: {ConcurrencyLimits.DEFAULT_STRESS_EVALS})",
    )
    # Schema & integration flags (REQ-P0-002, REQ-P0-004)
    parser.add_argument(
        "--strict-schema",
        action="store_true",
        help="Reject SKILL.md if required fields are missing (default: warning only)",
    )
    parser.add_argument(
        "--with-skill-lab",
        action="store_true",
        help="Enable SkillLab integration for external evaluation",
    )
    parser.add_argument(
        "--with-deepeval",
        action="store_true",
        help="Enable DeepEval integration for additional metrics",
    )
    parser.add_argument(
        "--deep-security",
        action="store_true",
        default=False,
        help="Enable deep security scan via Giskard (requires giskard installation)",
    )
    parser.add_argument(
        "--envelope",
        help="Custom envelope thresholds as JSON (e.g. '{\"max_steps\": 30}')",
    )
    # Observability & structured report (Phase 2 & 3)
    parser.add_argument(
        "--trace-export",
        choices=["jsonl", "otlp", "none"],
        default="jsonl",
        help="Trace export format (default: jsonl)",
    )
    parser.add_argument(
        "--trace-dir",
        help="Directory for trace output (default: same as --output)",
    )
    parser.add_argument(
        "--otlp-endpoint",
        help="OTLP endpoint URL (requires --trace-export otlp)",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json", "both"],
        default="both",
        help="Report output format (default: both)",
    )
    parser.add_argument(
        "--json-schema-validate",
        action="store_true",
        help="Validate JSON report against schema",
    )
    parser.add_argument(
        "--debias-position",
        type=lambda x: x.lower() not in ("false", "0", "no"),
        default=True,
        help=(
            "Enable position debiasing for LLM-as-Judge (default: true, set false to save 2x cost)"
        ),
    )
    parser.add_argument(
        "--calibration-set",
        help="Path to golden eval set JSON for calibration analysis",
    )
    parser.add_argument(
        "--ci-history",
        type=lambda x: x.lower() not in ("false", "0", "no"),
        default=True,
        help=(
            "Enable CI history for L4 stability (default: true, set false to disable)"
        ),
    )
    parser.add_argument(
        "--ci-history-path",
        default=".skill-cert-ci-history.json",
        help="Path to CI history file (default: .skill-cert-ci-history.json)",
    )
    parser.add_argument(
        "--judge-samples",
        type=int,
        default=3,
        help="Number of LLM judge calls per eval for majority voting (default: 3)",
    )
    parser.add_argument(
        "--no-llm-judge",
        action="store_true",
        help="Skip all LLM-as-Judge calls, use deterministic assertions only",
    )

    return parser


def _dispatch_mode(args, config) -> int:
    """Dispatch to the appropriate evaluation mode."""
    from skill_cert.cli import (
        run_dialogue_mode,
        run_multi_skill_mode,
        run_replay_mode,
        run_single_mode,
        run_stress_mode,
    )

    if args.stress:
        return _run_with_error_handling(lambda: run_stress_mode(args, config))
    if args.multi_skill:
        return _run_with_error_handling(lambda: run_multi_skill_mode(args, config))
    mode_dispatch = {
        "dialogue": lambda: run_dialogue_mode(args, config),
        "replay": lambda: run_replay_mode(args, config),
    }
    return _run_with_error_handling(
        mode_dispatch.get(args.mode, lambda: run_single_mode(args, config))
    )


def _run_with_error_handling(func) -> int:
    """Run a mode function with standard error handling."""
    from skill_cert.cli import EXIT_ERROR

    try:
        return func()
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return EXIT_ERROR
    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"ERROR: {e}", file=sys.stderr)
        return EXIT_ERROR


def main():
    # Intercept 'setup' subcommand before standard argparse
    # (avoids 'error: the following arguments are required: --skill')
    if len(sys.argv) > 1 and sys.argv[1] == "setup":
        return _handle_setup(sys.argv[1:])

    # Lazy imports — use skill_cert.cli namespace so test patches intercept.
    from skill_cert.cli import EXIT_ERROR, SkillCertConfig

    parser = _build_argument_parser()
    args = parser.parse_args()

    try:
        config = SkillCertConfig.load(args)
    except Exception as e:
        print(f"ERROR: Invalid configuration: {e}", file=sys.stderr)
        return EXIT_ERROR

    return _dispatch_mode(args, config)
