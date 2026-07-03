"""Dialogue evaluation mode — multi-turn skill assessment."""

import asyncio
import json
from pathlib import Path

from engine.observability import CompositeLedger

from .helpers import EXIT_ERROR, EXIT_PASS, _create_adapter, _print_phase


def run_dialogue_mode(args, config) -> int:
    # Lazy imports — use skill_cert.cli namespace so test patches intercept.
    from skill_cert.cli import (  # noqa: F811
        DialogueEvaluator,
        DialogueRunner,
        EvalRunner,
        UserSimulator,
        parse_skill_md,
    )

    spec_path = args.skill
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    skill_name = Path(spec_path).stem
    max_turns = getattr(args, "max_turns", 10) or 10

    _print_phase(0, "Parse SKILL.md")
    spec = parse_skill_md(spec_path)
    print(f"  Name: {spec['name']}, Confidence: {spec['parse_confidence']:.2f}")

    if not config.models:
        print("\nERROR: No models configured.")
        return EXIT_ERROR

    primary_adapter = _create_adapter(config.models[0], config.rate_limit_rpm)
    # Initialize CompositeLedger for SessionTelemetry
    try:
        from engine.token_ledger import TokenLedger

        ledger = TokenLedger()
        composite_ledger = CompositeLedger(ledger=ledger)
        session_telemetry = composite_ledger.session_telemetry
    except Exception as e:
        print(f"  WARNING: Failed to initialize telemetry: {e}")
        session_telemetry = None

    _print_phase(1, "Dialogue Evaluation")
    print(f"  Max turns: {max_turns}")

    runner = EvalRunner(
        max_concurrency=config.max_concurrency, rate_limit_rpm=config.rate_limit_rpm
    )
    evaluator = DialogueEvaluator(judge_callback=primary_adapter.chat)  # type: ignore[arg-type]
    simulator = UserSimulator()

    dialogue_runner = DialogueRunner(
        simulator=simulator,
        evaluator=evaluator,
        skill_runner=runner,
        max_turns=max_turns,
        telemetry=session_telemetry,
    )

    results = asyncio.run(
        dialogue_runner.run_dialogue_eval({"id": "dialogue_eval"}, str(spec_path))
    )
    runner.close()

    print(f"  Completed turns: {results.get('turns_completed', 0)}")
    print(f"  Verdict: {results.get('verdict', 'N/A')}")

    result_path = output_dir / f"{skill_name}-dialogue-result.json"
    result_path.write_text(
        json.dumps(results, indent=2, default=str, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  Results: {result_path}")

    return EXIT_PASS if results.get("verdict") == "PASS" else EXIT_ERROR
