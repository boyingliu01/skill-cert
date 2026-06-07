"""Single evaluation mode — parse, maintainability, testgen, execute."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _setup_single_mode(args, config, deadline=None):
    # Lazy imports — use skill_cert.cli namespace so test patches intercept.
    from skill_cert.cli import (  # noqa: F811
        EvalGenerator,
        MaintainabilityScorer,
        _create_adapter,
        _print_phase,
        parse_skill_md,
    )

    spec_path = args.skill
    if isinstance(spec_path, list):
        spec_path = spec_path[0]
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

    _print_phase(0, "Maintainability Assessment")
    scorer = MaintainabilityScorer()
    maintainability = scorer.score_file(spec_path)
    spec["maintainability"] = {
        "total_score": maintainability.total_score,
        "grade": maintainability.grade,
        "readability_score": maintainability.readability_score,
        "completeness_score": maintainability.completeness_score,
        "freshness_score": maintainability.freshness_score,
        "readability_details": maintainability.readability_details,
        "completeness_details": maintainability.completeness_details,
        "freshness_details": maintainability.freshness_details,
    }
    print(
        f"  Maintainability Score: {maintainability.total_score:.1f}/100 "
        f"(Grade: {maintainability.grade})"
    )
    print(f"  Readability: {maintainability.readability_score:.1f}")
    print(f"  Completeness: {maintainability.completeness_score:.1f}")
    print(f"  Freshness: {maintainability.freshness_score:.1f}")
    if maintainability.grade in ("D", "F"):
        print("  WARNING: Low maintainability score — SKILL.md needs improvement.")

    if not config.models:
        print(
            "\nERROR: No models configured. "
            "Use --models, SKILL_CERT_MODELS env, or ~/.skill-cert/models.yaml"
        )
        return None, None, None, None, None, None

    adapters = {mc.model_name: _create_adapter(mc, config.rate_limit_rpm) for mc in config.models}
    print(f"\n  Models: {', '.join(adapters.keys())}")

    _print_phase(1, "Generate Eval Tests")
    generator = EvalGenerator()
    primary_adapter = list(adapters.values())[0]
    review_adapter = list(adapters.values())[1] if len(adapters) > 1 else primary_adapter
    evals = generator.generate_evals_with_convergence(
        spec, primary_adapter, review_adapter, deadline=deadline
    )
    total_evals = sum(
        len(evals.get(k, []))
        for k in ("eval_cases", "evals", "cases", "test_cases", "evaluations", "eval")
    )
    print(f"  Generated: {total_evals} eval cases")

    coverage = generator._calculate_coverage(evals, spec)
    evals["_coverage"] = coverage
    if coverage < generator.coverage_threshold:
        print(f"  WARNING: Coverage below {generator.coverage_threshold * 100:.0f}% threshold")

    # REQ-017: Fail-fast on low coverage
    result = generator.check_coverage_or_abort(coverage)
    if result in (generator.CoverageResult.BLOCKED, generator.CoverageResult.FAILED):
        print(
            f"\n  FAIL-FAST: Coverage {coverage:.2f} below block threshold "
            f"({generator.block_threshold}). Aborting."
        )
        return spec_path, output_dir, skill_name, spec, evals, adapters

    _print_phase(2, "Execute Evals")
    return spec_path, output_dir, skill_name, spec, evals, adapters


def _generate_fail_fast_report(
    args,
    spec_path: Path,
    output_dir: Path,
    skill_name: str,
    spec: dict,
    coverage: float,
) -> dict[str, Any]:
    """Generate a minimal FAIL verdict report when coverage is too low."""
    from engine.reporter import Reporter

    fail_metrics = {
        "overall_score": 0.0,
        "l1_trigger_accuracy": 0.0,
        "l2_with_without_skill_delta": 0.0,
        "l3_step_adherence": 0.0,
        "l4_execution_stability": 0.0,
    }
    drift_report = {
        "drift_detected": False,
        "highest_severity": "none",
        "overall_verdict": "FAIL",
    }
    config_dict = {
        "skill_name": skill_name,
        "models": ["fail-fast-aborted"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_evaluations": 0,
        "avg_pass_rate": 0.0,
    }

    reporter = Reporter()
    md_report, json_report = reporter.generate_report(
        metrics=fail_metrics,
        drift=drift_report,
        config=config_dict,
    )

    # Override verdict to FAIL with coverage explanation
    json_report["verdict"] = "FAIL"
    json_report["fail_fast"] = True
    json_report["coverage_at_abort"] = coverage
    json_report["fail_reason"] = (
        f"Coverage {coverage:.2f} below block threshold (0.5). Evaluation aborted in Phase 1."
    )

    format_flag = getattr(args, "format", "both")
    if format_flag in ("markdown", "both"):
        md_path = output_dir / f"{skill_name}-report.md"
        md_report = md_report.replace(
            "## Executive Summary",
            "## FAIL-FAST: Evaluation Aborted\n\n"
            f"**Coverage**: {coverage:.2f} (threshold: 0.5)\n\n"
            f"**Reason**: Coverage below block threshold. "
            "Phase 2 (execution) skipped.\n\n"
            "## Executive Summary",
        )
        md_path.write_text(md_report, encoding="utf-8")
        print(f"  Markdown: {md_path}")

    if format_flag in ("json", "both"):
        json_path = output_dir / f"{skill_name}-result.json"
        json_path.write_text(
            json.dumps(json_report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"  JSON: {json_path}")

    return json_report


def run_single_mode(args, config) -> int:
    # Lazy import so test patches at skill_cert.cli._run_single_phase intercept.
    from engine.deadline import Deadline
    from skill_cert.cli import EXIT_ERROR, EXIT_PASS, _run_single_phase  # noqa: F811

    deadline = (
        Deadline(max_total_time=float(config.max_total_time))
        if config.max_total_time and config.max_total_time > 0
        else None
    )

    result = _setup_single_mode(args, config, deadline=deadline)
    spec_path, output_dir, skill_name, spec, evals, adapters = result
    if spec_path is None or spec is None:
        return EXIT_ERROR
    spec["evals"] = evals

    # REQ-017: Fail-fast on low coverage
    if evals.get("failed"):
        coverage = evals.get("_coverage", 0.0)
        json_report = _generate_fail_fast_report(
            args,
            Path(spec_path) if isinstance(spec_path, str) else spec_path,
            output_dir,
            skill_name,
            spec,
            coverage,
        )
        print(f"\n  Verdict: {json_report.get('verdict', 'FAIL')}")
        return EXIT_ERROR

    # Degraded mode — run Phase 2 but mark metrics for verdict cap
    if evals.get("degraded"):
        print("  Phase 2 running in degraded mode (coverage below target)")

    return _run_single_phase(
        args, config, spec_path, output_dir, skill_name, spec, adapters, deadline=deadline
    )
