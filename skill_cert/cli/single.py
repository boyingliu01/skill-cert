"""Single evaluation mode — parse, maintainability, testgen, execute."""

import time
from pathlib import Path


def _setup_single_mode(args, config):
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
    }
    print(f"  Maintainability Score: {maintainability.total_score:.1f}/100 (Grade: {maintainability.grade})")
    print(f"  Readability: {maintainability.readability_score:.1f}")
    print(f"  Completeness: {maintainability.completeness_score:.1f}")
    print(f"  Freshness: {maintainability.freshness_score:.1f}")
    if maintainability.grade in ("D", "F"):
        print("  WARNING: Low maintainability score — SKILL.md needs improvement.")

    if not config.models:
        print("\nERROR: No models configured. Use --models, SKILL_CERT_MODELS env, or ~/.skill-cert/models.yaml")
        return None, None, None, None, None, None

    adapters = {mc.model_name: _create_adapter(mc, config.rate_limit_rpm) for mc in config.models}
    print(f"\n  Models: {', '.join(adapters.keys())}")

    _print_phase(1, "Generate Eval Tests")
    generator = EvalGenerator()
    primary_adapter = list(adapters.values())[0]
    review_adapter = list(adapters.values())[1] if len(adapters) > 1 else primary_adapter
    evals = generator.generate_evals_with_convergence(spec, primary_adapter, review_adapter)
    total_evals = sum(len(evals.get(k, [])) for k in ("eval_cases", "evals", "cases", "test_cases", "evaluations", "eval"))
    print(f"  Generated: {total_evals} eval cases")
    if generator._calculate_coverage(evals, spec) < generator.coverage_threshold:
        print(f"  WARNING: Coverage below {generator.coverage_threshold * 100:.0f}% threshold")

    _print_phase(2, "Execute Evals")
    return spec_path, output_dir, skill_name, spec, evals, adapters


def run_single_mode(args, config) -> int:
    # Lazy import so test patches at skill_cert.cli._run_single_phase intercept.
    from skill_cert.cli import EXIT_ERROR, _run_single_phase  # noqa: F811

    result = _setup_single_mode(args, config)
    spec_path, output_dir, skill_name, spec, evals, adapters = result
    if spec_path is None:
        return EXIT_ERROR
    spec["evals"] = evals
    return _run_single_phase(args, config, spec_path, output_dir, skill_name, spec, adapters)
