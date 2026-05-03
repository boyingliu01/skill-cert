"""CLI entry point for skill-cert — AI Skill Evaluation Engine."""

import argparse
import asyncio
import sys
import time
from pathlib import Path

from engine.analyzer import parse_skill_md
from engine.config import SkillCertConfig, ModelConfig
from engine.testgen import EvalGenerator
from engine.runner import EvalRunner
from engine.grader import Grader
from engine.metrics import MetricsCalculator
from engine.drift import DriftDetector
from engine.reporter import Reporter
from engine.dialogue_runner import DialogueRunner
from engine.dialogue_evaluator import DialogueEvaluator
from engine.simulator import UserSimulator
from engine.replay import HistoryReplay
from adapters.openai_compat import OpenAICompatAdapter
from adapters.anthropic_compat import AnthropicCompatAdapter


EXIT_PASS = 0
EXIT_ERROR = 1
EXIT_FAIL_WITH_CAVEATS = 2


def _create_adapter(model_config: ModelConfig, rpm_limit: int = 60):
    if "anthropic" in model_config.base_url.lower() or model_config.model_name in AnthropicCompatAdapter.SUPPORTED_MODELS:
        return AnthropicCompatAdapter(
            base_url=model_config.base_url,
            api_key=model_config.api_key,
            model=model_config.model_name,
            fallback_model=model_config.fallback_model,
            rpm_limit=rpm_limit,
        )
    return OpenAICompatAdapter(
        base_url=model_config.base_url,
        api_key=model_config.api_key,
        model=model_config.model_name,
        fallback_model=model_config.fallback_model,
        rpm_limit=rpm_limit,
    )


def _print_phase(phase: int, name: str) -> None:
    print(f"\n{'='*60}")
    print(f"  Phase {phase}: {name}")
    print(f"{'='*60}")


def _print_metric(label: str, value: float, threshold: float | None = None) -> None:
    pct = f"{value * 100:.1f}%"
    if threshold is not None:
        status = "✓" if value >= threshold else "✗"
        print(f"  {label}: {pct} (threshold: {threshold * 100:.0f}%) {status}")
    else:
        print(f"  {label}: {pct}")


def _run_eval_for_model(model_name, adapter, runner, grader, evals, spec_path):
    with_skill = asyncio.run(runner.run_with_skill(evals, spec_path, adapter))
    without_skill = asyncio.run(runner.run_without_skill(evals, adapter))
    eval_cases = evals.get("eval_cases", evals.get("cases", []))
    graded = []
    for r in with_skill:
        if "error" not in r:
            case = next((e for e in eval_cases if e.get("id") == r.get("eval_id")), None)
            graded.append({**r, "grade": grader.grade_output(case, r.get("output", "")), "mode": "with_skill"})
    for r in without_skill:
        if "error" not in r:
            case = next((e for e in eval_cases if e.get("id") == r.get("eval_id")), None)
            graded.append({**r, "grade": grader.grade_output(case, r.get("output", "")), "mode": "without_skill"})
    ws_passed = sum(1 for r in graded if r["mode"] == "with_skill" and r.get("grade", {}).get("passed"))
    wos_passed = sum(1 for r in graded if r["mode"] == "without_skill" and r.get("grade", {}).get("passed"))
    return graded, ws_passed, wos_passed


def _run_all_evals(adapters, runner, grader, evals, spec_path):
    all_results = []
    for name, adapter in adapters.items():
        print(f"\n  Model: {name}")
        graded, ws, wos = _run_eval_for_model(name, adapter, runner, grader, evals, spec_path)
        all_results.extend(graded)
        print(f"    With-skill passed: {ws}")
        print(f"    Without-skill passed: {wos}")
    return all_results


def _run_single_phase(args, config: SkillCertConfig, spec_path, output_dir, skill_name, spec, adapters) -> int:
    runner = EvalRunner(max_concurrency=config.max_concurrency, rate_limit_rpm=config.rate_limit_rpm, request_timeout=config.request_timeout)
    primary_adapter = list(adapters.values())[0]
    grader = Grader(llm_client=primary_adapter)

    all_results = _run_all_evals(adapters, runner, grader, spec["evals"], spec_path)
    runner.close()

    _print_phase(3, "Calculate Metrics")
    calc = MetricsCalculator()
    metrics = calc.calculate_metrics(all_results)
    _print_metric("L1 Trigger Accuracy", metrics.get("l1", 0), 0.9)
    _print_metric("L2 Output Delta", metrics.get("l2", 0), 0.2)
    _print_metric("L3 Step Adherence", metrics.get("l3", 0), 0.85)
    l4_val = metrics.get("l4", 0)
    l4_pass = metrics.get("l4_stability_pass", True)
    print(f"  L4 Stability: {l4_val * 100:.1f}% (std≤10%) {'✓' if l4_pass else '✗'}")
    print(f"  Overall: {metrics.get('overall', 0) * 100:.1f}%")

    _print_phase(4, "Drift Detection")
    drift_report = None
    if len(adapters) > 1:
        detector = DriftDetector()
        drift_results = detector.detect_drift(spec["evals"].get("eval_cases", spec["evals"].get("cases", [])), adapters, grader)
        drift_report = detector.aggregate_drift_report(drift_results)
        print(f"  Highest severity: {drift_report.get('highest_severity', 'none')}")
        print(f"  Average variance: {drift_report.get('average_variance', 0):.3f}")
    else:
        print("  Skipped (single model)")

    _print_phase(5, "Generate Report")
    reporter = Reporter()
    report = reporter.generate_report(metrics=metrics, drift=drift_report, config=config.model_dump())

    md_path = output_dir / f"{skill_name}-report.md"
    json_path = output_dir / f"{skill_name}-result.json"
    md_path.write_text(report["markdown"], encoding="utf-8")
    json_path.write_text(report["json"], encoding="utf-8")
    print(f"  Markdown: {md_path}")
    print(f"  JSON: {json_path}")

    evals_cache = output_dir / f"{skill_name}-evals-cache.json"
    evals_cache.write_text(json.dumps(spec["evals"], indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Evals cache: {evals_cache}")

    verdict = report.get("verdict", "FAIL")
    print(f"\n  Verdict: {verdict}")
    if verdict == "PASS":
        return EXIT_PASS
    if verdict == "PASS_WITH_CAVEATS":
        return EXIT_FAIL_WITH_CAVEATS
    return EXIT_ERROR


def _setup_single_mode(args, config: SkillCertConfig):
    spec_path = args.skill
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    skill_name = Path(spec_path).stem

    _print_phase(0, "Parse SKILL.md")
    print(f"  File: {spec_path}")
    start = time.time()
    spec = parse_skill_md(spec_path)
    elapsed = time.time() - start
    print(f"  Name: {spec['name']}")
    print(f"  Parse method: {spec['parse_method']}")
    print(f"  Parse confidence: {spec['parse_confidence']:.2f}")
    print(f"  Workflow steps: {len(spec['workflow_steps'])}")
    print(f"  Anti-patterns: {len(spec['anti_patterns'])}")
    print(f"  Output format fields: {len(spec['output_format'])}")
    print(f"  Triggers: {len(spec['triggers'])}")
    print(f"  Elapsed: {elapsed:.2f}s")

    if spec["parse_confidence"] < 0.6:
        print("  WARNING: Low parse confidence. Results may be unreliable.")

    if not config.models:
        print("\nERROR: No models configured. Use --models, SKILL_CERT_MODELS env, or ~/.skill-cert/models.yaml")
        return None, None, None, None, None

    adapters = {mc.model_name: _create_adapter(mc, config.rate_limit_rpm) for mc in config.models}
    print(f"\n  Models: {', '.join(adapters.keys())}")

    _print_phase(1, "Generate Eval Tests")
    generator = EvalGenerator()
    primary_adapter = list(adapters.values())[0]
    review_adapter = list(adapters.values())[1] if len(adapters) > 1 else primary_adapter
    evals = generator.generate_evals_with_convergence(spec, primary_adapter, review_adapter)
    total_evals = sum(len(evals.get(k, [])) for k in ("eval_cases", "cases", "test_cases", "evaluations", "eval"))
    print(f"  Generated: {total_evals} eval cases")
    if generator._calculate_coverage(evals, spec) < generator.coverage_threshold:
        print(f"  WARNING: Coverage below {generator.coverage_threshold * 100:.0f}% threshold")

    _print_phase(2, "Execute Evals")
    return spec_path, output_dir, skill_name, spec, evals


def run_single_mode(args, config: SkillCertConfig) -> int:
    result = _setup_single_mode(args, config)
    spec_path, output_dir, skill_name, spec, evals = result
    if spec_path is None:
        return EXIT_ERROR
    spec["evals"] = evals
    return _run_single_phase(args, config, spec_path, output_dir, skill_name, spec, {mc.model_name: _create_adapter(mc, config.rate_limit_rpm) for mc in config.models})


def run_dialogue_mode(args, config: SkillCertConfig) -> int:
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

    _print_phase(1, "Dialogue Evaluation")
    print(f"  Max turns: {max_turns}")

    runner = EvalRunner(max_concurrency=config.max_concurrency, rate_limit_rpm=config.rate_limit_rpm)
    evaluator = DialogueEvaluator(judge_callback=primary_adapter)
    simulator = UserSimulator(model_adapter=primary_adapter, skill_spec=spec)

    dialogue_runner = DialogueRunner(
        simulator=simulator,
        evaluator=evaluator,
        skill_runner=runner,
        max_turns=max_turns,
    )

    results = asyncio.run(dialogue_runner.run(spec_path))
    runner.close()

    print(f"  Completed turns: {results.get('turns_completed', 0)}")
    print(f"  Verdict: {results.get('verdict', 'N/A')}")

    import json
    result_path = output_dir / f"{skill_name}-dialogue-result.json"
    result_path.write_text(json.dumps(results, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    print(f"  Results: {result_path}")

    return EXIT_PASS if results.get("verdict") == "PASS" else EXIT_ERROR


def run_replay_mode(args, config: SkillCertConfig) -> int:
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

    runner = EvalRunner(max_concurrency=config.max_concurrency, rate_limit_rpm=config.rate_limit_rpm)
    grader = Grader(llm_client=primary_adapter)
    replay = HistoryReplay(skill_runner=runner)

    messages = replay.load_session(session_path)
    print(f"  Loaded {len(messages)} messages")

    results = asyncio.run(replay.replay_session(messages, spec_path, grader))
    runner.close()

    import json
    result_path = output_dir / f"{skill_name}-replay-result.json"
    result_path.write_text(json.dumps(results, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    print(f"  Results: {result_path}")

    return EXIT_PASS


def main():
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
    parser.add_argument("--skill", required=True, help="Path to SKILL.md file")
    parser.add_argument("--models", default="", help="Models: 'name=url,key[,fallback]|name2=url,key'")
    parser.add_argument("--output", default="./results", help="Output directory (default: ./results)")
    parser.add_argument("--mode", choices=["single", "dialogue", "replay"], default="single", help="Evaluation mode (default: single)")
    parser.add_argument("--max-turns", type=int, default=10, help="Max turns for dialogue mode (default: 10)")
    parser.add_argument("--session", help="Session JSONL file for replay mode")
    parser.add_argument("--max-concurrency", type=int, help="Max concurrent requests")
    parser.add_argument("--rate-limit-rpm", type=int, help="Rate limit (requests per minute)")
    parser.add_argument("--request-timeout", type=int, help="Request timeout in seconds")
    parser.add_argument("--max-total-time", type=int, default=3600, help="Global timeout in seconds")

    args = parser.parse_args()

    try:
        config = SkillCertConfig.load(args)
    except Exception as e:
        print(f"ERROR: Invalid configuration: {e}", file=sys.stderr)
        return EXIT_ERROR

    try:
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


if __name__ == "__main__":
    sys.exit(main())
