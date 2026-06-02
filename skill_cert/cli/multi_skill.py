"""Multi-skill conflict analysis mode."""

import json
from pathlib import Path

from .helpers import EXIT_ERROR, EXIT_PASS, _print_phase


def run_multi_skill_mode(args, config) -> int:
    # Lazy imports: parse_skill_md and Reporter go through skill_cert.cli
    # (for test patch compat). MultiSkillAnalyzer from engine directly.
    from engine.multi_skill import MultiSkillAnalyzer  # noqa: F811
    from skill_cert.cli import Reporter, parse_skill_md  # noqa: F811

    skill_paths = args.skill if isinstance(args.skill, list) else [args.skill]
    if len(skill_paths) < 2:
        print("\nERROR: --multi-skill requires at least 2 --skill arguments")
        return EXIT_ERROR

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    specs = []
    for sp in skill_paths:
        _print_phase(0, f"Parse SKILL.md: {Path(sp).name}")
        spec = parse_skill_md(sp)
        print(f"  Name: {spec['name']}, Confidence: {spec['parse_confidence']:.2f}")
        specs.append(spec)

    _print_phase(1, "Multi-Skill Conflict Analysis")
    analyzer = MultiSkillAnalyzer()
    analyzer.inject_multiple_skills(specs)
    report = analyzer.analyze(token_budget=args.token_budget)

    conflicts = report["conflicts"]
    print(f"  Skills analysed: {report['skill_count']}")
    print(f"  Total conflicts: {len(conflicts)}")
    print(f"  Trigger overlaps: {report['trigger_conflicts']}")
    print(f"  Prompt contamination: {report['prompt_contamination_conflicts']}")
    print(f"  Token overflow: {report['token_overflow_conflicts']}")
    print(f"  Overall risk: {report['overall_risk']}")

    if conflicts:
        for c in conflicts:
            print(f"    [{c.severity.value}] {c}")

    reporter = Reporter()
    md_report, json_report = reporter.generate_report_with_multi_skill(
        metrics={"overall_score": 1.0 if report["overall_risk"] == "none" else 0.5},
        drift={"drift_detected": False, "highest_severity": "none"},
        config={"total_evaluations": 0},
        multi_skill_report=report,
    )

    md_path = output_dir / "multi-skill-report.md"
    json_path = output_dir / "multi-skill-result.json"
    md_path.write_text(md_report, encoding="utf-8")
    json_path.write_text(json.dumps(json_report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\n  Markdown: {md_path}")
    print(f"  JSON: {json_path}")

    verdict = "PASS" if report["overall_risk"] in ("none", "low") else "FAIL"
    print(f"\n  Verdict: {verdict}")
    return EXIT_PASS if verdict == "PASS" else EXIT_ERROR
