"""Replay evaluation mode — regression testing with historical sessions."""

import asyncio
import json
from pathlib import Path

from .helpers import EXIT_ERROR, EXIT_PASS, _create_adapter, _print_phase


def run_replay_mode(args, config) -> int:
    # Lazy imports — use skill_cert.cli namespace so test patches intercept.
    from skill_cert.cli import EvalRunner, Grader, HistoryReplay, parse_skill_md  # noqa: F811

    spec_path = args.skill
    session_path = getattr(args, "session", None)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    skill_name = Path(spec_path).stem

    if not session_path:
        print("ERROR: --session required for replay mode")
        return EXIT_ERROR

    _print_phase(0, "Parse SKILL.md")
    spec = parse_skill_md(spec_path)
    print(f"  Name: {spec['name']}, Confidence: {spec['parse_confidence']:.2f}")

    if not config.models:
        print("\nERROR: No models configured.")
        return EXIT_ERROR

    primary_adapter = _create_adapter(config.models[0], config.rate_limit_rpm)

    _print_phase(1, "Replay Session")
    print(f"  Session: {session_path}")

    runner = EvalRunner(
        max_concurrency=config.max_concurrency, rate_limit_rpm=config.rate_limit_rpm
    )
    grader = Grader(llm_client=primary_adapter)
    replay = HistoryReplay(skill_runner=runner)

    messages = replay.load_session(session_path)
    print(f"  Loaded {len(messages)} messages")

    results = asyncio.run(replay.replay_session(messages, spec_path, grader))
    runner.close()

    result_path = output_dir / f"{skill_name}-replay-result.json"
    result_path.write_text(
        json.dumps(results, indent=2, default=str, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  Results: {result_path}")

    return EXIT_PASS
