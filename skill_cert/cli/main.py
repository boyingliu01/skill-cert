"""CLI entry point — argument parsing and mode dispatch."""

import argparse
import sys


def main():
    # Lazy imports — use skill_cert.cli namespace so test patches intercept.
    from engine.constants import (  # noqa: F811
        ConcurrencyLimits,
        StabilityThresholds,
        TimingLimits,
        TokenLimits,
    )
    from skill_cert.cli import (  # noqa: F811
        EXIT_ERROR,
        SkillCertConfig,
        run_dialogue_mode,
        run_multi_skill_mode,
        run_replay_mode,
        run_single_mode,
        run_stress_mode,
    )

    parser = argparse.ArgumentParser(
        description="Skill-Cert: AI Skill Evaluation Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  skill-cert --skill path/to/SKILL.md --models "claude=https://api.openai.com/v1,$KEY"
  skill-cert --skill path/to/SKILL.md --mode dialogue --max-turns 10
  skill-cert --skill path/to/SKILL.md --mode replay --session session.jsonl
  skill-cert --skill path/to/SKILL.md --models "m1=url,key|m2=url,key" --output ./results/
""",
    )
    parser.add_argument("--skill", required=True, action="append", help="Path to SKILL.md file (can be repeated for --multi-skill)")
    parser.add_argument("--models", default="", help="Models: 'name=url,key[,fallback]|name2=url,key'")
    parser.add_argument("--output", default="./results", help="Output directory (default: ./results)")
    parser.add_argument("--mode", choices=["single", "dialogue", "replay"], default="single", help="Evaluation mode (default: single)")
    parser.add_argument("--multi-skill", action="store_true", help="Enable multi-skill conflict analysis (requires --skill repeated)")
    parser.add_argument("--token-budget", type=int, default=TokenLimits.DEFAULT_TOKEN_BUDGET, help=f"Token budget for multi-skill analysis (default: {TokenLimits.DEFAULT_TOKEN_BUDGET})")
    parser.add_argument("--max-turns", type=int, default=10, help="Max turns for dialogue mode (default: 10)")
    parser.add_argument("--session", help="Session JSONL file for replay mode")
    parser.add_argument("--max-concurrency", type=int, help="Max concurrent requests")
    parser.add_argument("--rate-limit-rpm", type=int, help="Rate limit (requests per minute)")
    parser.add_argument("--request-timeout", type=int, help="Request timeout in seconds")
    parser.add_argument("--max-total-time", type=int, default=TimingLimits.GLOBAL_TIMEOUT, help=f"Global timeout in seconds (default: {TimingLimits.GLOBAL_TIMEOUT})")
    parser.add_argument("--runs", type=int, default=StabilityThresholds.DEFAULT_RUNS, help=f"Number of evaluation runs for stability (default: {StabilityThresholds.DEFAULT_RUNS})")
    parser.add_argument("--stress", action="store_true", help="Run scalability stress test")
    parser.add_argument("--stress-concurrency", type=int, default=ConcurrencyLimits.DEFAULT_STRESS_CONCURRENCY, help=f"Concurrency for stress test (default: {ConcurrencyLimits.DEFAULT_STRESS_CONCURRENCY})")
    parser.add_argument("--stress-evals", type=int, default=ConcurrencyLimits.DEFAULT_STRESS_EVALS, help=f"Number of evals for stress test (default: {ConcurrencyLimits.DEFAULT_STRESS_EVALS})")

    args = parser.parse_args()

    try:
        config = SkillCertConfig.load(args)
    except Exception as e:
        print(f"ERROR: Invalid configuration: {e}", file=sys.stderr)
        return EXIT_ERROR

    try:
        if args.stress:
            return run_stress_mode(args, config)
        if args.multi_skill:
            return run_multi_skill_mode(args, config)
        if args.mode == "dialogue":
            return run_dialogue_mode(args, config)
        elif args.mode == "replay":
            return run_replay_mode(args, config)
        else:
            return run_single_mode(args, config)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return EXIT_ERROR
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return EXIT_ERROR
