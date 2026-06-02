"""Stress test evaluation mode — concurrency and scalability testing."""

import asyncio
import json
from pathlib import Path

from .helpers import EXIT_ERROR, EXIT_PASS, _create_adapter, _print_phase


def run_stress_mode(args, config) -> int:
    # Lazy imports — use skill_cert.cli namespace so test patches intercept.
    from skill_cert.cli import StressTester, format_scalability_report, parse_skill_md  # noqa: F811

    spec_path = args.skill[0] if isinstance(args.skill, list) else args.skill
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    skill_name = Path(spec_path).stem

    _print_phase(0, "Parse SKILL.md")
    spec = parse_skill_md(spec_path)
    print(f"  Name: {spec['name']}, Confidence: {spec['parse_confidence']:.2f}")

    if not config.models:
        print("\nERROR: No models configured.")
        return EXIT_ERROR

    concurrency = args.stress_concurrency
    num_evals = args.stress_evals
    print(f"\n  Stress test: concurrency={concurrency}, evals={num_evals}")

    _print_phase(1, "Stress Test")
    stress_tester = StressTester(
        concurrency=concurrency,
        rate_limit_rpm=config.rate_limit_rpm,
        models=[mc.model_name for mc in config.models],
    )
    adapter = _create_adapter(config.models[0], config.rate_limit_rpm)

    eval_cases = [
        {"id": f"stress-{i}", "model": config.models[i % len(config.models)].model_name}
        for i in range(num_evals)
    ]

    stress_result = asyncio.run(
        stress_tester.run_stress_test(eval_cases, adapter, concurrency=concurrency)
    )

    report_text = format_scalability_report(stress_result)
    print(report_text)

    result_path = output_dir / f"{skill_name}-stress-result.json"
    result_data = {
        "total_evals": stress_result.total_evals,
        "completed": stress_result.completed,
        "failed": stress_result.failed,
        "timed_out": stress_result.timed_out,
        "errored": stress_result.errored,
        "completion_rate": stress_result.completion_rate,
        "fairness_ratio": stress_result.fairness_ratio,
        "scalability_score": stress_result.scalability_score,
        "verdict": stress_result.verdict,
        "latency": {
            "avg": stress_result.avg_latency,
            "min": stress_result.min_latency,
            "max": stress_result.max_latency,
            "median": stress_result.median_latency,
            "p95": stress_result.p95_latency,
            "p99": stress_result.p99_latency,
        },
        "memory_mb_peak": stress_result.memory_mb_peak,
        "model_exec_counts": stress_result.model_exec_counts,
    }
    result_path.write_text(json.dumps(result_data, indent=2), encoding="utf-8")
    print(f"  Results: {result_path}")

    stress_md_path = output_dir / f"{skill_name}-stress-report.md"
    stress_md_path.write_text(report_text, encoding="utf-8")
    print(f"  Report: {stress_md_path}")

    print(f"\n  Verdict: {stress_result.verdict}")
    return EXIT_PASS if stress_result.verdict == "PASS" else EXIT_ERROR
