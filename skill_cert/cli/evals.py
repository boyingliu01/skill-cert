"""Eval orchestration functions for single-mode pipeline."""

import json
import logging
from pathlib import Path

from engine.constants import StabilityThresholds, VerdictThresholds
from engine.grader import EvalAssertion, EvalCase
from engine.token_ledger import TokenLedger

from .helpers import EXIT_ERROR, EXIT_FAIL_WITH_CAVEATS, EXIT_PASS, _print_metric, _print_phase

logger = logging.getLogger(__name__)


def _run_eval_for_model(model_name, adapter, runner, grader, evals, spec_path, tracker=None):
    eval_cases_list = evals if isinstance(evals, list) else (
        evals.get("eval_cases") or evals.get("evals") or evals.get("cases") or evals.get("test_cases") or []
    )
    with_skill = runner.run_with_skill(eval_cases_list, spec_path, adapter)
    without_skill = runner.run_without_skill(eval_cases_list, adapter)

    if tracker:
        for r in with_skill:
            tracker.record_eval(
                r.get("eval_id"),
                r.get("error") is None,
                r.get("error"),
            )
        for r in without_skill:
            tracker.record_eval(
                r.get("eval_id"),
                r.get("error") is None,
                r.get("error"),
            )

    def _build_eval_case(case_dict):
        if hasattr(case_dict, 'prompt'):
            return case_dict
        assertions = []
        for a in case_dict.get("assertions", []):
            if isinstance(a, dict):
                w = a.get("weight", 1)
                assertions.append(EvalAssertion(
                    name=a.get("name", ""),
                    type=a.get("type", "contains"),
                    value=str(a.get("value", "")),
                    weight=int(float(w))
                ))
        prompt = case_dict.get("input") or case_dict.get("prompt", "")
        return EvalCase(
            id=case_dict.get("id", 0),
            name=case_dict.get("name", ""),
            category=case_dict.get("category", "normal"),
            prompt=prompt,
            assertions=assertions
        )

    case_map = {c.get("id"): _build_eval_case(c) for c in eval_cases_list}

    def _flatten_grade(result, grade, mode):
        return {
            **result,
            "grade": grade,
            "mode": mode,
            "skill_used": mode == "with_skill",
            "final_passed": grade.get("final_passed", False),
            "pass_rate": grade.get("pass_rate", 0.0),
            "total_weighted_score": grade.get("total_weighted_score", 0),
            "total_possible_score": grade.get("total_possible_score", 0),
            "category": result.get("eval_category", result.get("category", "")),
        }

    graded = []
    for r in with_skill:
        if not r.get("error"):
            case = case_map.get(r.get("eval_id"))
            if case:
                grade = grader.grade_output(case, r.get("output") or "")
                graded.append(_flatten_grade(r, grade, "with_skill"))
    for r in without_skill:
        if not r.get("error"):
            case = case_map.get(r.get("eval_id"))
            if case:
                grade = grader.grade_output(case, r.get("output") or "")
                graded.append(_flatten_grade(r, grade, "without_skill"))
    ws_passed = sum(1 for r in graded if r.get("mode") == "with_skill" and r.get("grade", {}).get("final_passed"))
    wos_passed = sum(1 for r in graded if r.get("mode") == "without_skill" and r.get("grade", {}).get("final_passed"))
    return graded, ws_passed, wos_passed


def _run_all_evals(adapters, runner, grader, evals, spec_path, tracker=None):
    # Lazy import so test patches at skill_cert.cli._run_eval_for_model intercept.
    from skill_cert.cli import _run_eval_for_model  # noqa: F811

    all_results = []
    for name, adapter in adapters.items():
        print(f"\n  Model: {name}")
        graded, ws, wos = _run_eval_for_model(name, adapter, runner, grader, evals, spec_path, tracker)
        all_results.extend(graded)
        print(f"    With-skill passed: {ws}")
        print(f"    Without-skill passed: {wos}")
    return all_results


def _run_single_phase(args, config, spec_path, output_dir, skill_name, spec, adapters) -> int:
    # Lazy imports so test patches at skill_cert.cli.XXX intercept.
    from skill_cert.cli import (  # noqa: F811
        DriftDetector,
        EvalRunner,
        Grader,
        MetricsCalculator,
        ReliabilityTracker,
        Reporter,
        StabilityRunner,
        calculate_l4_stability,
    )

    # Create TokenLedger for per-eval token accounting
    token_ledger = TokenLedger()

    runner = EvalRunner(max_concurrency=config.max_concurrency, rate_limit_rpm=config.rate_limit_rpm, request_timeout=config.request_timeout, token_ledger=token_ledger)
    primary_adapter = list(adapters.values())[0]
    grader = Grader(llm_client=primary_adapter)
    tracker = ReliabilityTracker()

    all_results = _run_all_evals(adapters, runner, grader, spec["evals"], spec_path, tracker)
    runner.close()

    reliability_report = tracker.generate_report()
    _print_phase(4, "Reliability Analysis")
    print(f"  Success rate: {reliability_report['success_rate'] * 100:.1f}%")
    print(f"  Error rate: {reliability_report['error_rate'] * 100:.1f}%")
    if reliability_report["errors_by_category"]:
        for cat, count in reliability_report["errors_by_category"].items():
            print(f"    {cat}: {count}")
    if reliability_report["retry_stats"]["total_retries"] > 0:
        print(
            f"  Retries: avg={reliability_report['retry_stats']['avg_retries']:.2f}, max={reliability_report['retry_stats']['max_retries']}"
        )

    _print_phase(3, "Calculate Metrics")
    calc = MetricsCalculator()
    metrics = calc.calculate_metrics(all_results)

    num_runs = getattr(args, "runs", 1) or 1
    if num_runs > 1:
        _print_phase(4, f"Stability Analysis ({num_runs} runs)")
        eval_cases = spec["evals"].get("eval_cases", spec["evals"].get("cases", []))
        stab_runner = StabilityRunner(
            base_runner=EvalRunner(max_concurrency=config.max_concurrency, rate_limit_rpm=config.rate_limit_rpm),
            num_runs=num_runs, max_concurrency=config.max_concurrency
        )
        stability_data = stab_runner.run_stability(eval_cases, spec_path, primary_adapter, with_skill=True)
        l4_score = calculate_l4_stability(stability_data)
        metrics["l4_execution_stability"] = l4_score
        metrics["l4_stability_pass"] = l4_score >= StabilityThresholds.L4_PASS_THRESHOLD
        metrics["stability_data"] = stability_data
        print(f"  Runs: {num_runs}")
        print(f"  Mean pass rate: {stability_data['overall_mean_pass_rate']:.2f}")
        print(f"  Stability std: {stability_data['overall_std_dev']:.4f}, L4: {l4_score:.2f}")

    l7 = calc.calculate_l7_cost_efficiency(all_results)
    if l7:
        metrics["l7_cost_efficiency"] = l7

    metrics['reliability'] = reliability_report
    metrics['_results'] = all_results

    # Aggregate token data from traces via TokenLedger
    runner.close()  # flushes token_ledger
    all_traces = runner.get_traces()
    if all_traces:
        token_ledger.aggregate(all_traces)
    token_summary = token_ledger.get_summary()
    if token_summary["total_tokens"] > 0:
        metrics["token_analysis"] = token_summary
        _print_phase(4, "Token Analysis")
        print(f"  Total tokens: {token_summary['total_tokens']:,}")
        print(f"  Total cost: ${token_summary['total_cost']:.4f}")
        for phase, data in token_summary.get("by_phase", {}).items():
            print(f"  {phase}: {data['total_tokens']:,} tokens")

    _print_metric("L1 Trigger Accuracy", metrics.get("l1_trigger_accuracy", 0), VerdictThresholds.L1_MIN)
    _print_metric("L2 Output Delta", metrics.get("l2_with_without_skill_delta", 0), VerdictThresholds.L2_MIN)
    _print_metric("L3 Step Adherence", metrics.get("l3_step_adherence", 0), VerdictThresholds.L3_MIN)
    num_runs = getattr(args, "runs", 1) or 1
    if num_runs > 1:
        stability_d = metrics.get("stability_data", {})
        l4_val = metrics.get("l4_execution_stability", 0)
        l4_pass = metrics.get("l4_stability_pass", True)
        print(f"  L4 Stability: {l4_val * 100:.1f}% (std={stability_d.get('overall_std_dev', 0):.4f})")
    else:
        l4_val = metrics.get("l4_execution_stability", 0)
        l4_pass = True
    print(f"  L4 Execution Stability: {l4_val * 100:.1f}% (std<=10%) {'OK' if l4_pass else 'FAIL'}")
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
    md_report, json_report = reporter.generate_report(
        metrics=metrics, drift=drift_report, config=config.model_dump(),
        maintainability=spec.get("maintainability"),
    )

    # Build structured report (Phase 3)
    token_analysis = metrics.get("token_analysis")
    observability_data = {
        "trace_count": len(all_traces),
        "total_events": sum(len(t.events) for t in all_traces),
        "total_duration_ms": sum(t.duration_ms for t in all_traces),
        "total_tool_calls": sum(t.tool_call_count for t in all_traces),
        "trace_format": getattr(args, "trace_export", "jsonl"),
    } if all_traces else None

    structured_report = reporter.build_structured_report(
        metrics=metrics,
        drift=drift_report,
        config={"skill_name": skill_name, "skill_path": spec_path, "models": list(adapters.keys()), **config.model_dump()},
        maintainability=spec.get("maintainability"),
        token_analysis=token_analysis,
        observability=observability_data,
    )

    # Write reports based on --format
    report_format = getattr(args, "format", "both")
    md_path = output_dir / f"{skill_name}-report.md"
    json_path = output_dir / f"{skill_name}-result.json"

    if report_format in ("markdown", "both"):
        md_path.write_text(md_report, encoding="utf-8")
        print(f"  Markdown: {md_path}")

    if report_format in ("json", "both"):
        # Use structured report JSON if available
        json_str = reporter.generate_json_report(structured_report)
        json_path.write_text(json_str, encoding="utf-8")
        print(f"  JSON: {json_path}")

        # Optional schema validation
        if getattr(args, "json_schema_validate", False):
            import json as _json
            from pathlib import Path as _Path
            schema_path = _Path(__file__).parent.parent.parent / "schemas" / "report.schema.json"
            if schema_path.exists():
                schema = _json.loads(schema_path.read_text(encoding="utf-8"))
                # Use Pydantic for validation (no jsonschema dependency)
                from engine.report_models import StructuredReport as SR
                try:
                    SR.model_validate(_json.loads(json_str))
                    print("  Schema validation: PASS")
                except Exception as e:
                    print(f"  Schema validation: FAIL - {e}")

    evals_cache = output_dir / f"{skill_name}-evals-cache.json"
    evals_cache.write_text(json.dumps(spec["evals"], indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Evals cache: {evals_cache}")

    # Export traces as JSONL (for observability)
    trace_export = getattr(args, "trace_export", "jsonl")
    if trace_export != "none" and all_traces:
        trace_dir = Path(getattr(args, "trace_dir", None) or output_dir)
        trace_dir.mkdir(parents=True, exist_ok=True)
        traces_path = trace_dir / f"{skill_name}-traces.jsonl"
        with open(traces_path, "w", encoding="utf-8") as f:
            for trace in all_traces:
                f.write(trace.model_dump_json() + "\n")
        print(f"  Traces: {traces_path} ({len(all_traces)} traces)")

    verdict = json_report.get("verdict", "FAIL")
    print(f"\n  Verdict: {verdict}")
    if verdict == "PASS":
        return EXIT_PASS
    if verdict == "PASS_WITH_CAVEATS":
        return EXIT_FAIL_WITH_CAVEATS
    return EXIT_ERROR
