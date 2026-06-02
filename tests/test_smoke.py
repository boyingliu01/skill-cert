"""End-to-end smoke test for the full skill-cert pipeline.

Runs the complete parse → generate → execute → grade → report pipeline
using mock model adapters and the project's own SKILL.md as input.
Verifies all output files are created without exceptions.
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

# ── Mock Model Adapter ──────────────────────────────────────────────────


class MockModelAdapter:
    """Mock LLM adapter returning deterministic responses for pipeline phases."""

    def __init__(self, model_name="mock-model"):
        self.model_name = model_name
        self.model = model_name
        self.chat_history = []
        self._mock_name = "mock_adapter"
        self.call_count = 0

        # Pre-defined responses keyed by phase
        self.responses = {
            "generate_evals": json.dumps({
                "eval_cases": [
                    {
                        "id": 1,
                        "name": "basic-trigger-test",
                        "category": "trigger",
                        "input": "Please review this skill for evaluation",
                        "expected_triggers": True,
                        "assertions": [
                            {"type": "contains", "value": "PASS", "weight": 3},
                            {"type": "regex", "value": "(verdict|result|score)", "weight": 2},
                        ],
                    },
                    {
                        "id": 2,
                        "name": "should-not-trigger-test",
                        "category": "trigger",
                        "input": "Hello world",
                        "expected_triggers": False,
                        "assertions": [
                            {"type": "not_contains", "value": "review", "weight": 2},
                            {"type": "regex", "value": "(greeting|hello)", "weight": 1},
                        ],
                    },
                    {
                        "id": 3,
                        "name": "normal-operation-test",
                        "category": "normal",
                        "input": "Execute the skill with sample input data",
                        "expected_triggers": True,
                        "assertions": [
                            {"type": "contains", "value": "skill", "weight": 2},
                            {"type": "regex", "value": "(output|result|metric)", "weight": 1},
                        ],
                    },
                    {
                        "id": 4,
                        "name": "anti-pattern-test",
                        "category": "boundary",
                        "input": "Try an invalid scenario",
                        "expected_triggers": False,
                        "assertions": [
                            {"type": "not_contains", "value": "error", "weight": 2},
                            {"type": "contains", "value": "invalid", "weight": 1},
                        ],
                    },
                ]
            }),
            "review_evals": json.dumps({
                "coverage": 0.95,
                "gaps": [],
                "needs_improvement": False,
            }),
            "eval_output": "Skill executed successfully. PASS verdict. L1: 0.95, L2: 0.80, L3: 0.90. "
                           "Results: all metrics computed. Coverage: 95%. "
                           "Step adherence: complete. No drift detected.",
        }

    def chat(self, messages, system=None, timeout=120):
        """Return predefined response based on message content."""
        content = ""
        for msg in messages:
            if isinstance(msg, dict) and "content" in msg:
                content += str(msg["content"])

        self.chat_history.append({"messages": messages, "system": system})
        self.call_count += 1

        # Route to the appropriate canned response
        if "generate" in content.lower() and "eval" in content.lower():
            return self.responses["generate_evals"]
        elif "review" in content.lower() and "eval" in content.lower():
            return self.responses["review_evals"]
        else:
            return self.responses["eval_output"]

    def chat_with_usage(self, messages):
        """Mock chat with token usage for runner compatibility."""
        response = self.chat(messages)
        return response, {
            "prompt_tokens": 50,
            "completion_tokens": len(response.split()),
            "total_tokens": 50 + len(response.split()),
        }


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def skill_path():
    """Path to the project's own SKILL.md (used as pipeline input)."""
    return str(Path(__file__).resolve().parent.parent / "SKILL.md")


@pytest.fixture
def output_dir():
    """Temporary directory for pipeline output files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


# ── Tests ───────────────────────────────────────────────────────────────


def test_full_pipeline_smoke(skill_path, output_dir):
    """Run the complete skill-cert pipeline end-to-end with mocks.

    Verifies:
      - No exceptions raised during any phase
      - parse_skill_md returns a valid SkillSpec dict
      - generate_evals_with_convergence returns eval cases
      - Runner produces results with-without-skill
      - Grader produces assertion_results for each eval
      - Reporter generates report.md, result.json
      - evals-cache.json is persisted to output directory
    """
    # ── Phase 0: Parse ──────────────────────────────────────────────────
    from engine.analyzer import parse_skill_md

    spec = parse_skill_md(skill_path)
    assert spec is not None, "parse_skill_md returned None"
    assert "name" in spec, "spec missing 'name'"
    assert isinstance(spec["name"], str) and spec["name"], "name should be non-empty string"
    assert "workflow_steps" in spec, "spec missing 'workflow_steps'"
    assert "parse_confidence" in spec, "spec missing 'parse_confidence'"
    assert isinstance(spec["parse_confidence"], (int, float))
    assert spec["parse_confidence"] >= 0.0, "parse_confidence should be >= 0"

    # ── Phase 1: Generate Evals with Convergence ────────────────────────
    from engine.testgen import EvalGenerator

    generator = EvalGenerator()
    mock_adapter = MockModelAdapter()
    mock_review_adapter = MockModelAdapter()

    evals = generator.generate_evals_with_convergence(
        spec, mock_adapter, mock_review_adapter
    )
    assert evals is not None, "generate_evals_with_convergence returned None"

    # Extract eval cases (handles flexible key naming)
    eval_cases = evals.get("eval_cases") or evals.get("evals") or evals.get("cases") or []
    assert len(eval_cases) >= 1, "Should have at least 1 eval case"

    # Persist evals-cache.json to output directory
    evals_cache_path = Path(output_dir) / "evals-cache.json"
    evals_cache_path.write_text(json.dumps(evals, indent=2), encoding="utf-8")

    # ── Phase 2: Execute Evals (with and without skill) ─────────────────
    from engine.runner import EvalRunner

    runner = EvalRunner(max_concurrency=2, rate_limit_rpm=120, request_timeout=10)

    results_with = runner.run_with_skill(eval_cases, skill_path, mock_adapter)
    results_without = runner.run_without_skill(eval_cases, mock_adapter)

    assert len(results_with) == len(eval_cases), (
        f"Expected {len(eval_cases)} with-skill results, got {len(results_with)}"
    )
    assert len(results_without) == len(eval_cases), (
        f"Expected {len(eval_cases)} without-skill results, got {len(results_without)}"
    )

    for r in results_with:
        assert r["eval_id"] is not None, "with-skill result missing eval_id"
        assert r["run"] == "with-skill", "with-skill result has wrong run type"
        assert r["error"] is None, f"with-skill result has error: {r['error']}"
        assert r["output"] is not None, "with-skill result missing output"

    for r in results_without:
        assert r["eval_id"] is not None, "without-skill result missing eval_id"
        assert r["run"] == "without-skill", "without-skill result has wrong run type"
        assert r["error"] is None, f"without-skill result has error: {r['error']}"
        assert r["output"] is not None, "without-skill result missing output"

    # ── Phase 3: Grade Outputs ──────────────────────────────────────────
    from engine.grader import EvalAssertion, EvalCase, Grader

    grader = Grader(llm_client=None)  # No LLM-as-judge; deterministic only

    graded_results = []

    def _grade_one(ec_dict, result_dict, skill_used):
        """Convert an eval case dict to EvalCase and grade the output."""
        assertions = [
            EvalAssertion(
                name=f"assert_{i}",
                type=a["type"],
                value=a["value"],
                weight=a.get("weight", 1),
            )
            for i, a in enumerate(ec_dict.get("assertions", []))
        ]
        case = EvalCase(
            id=ec_dict["id"],
            name=ec_dict.get("name", f"eval-{ec_dict['id']}"),
            category=ec_dict.get("category", "normal"),
            prompt=ec_dict.get("input", ec_dict.get("prompt", "")),
            assertions=assertions,
        )
        grade_result = grader.grade_output(case, result_dict.get("output", ""))
        return {
            **result_dict,
            "grade": grade_result,
            "skill_used": skill_used,
            "final_passed": grade_result.get("final_passed", False),
            "pass_rate": grade_result.get("pass_rate", 0.0),
            "category": result_dict.get("eval_category", ec_dict.get("category", "normal")),
        }

    for r in results_with:
        ec = next((c for c in eval_cases if c["id"] == r["eval_id"]), None)
        if ec is not None:
            graded_results.append(_grade_one(ec, r, skill_used=True))

    for r in results_without:
        ec = next((c for c in eval_cases if c["id"] == r["eval_id"]), None)
        if ec is not None:
            graded_results.append(_grade_one(ec, r, skill_used=False))

    assert len(graded_results) > 0, "No graded results produced"

    # Verify structure of graded results
    for gr in graded_results:
        assert "grade" in gr, "graded result missing 'grade'"
        grade = gr["grade"]
        assert "assertion_results" in grade, "grade missing assertion_results"
        assert len(grade["assertion_results"]) > 0, "assertion_results is empty"
        assert "pass_rate" in grade, "grade missing pass_rate"
        assert "final_passed" in grade, "grade missing final_passed"
        # Each assertion result should have the expected fields
        for ar in grade["assertion_results"]:
            assert "assertion" in ar, "assertion result missing 'assertion'"
            assert "passed" in ar, "assertion result missing 'passed'"
            assert "confidence" in ar, "assertion result missing 'confidence'"
            assert "reason" in ar, "assertion result missing 'reason'"

    # ── Phase 4: Calculate Metrics ──────────────────────────────────────
    from engine.metrics import MetricsCalculator

    calc = MetricsCalculator()
    metrics = calc.calculate_metrics(graded_results)

    assert "overall_score" in metrics, "metrics missing overall_score"
    assert isinstance(metrics["overall_score"], (int, float))
    assert "l1_trigger_accuracy" in metrics, "metrics missing l1_trigger_accuracy"
    assert "l2_with_without_skill_delta" in metrics, "metrics missing l2_with_without_skill_delta"
    assert "l3_step_adherence" in metrics, "metrics missing l3_step_adherence"
    assert "l4_execution_stability" in metrics, "metrics missing l4_execution_stability"
    assert "metrics_breakdown" in metrics, "metrics missing metrics_breakdown"

    # Attach raw results for report generation
    metrics["_results"] = graded_results

    # ── Phase 5: Generate Report ────────────────────────────────────────
    from engine.reporter import Reporter

    drift_report = {
        "drift_detected": False,
        "highest_severity": "none",
        "average_variance": 0.0,
        "max_variance": 0.0,
        "model_pairs_compared": 0,
        "overall_verdict": "PASS",
        "drift_results": [],
    }

    config = {
        "max_concurrency": 2,
        "rate_limit_rpm": 120,
        "request_timeout": 10,
        "models": [{"model_name": "mock-model"}],
        "total_evaluations": len(graded_results),
        "avg_pass_rate": (
            sum(r.get("pass_rate", 0.0) for r in graded_results) / len(graded_results)
            if graded_results
            else 0.0
        ),
        "total_tokens": sum(r.get("tokens_used", 0) for r in graded_results),
    }

    reporter = Reporter()
    md_report, json_report = reporter.generate_report(metrics, drift_report, config)

    assert md_report is not None, "generate_report returned None for markdown"
    assert json_report is not None, "generate_report returned None for JSON"
    assert "Skill Certification Report" in md_report, "Markdown missing title"
    assert json_report["verdict"] in ("PASS", "PASS_WITH_CAVEATS", "FAIL"), (
        f"Unexpected verdict: {json_report['verdict']}"
    )
    assert "metrics" in json_report, "JSON report missing metrics"
    assert "drift_analysis" in json_report, "JSON report missing drift_analysis"

    # ── Write Output Files ──────────────────────────────────────────────
    report_md_path = Path(output_dir) / "report.md"
    report_json_path = Path(output_dir) / "result.json"

    report_md_path.write_text(md_report, encoding="utf-8")
    report_json_path.write_text(
        json.dumps(json_report, indent=2, default=str), encoding="utf-8"
    )

    # ── Verify All 3 Output Files Exist ─────────────────────────────────
    assert report_md_path.exists(), f"report.md not found at {report_md_path}"
    assert report_json_path.exists(), f"result.json not found at {report_json_path}"
    assert evals_cache_path.exists(), f"evals-cache.json not found at {evals_cache_path}"

    # Verify files are non-empty
    assert report_md_path.stat().st_size > 0, "report.md is empty"
    assert report_json_path.stat().st_size > 0, "result.json is empty"
    assert evals_cache_path.stat().st_size > 0, "evals-cache.json is empty"

    # Verify JSON reports are valid
    loaded_json = json.loads(report_json_path.read_text(encoding="utf-8"))
    assert loaded_json["verdict"] == json_report["verdict"], (
        "Written JSON report mismatch"
    )

    loaded_evals = json.loads(evals_cache_path.read_text(encoding="utf-8"))
    assert "eval_cases" in loaded_evals, "evals-cache.json missing eval_cases"


def test_pipeline_rejects_nonexistent_skill():
    """Verify parse_skill_md raises FileNotFoundError for missing file."""
    from engine.analyzer import parse_skill_md

    with pytest.raises(FileNotFoundError, match="SKILL.md not found"):
        parse_skill_md("/nonexistent/path/SKILL.md")


def test_pipeline_parse_minimal_skill():
    """Verify the parser works on a minimal in-memory skill file."""
    import tempfile

    from engine.analyzer import parse_skill_md

    minimal_skill = """---
name: minimal-test
description: A minimal skill for testing
---

# Minimal Test

## Workflow

1. Do something
2. Do something else
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(minimal_skill)
        tmp_path = f.name

    try:
        spec = parse_skill_md(tmp_path)
        assert spec["name"] == "minimal-test"
        assert len(spec["workflow_steps"]) == 2
        assert spec["parse_confidence"] > 0.0
        assert "schema_validation" in spec
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
