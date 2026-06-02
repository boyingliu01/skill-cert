"""CLI entry point for skill-cert — AI Skill Evaluation Engine.

Thin re-export wrapper for backward compatibility.
All implementation lives in skill_cert/cli/ package.
"""

import sys

from skill_cert.cli import (  # noqa: F401
    EXIT_ERROR,
    EXIT_FAIL_WITH_CAVEATS,
    EXIT_PASS,
    _create_adapter,
    _print_metric,
    _print_phase,
    _run_all_evals,
    _run_eval_for_model,
    _run_single_phase,
    _setup_single_mode,
    main,
    run_dialogue_mode,
    run_multi_skill_mode,
    run_replay_mode,
    run_single_mode,
    run_stress_mode,
)

if __name__ == "__main__":
    sys.exit(main())
