"""Eval orchestration functions for single-mode pipeline."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from engine.constants import StabilityThresholds, VerdictThresholds
from engine.deadline import PhaseTimer
from engine.grader import EvalAssertion, EvalCase
from engine.observability import SessionTelemetry
from engine.report_models import StructuredReport
from engine.token_ledger import TokenLedger

from .helpers import EXIT_ERROR, EXIT_FAIL_WITH_CAVEATS, EXIT_PASS, _print_metric, _print_phase

logger = logging.getLogger(__name__)


def _build_eval_case_from_dict(case_dict) -> EvalCase:
    """Build EvalCase from dict or return as-is if already EvalCase."""
    if hasattr(case_dict, "prompt"):
        return case_dict
    assertions = []
    for a in case_dict.get("assertions", []):
        if isinstance(a, dict):
            w = a.get("weight", 1)
            assertions.append(
                EvalAssertion(
                    name=a.get("name", ""),
                    type=a.get("type", "contains"),
                    value=str(a.get("value", "")),
                    weight=int(float(w)),
                )
            )
    prompt = case_dict.get("input") or case_dict.get("prompt", "")
    if not isinstance(prompt, str):
        prompt = json.dumps(prompt) if isinstance(prompt, (dict, list)) else str(prompt)
    ws_assertions = []
    for a in case_dict.get("without_skill_assertions", []):
        if isinstance(a, dict):
            w = a.get("weight", 1)
            ws_assertions.append(
                EvalAssertion(
                    name=a.get("name", ""),
                    type=a.get("type", "contains"),
                    value=str(a.get("value", "")),
                    weight=int(float(w)),
                )
            )
    return EvalCase(
        id=case_dict.get("id", 0),
        name=case_dict.get("name", ""),
        category=case_dict.get("category", "normal"),
        prompt=prompt,
        assertions=assertions,
        without_skill_assertions=ws_assertions,
        workflow_step=case_dict.get("workflow_step"),
        negative_case=bool(case_dict.get("negative_case", False)),
        assertion_strategy=case_dict.get("assertion_strategy", "deterministic"),
    )


def _flatten_grade_result(result, grade, mode) -> dict:
    """Flatten grade result with mode information."""
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
        "workflow_step": grade.get("workflow_step"),
        "negative_case": grade.get("negative_case", False),
    }


def _extract_eval_cases_list(evals) -> list:
    """Extract eval cases list from evals dict or return as-is."""
    if isinstance(evals, list):
        return evals
    return (
        evals.get("eval_cases")
        or evals.get("evals")
        or evals.get("cases")
        or evals.get("test_cases")
        or []
    )


def _track_reality_results(tracker, results) -> None:
    """Track results for reliability tracking."""
    if not tracker:
        return
    for r in results:
        tracker.record_eval(
            r.get("eval_id"),
            r.get("error") is None,
            r.get("error"),
        )


def _grade_single_result(case_map, grader, result, mode) -> dict | None:
    """Grade a single result, return None if error or no case."""
    if result.get("error"):
        return None
    case = case_map.get(result.get("eval_id"))
    if not case:
        return None
    grade = grader.grade_output(case, result.get("output") or "", mode=mode)
    return _flatten_grade_result(result, grade, mode)


def _count_passes(graded: list, mode: str) -> int:
    """Count passes for a given mode."""
    return sum(
        1 for r in graded if r.get("mode") == mode and r.get("grade", {}).get("final_passed")
    )


def _run_eval_for_model(
    model_name, adapter, runner, grader, evals, spec_path, tracker=None, deadline=None
):
    # Extract eval cases list
    eval_cases_list = _extract_eval_cases_list(evals)

    # Run with and without skill
    with_skill = runner.run_with_skill(eval_cases_list, spec_path, adapter, deadline=deadline)
    without_skill = runner.run_without_skill(eval_cases_list, adapter, deadline=deadline)

    # Track reliability if tracker provided
    _track_reality_results(tracker, with_skill)
    _track_reality_results(tracker, without_skill)

    # Build case map
    eval_cases = [_build_eval_case_from_dict(c) for c in eval_cases_list]
    case_map = {c.id: c for c in eval_cases}

    # Grade results in parallel for all evals (with + without skill)
    grade_futures = []
    with ThreadPoolExecutor(max_workers=runner.max_concurrency * 2) as grade_executor:
        for r in with_skill:
            if not r.get("error"):
                grade_futures.append(
                    grade_executor.submit(_grade_single_result, case_map, grader, r, "with_skill")
                )
        for r in without_skill:
            if not r.get("error"):
                grade_futures.append(
                    grade_executor.submit(_grade_single_result, case_map, grader, r, "without_skill")
                )

    graded = [f.result() for f in grade_futures if f.result() is not None]

    # Count passes
    ws_passed = _count_passes(graded, "with_skill")
    wos_passed = _count_passes(graded, "without_skill")

    return graded, ws_passed, wos_passed


def _run_all_evals(adapters, runner, grader, evals, spec_path, tracker=None, deadline=None):
    # Lazy import so test patches at skill_cert.cli._run_eval_for_model intercept.
    from skill_cert.cli import _run_eval_for_model  # noqa: F811

    timer = PhaseTimer(phase_name="evals", item_count=len(adapters), deadline=deadline)

    all_results = []
    for name, adapter in adapters.items():
        timer.items_completed = len(all_results)  # count completed before this model
        timer.log_progress(f"Model: {name}")
        print(f"\n  Model: {name}")
        graded, ws, wos = _run_eval_for_model(
            name, adapter, runner, grader, evals, spec_path, tracker, deadline=deadline
        )
        all_results.extend(graded)
        print(f"    With-skill passed: {ws}")
        print(f"    Without-skill passed: {wos}")
    return all_results


def _print_reliability_report(reliability_report: dict[str, Any]) -> None:
    """Print reliability analysis report."""
    _print_phase(4, "Reliability Analysis")
    print(f"  Success rate: {reliability_report['success_rate'] * 100:.1f}%")
    print(f"  Error rate: {reliability_report['error_rate'] * 100:.1f}%")
    if reliability_report["errors_by_category"]:
        for cat, count in reliability_report["errors_by_category"].items():
            print(f"    {cat}: {count}")
    if reliability_report["retry_stats"]["total_retries"] > 0:
        print(
            f"  Retries: avg={reliability_report['retry_stats']['avg_retries']:.2f}, "
            f"max={reliability_report['retry_stats']['max_retries']}"
        )


def _calculate_metrics_with_stability(
    all_results: list[dict[str, Any]], args, spec, spec_path, primary_adapter, config
) -> dict[str, Any]:
    """Calculate metrics including stability analysis if needed."""
    from skill_cert.cli import (  # noqa: F811
        EvalRunner,
        MetricsCalculator,
        StabilityRunner,
        calculate_l4_stability,
    )

    calc = MetricsCalculator()

    # Determine CI history path
    ci_history_enabled = getattr(args, "ci_history", True)
    ci_history_path = getattr(args, "ci_history_path", ".skill-cert-ci-history.json")
    if not ci_history_enabled:
        ci_history_path = None

    metrics = calc.calculate_metrics(all_results, ci_history_path=ci_history_path)

    num_runs = getattr(args, "runs", 1) or 1
    if num_runs > 1:
        _print_phase(4, f"Stability Analysis ({num_runs} runs)")
        _evals = spec["evals"]
        eval_cases: list[Any] = (
            (_evals.get("eval_cases") or _evals.get("cases") or [])
            if isinstance(_evals, dict)
            else []
        )
        stab_runner = StabilityRunner(
            base_runner=EvalRunner(
                max_concurrency=config.max_concurrency, rate_limit_rpm=config.rate_limit_rpm
            ),
            num_runs=num_runs,
            max_concurrency=config.max_concurrency,
        )
        stability_data = stab_runner.run_stability(
            eval_cases, spec_path, primary_adapter, with_skill=True
        )
        l4_score = calculate_l4_stability(stability_data)
        if l4_score is None:
            metrics["l4_execution_stability"] = None
            metrics["l4_stability_pass"] = False
            metrics["stability_data"] = stability_data
            print(
                f"  WARNING: L4 requires >= {StabilityThresholds.MIN_SAMPLES_FOR_L4} runs "
                f"({num_runs} provided). L4 set to None/unavailable."
            )
            print(f"  Runs: {num_runs}")
            print(f"  Mean pass rate: {stability_data['overall_mean_pass_rate']:.2f}")
            print(f"  Stability std: {stability_data['overall_std_dev']:.4f}, L4: unavailable")
        else:
            metrics["l4_execution_stability"] = l4_score
            metrics["l4_stability_pass"] = l4_score >= StabilityThresholds.L4_PASS_THRESHOLD
            metrics["stability_data"] = stability_data
            print(f"  Runs: {num_runs}")
            print(f"  Mean pass rate: {stability_data['overall_mean_pass_rate']:.2f}")
            print(f"  Stability std: {stability_data['overall_std_dev']:.4f}, L4: {l4_score:.2f}")

    l7 = calc.calculate_l7_cost_efficiency(all_results)
    if l7:
        metrics["l7_cost_efficiency"] = l7

    return metrics


def _aggregate_token_data(runner, token_ledger, metrics: dict[str, Any]) -> None:
    """Aggregate token data from traces and update metrics."""
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


def _print_metrics_summary(metrics: dict[str, Any], args) -> None:
    """Print metrics summary."""

    _print_metric(
        "L1 Trigger Accuracy",
        metrics.get("l1_trigger_accuracy", 0),
        VerdictThresholds.L1_MIN,
    )
    _print_metric(
        "L2 Output Delta",
        metrics.get("l2_with_without_skill_delta", 0),
        VerdictThresholds.L2_MIN,
    )
    _print_metric(
        "L3 Step Adherence",
        metrics.get("l3_step_adherence", 0),
        VerdictThresholds.L3_MIN,
    )
    num_runs = getattr(args, "runs", 1) or 1
    if num_runs > 1:
        stability_d = metrics.get("stability_data", {})
        l4_val = metrics.get("l4_execution_stability")
        l4_pass = metrics.get("l4_stability_pass", True)
        if l4_val is not None:
            print(
                f"  L4 Stability: {l4_val * 100:.1f}% (std={stability_d.get('overall_std_dev', 0):.4f})"
            )
        else:
            print(f"  L4 Stability: N/A (>= 5 runs required)")
    else:
        l4_val = metrics.get("l4_execution_stability")
        l4_pass = True
    if l4_val is not None:
        print(f"  L4 Execution Stability: {l4_val * 100:.1f}% (std<=10%) {'OK' if l4_pass else 'FAIL'}")
    else:
        print(f"  L4 Execution Stability: N/A (>= 5 runs required)")
    overall_val = metrics.get("overall")
    if overall_val is not None:
        print(f"  Overall: {overall_val * 100:.1f}%")
    else:
        print(f"  Overall: N/A")


def _detect_and_print_drift(spec, adapters, grader) -> dict[str, Any] | None:
    """Detect cross-model drift and print report."""
    from skill_cert.cli import DriftDetector

    _print_phase(4, "Drift Detection")
    if len(adapters) > 1:
        detector = DriftDetector()
        _evals = spec["evals"]
        drift_results = detector.detect_drift(
            (_evals.get("eval_cases") or _evals.get("cases") or [])
            if isinstance(_evals, dict)
            else [],
            adapters,
            grader,
        )
        drift_report = detector.aggregate_drift_report(drift_results)
        print(f"  Highest severity: {drift_report.get('highest_severity', 'none')}")
        print(f"  Average variance: {drift_report.get('average_variance', 0):.3f}")
        return drift_report
    print("  Skipped (single model)")
    return None


def _run_calibration(args, all_results) -> dict[str, Any] | None:
    """Run calibration analysis if --calibration-set is provided."""
    calibration_set_path = getattr(args, "calibration_set", None)
    if not calibration_set_path:
        return None

    from dataclasses import asdict

    from engine.calibration import CalibrationRunner, GoldenEvalSet

    _print_phase(4, "Calibration Analysis")
    try:
        cal_path = Path(calibration_set_path)
        if not cal_path.exists():
            print(f"  WARNING: Calibration set not found: {calibration_set_path}")
            return None

        raw_data = json.loads(cal_path.read_text(encoding="utf-8"))
        golden_set = GoldenEvalSet.from_dicts(raw_data)

        auto_results = [r.get("grade", {}).get("final_passed", False) for r in all_results]
        if len(auto_results) < len(golden_set):
            auto_results.extend([False] * (len(golden_set) - len(auto_results)))
        auto_results = auto_results[: len(golden_set)]

        runner = CalibrationRunner()
        report = runner.calibrate(golden_set, auto_results)
        cal_data = asdict(report)

        print(f"  Agreement rate: {cal_data['agreement_rate']:.2%}")
        print(f"  Cohen's kappa: {cal_data['cohens_kappa']:.4f}")
        print(
            f"  FPR: {cal_data['false_positive_rate']:.2%}, "
            f"FNR: {cal_data['false_negative_rate']:.2%}"
        )
        return cal_data
    except Exception as e:
        print(f"  WARNING: Calibration failed: {e}")
        return None


def _build_structured_report_context(
    metrics: dict[str, Any], args, all_traces: list, telemetry=None
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Build token and observability data for structured report."""
    token_analysis = metrics.get("token_analysis")
    observability_data = None

    # Prefer telemetry summary if available
    if telemetry is not None and hasattr(telemetry, "get_summary"):
        summary = telemetry.get_summary()
        observability_data = {
            "trace_count": summary.get("trace_count", 0),
            "total_events": summary.get("total_events", 0),
            "total_duration_ms": summary.get("total_duration_ms", 0),
            "total_tool_calls": summary.get("total_tool_calls", 0),
            "session_duration_s": summary.get("session_duration_s", 0),
            "export_path": summary.get("export_path"),
            "trace_format": summary.get("export_format", getattr(args, "trace_export", "jsonl")),
        }
    elif all_traces:
        observability_data = {
            "trace_count": len(all_traces),
            "total_events": sum(len(t.events) for t in all_traces),
            "total_duration_ms": sum(t.duration_ms for t in all_traces),
            "total_tool_calls": sum(t.tool_call_count for t in all_traces),
            "trace_format": getattr(args, "trace_export", "jsonl"),
        }

    return token_analysis, observability_data


def _write_markdown_report(
    output_dir: Path, skill_name: str, md_report: str, report_format: str
) -> Path | None:
    """Write markdown report if format allows. Return path if written."""
    if report_format not in ("markdown", "both"):
        return None

    md_path = output_dir / f"{skill_name}-report.md"
    md_path.write_text(md_report, encoding="utf-8")
    print(f"  Markdown: {md_path}")
    return md_path


def _write_json_report(
    args,
    output_dir: Path,
    skill_name: str,
    structured_report: StructuredReport,
    report_format: str,
) -> tuple[Path | None, str | None]:
    """Write JSON report if format allows. Return path and JSON string."""
    from skill_cert.cli import Reporter

    if report_format not in ("json", "both"):
        return None, None

    json_path = output_dir / f"{skill_name}-result.json"
    json_str = Reporter().generate_json_report(structured_report)
    json_path.write_text(json_str, encoding="utf-8")
    print(f"  JSON: {json_path}")

    # Optional schema validation
    if getattr(args, "json_schema_validate", False):
        import json as _json
        from pathlib import Path as _Path

        schema_path = _Path(__file__).parent.parent.parent / "schemas" / "report.schema.json"
        if schema_path.exists():
            try:
                StructuredReport.model_validate(_json.loads(json_str))
                print("  Schema validation: PASS")
            except Exception as e:
                print(f"  Schema validation: FAIL - {e}")

    return json_path, json_str


def _write_evals_cache(output_dir: Path, skill_name: str, spec_evals: dict) -> Path:
    """Write evals cache file."""
    evals_cache = output_dir / f"{skill_name}-evals-cache.json"
    evals_cache.write_text(json.dumps(spec_evals, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Evals cache: {evals_cache}")
    return evals_cache


def _export_traces(args, output_dir: Path, skill_name: str, all_traces: list) -> Path | None:
    """Export traces as JSONL if enabled. Return path if exported."""
    trace_export = getattr(args, "trace_export", "jsonl")
    if trace_export == "none" or not all_traces:
        return None

    trace_dir = Path(getattr(args, "trace_dir", None) or output_dir)
    trace_dir.mkdir(parents=True, exist_ok=True)
    traces_path = trace_dir / f"{skill_name}-traces.jsonl"
    with open(traces_path, "w", encoding="utf-8") as f:
        for trace in all_traces:
            f.write(trace.model_dump_json() + "\n")
    print(f"  Traces: {traces_path} ({len(all_traces)} traces)")
    return traces_path


def _append_to_ci_history(
    args, spec_path: str, metrics: dict[str, Any]
) -> None:
    """Append current run metrics to CI history file."""
    ci_history_enabled = getattr(args, "ci_history", True)
    if not ci_history_enabled:
        return

    from datetime import datetime, timezone

    ci_history_path = Path(getattr(args, "ci_history_path", ".skill-cert-ci-history.json"))

    # Load existing history or create new
    if ci_history_path.exists():
        try:
            data = json.loads(ci_history_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {"runs": []}
    else:
        data = {"runs": []}

    # Append current run
    run_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "skill_path": spec_path,
        "l1_trigger_accuracy": metrics.get("l1_trigger_accuracy"),
        "l2_with_without_skill_delta": metrics.get("l2_with_without_skill_delta"),
        "l3_step_adherence": metrics.get("l3_step_adherence"),
        "l4_execution_stability": metrics.get("l4_execution_stability"),
        "l5_step_efficiency": metrics.get("l5_step_efficiency"),
        "l6_trajectory_quality": metrics.get("l6_trajectory_quality"),
        "overall_score": metrics.get("overall_score"),
    }
    data["runs"].append(run_entry)

    # Write back
    ci_history_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _generate_and_write_reports(
    args,
    output_dir,
    skill_name,
    spec,
    spec_path,
    adapters,
    metrics,
    drift_report,
    config,
    telemetry=None,
    calibration_data=None,
) -> tuple[str, dict[str, Any]]:
    """Generate and write reports, return md_report and json_report."""
    from skill_cert.cli import Reporter

    _print_phase(5, "Generate Report")
    reporter = Reporter()
    md_report, json_report = reporter.generate_report(
        metrics=metrics,
        drift=drift_report,
        config=config.model_dump(),
        maintainability=spec.get("maintainability"),
    )

    # Build structured report
    token_analysis, observability_data = _build_structured_report_context(
        metrics,
        args,
        [],  # all_traces would come from runner.get_traces()
        telemetry,
    )

    # Add SessionTelemetry summary if available
    session_telemetry_summaries = None
    if telemetry is not None:
        summaries = telemetry.get_all_summaries()
        if summaries:
            session_telemetry_summaries = [s.model_dump() for s in summaries]

    structured_report = reporter.build_structured_report(
        metrics=metrics,
        drift=drift_report,
        config={
            "skill_name": skill_name,
            "skill_path": spec_path,
            **config.model_dump(),
            "models": list(adapters.keys()),
        },
        maintainability=spec.get("maintainability"),
        token_analysis=token_analysis,
        observability=observability_data,
        session_telemetry=session_telemetry_summaries,
        eval_results=metrics.get("_results"),
        calibration_data=calibration_data,
    )

    # Write reports based on --format
    report_format = getattr(args, "format", "both")
    _write_markdown_report(output_dir, skill_name, md_report, report_format)
    _write_json_report(args, output_dir, skill_name, structured_report, report_format)

    # Write evals cache
    _write_evals_cache(output_dir, skill_name, spec.get("evals") or {})

    # Export traces as JSONL
    _export_traces(args, output_dir, skill_name, [])  # all_traces would come from runner

    return md_report, json_report


def _build_integration_dispatcher(args: Any) -> Any:
    """Build IntegrationDispatcher from CLI args for pipeline connection."""
    try:
        from engine.integrations import (  # noqa: F811
            GiskardSecurityIntegration,
            IntegrationDispatcher,
        )
    except ImportError:
        return None
    dispatcher = IntegrationDispatcher()
    dispatcher.register(GiskardSecurityIntegration())
    # Promptfoo is the backup option (Node.js dependency), registered lazily
    return dispatcher


def _run_single_phase(
    args, config, spec_path, output_dir, skill_name, spec, adapters, deadline=None
) -> int:
    # Lazy imports so test patches at skill_cert.cli.XXX intercept.
    from skill_cert.cli import (  # noqa: F811
        EvalRunner,
        Grader,
        ReliabilityTracker,
    )

    # Create TokenLedger for per-eval token accounting
    token_ledger = TokenLedger()

    # Create SessionTelemetry for observability aggregation
    telemetry = SessionTelemetry()

    runner = EvalRunner(
        max_concurrency=config.max_concurrency,
        rate_limit_rpm=config.rate_limit_rpm,
        request_timeout=config.request_timeout,
        token_ledger=token_ledger,
        telemetry=telemetry,
        model_names=list(adapters.keys()) if adapters else [],
        integration_dispatcher=_build_integration_dispatcher(args),
        deep_security=getattr(args, "deep_security", False),
    )
    primary_adapter = list(adapters.values())[0]
    debias_position = getattr(args, "debias_position", True)
    grader = Grader(llm_client=primary_adapter, debias_position=debias_position)
    tracker = ReliabilityTracker()

    # Phase 1: Run evaluations
    all_results = _run_all_evals(
        adapters, runner, grader, spec.get("evals") or {}, spec_path, tracker, deadline=deadline
    )

    # Phase 2: Reliability Analysis
    reliability_report = tracker.generate_report()
    _print_reliability_report(reliability_report)

    # Phase 3: Calculate Metrics
    metrics = _calculate_metrics_with_stability(
        all_results, args, spec, spec_path, primary_adapter, config
    )

    # Append metrics to CI history
    _append_to_ci_history(args, spec_path, metrics)

    # Aggregate token data
    _aggregate_token_data(runner, token_ledger, metrics)
    metrics["reliability"] = reliability_report
    metrics["_results"] = all_results

    # REQ-017: Propagate degraded flag from Phase 1 for verdict capping
    _evals = spec.get("evals") or {}
    if isinstance(_evals, dict) and _evals.get("degraded"):
        metrics["degraded"] = True
        cov = _evals.get("_coverage", 0.0)
        print(f"\n  WARNING: Evaluation ran in degraded mode (coverage={cov:.0%})")

    # Print metrics summary
    _print_metrics_summary(metrics, args)

    # Phase 4: Drift Detection
    drift_report = _detect_and_print_drift(spec, adapters, grader)

    # Phase 4.5: Calibration Analysis (optional)
    calibration_data = _run_calibration(args, all_results)

    # Phase 5: Generate Report
    md_report, json_report = _generate_and_write_reports(
        args,
        output_dir,
        skill_name,
        spec,
        spec_path,
        adapters,
        metrics,
        drift_report,
        config,
        telemetry,
        calibration_data=calibration_data,
    )

    verdict = json_report.get("verdict", "FAIL")
    print(f"\n  Verdict: {verdict}")
    if verdict == "PASS":
        return EXIT_PASS
    if verdict == "PASS_WITH_CAVEATS":
        return EXIT_FAIL_WITH_CAVEATS
    return EXIT_ERROR
