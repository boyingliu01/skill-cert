# AGENTS.md

This file provides guidance to AI coding agents working on the **skill-cert** engine codebase. Do NOT apply this guidance to unrelated projects that happen to mention "skills" or "evaluation."

**Project:** skill-cert — AI Skill Evaluation Engine  
**Version:** 0.15.1 (single source: `pyproject.toml`; there is no VERSION file)  
**Python:** 3.10+  
**Framework:** Pydantic v2, pytest, httpx, markdown-it-py

## OVERVIEW

Automated evaluation engine for AI skills (SKILL.md files). Parses skill definitions via regex + AST (LLM fallback), generates eval tests via self-review loop (coverage ≥ 90%), executes with/without-skill baseline comparison across multiple LLM models, grades outputs via deterministic assertions + LLM-as-judge (temp=0), computes L1–L8 metrics, detects cross-model drift, security probes, multi-skill conflicts, and produces standardized PASS/FAIL verdicts.

A second, independent path — `skill-cert harness` — runs a skill through a **real agent runtime** (opencode / dsh): taskgen derives tasks plus hidden rubrics from the SKILL.md, the harness adapter executes each task twice (with and without the skill), and an LLM judge scores every rubric item via structured output.

## ARCHITECTURE

```
skill-cert/
├── engine/            # Core domain (32 modules + harness/ + reporters/): analyzer, testgen, runner,
│                      # grader, metrics, reporter, drift, envelope, dialogue, replay, security,
│                      # observability, deadline, token_ledger, integrations, reliability,
│                      # maintainability, multi_skill, stress_test, stability, calibration, harness/
├── skill_cert/cli/    # CLI entry point: main.py, harness.py, setup.py, single/dialogue/replay/evals
├── adapters/          # LLM provider adapters: base protocol, anthropic, openai, pricing, harness/
├── prompts/           # LLM prompt templates (.md files)
├── schemas/           # JSON schema: report.schema.json
├── templates/         # Eval fallback: minimum-evals.json
├── tests/             # pytest suite — 1594 tests, mirrors engine/ 1:1
└── results/           # Output: {skill}-report.md, {skill}-result.json, {skill}-evals-cache.json
```

**Layer flow:** `skill_cert/cli/` → `engine/` → `adapters/`

## COMMANDS

```bash
# Install (editable with dev deps)
pip install --no-build-isolation -e ".[dev]"

# Run evaluation
skill-cert --skill /path/to/SKILL.md --models "m1=url,key|m2=url,key" --output ./results/

# CLI flags
--version              # Print version
--strict-schema        # Reject SKILL.md on required field violations
--with-skill-lab       # Enable SkillLab integration
--with-deepeval        # Enable DeepEval integration
--envelope '{"max_steps":30}'  # Custom envelope thresholds
--mode single|dialogue|replay
--runs N               # Multi-run for L4 stability
--max-turns N          # Dialogue turn limit
--stress               # Enable stress testing
--stress-concurrency N # Stress test concurrency level
--stress-evals N       # Stress test eval count

# Setup wizard (interactive config)
skill-cert setup

# Real-harness evaluation (double-run delta scored by an LLM judge)
skill-cert harness --skill /path/to/SKILL.md --model provider/model \
                   [--harness opencode|dsh] [--judge-model NAME] [--tasks 6] \
                   [--runs 1] [--serve] [--task-timeout 600] [--keep-sandboxes] [--output ./results]

# Run tests
pytest tests/
pytest tests/test_metrics.py -v           # Single file
pytest tests/test_metrics.py::TestMetricsCalculator::test_l2_with_greater_than_without_exact_delta -v  # Single test

# Coverage
pytest --cov=engine --cov=skill_cert --cov=adapters --cov-report=term-missing

# Lint
ruff check . && ruff format .
```

## KEY MODULES

| Module | Purpose |
|--------|---------|
| `engine/analyzer.py` | SKILL.md parser → SkillSpec (regex + AST, LLM fallback, schema validation, `SchemaValidationError`) |
| `engine/testgen.py` | EvalGenerator: generate → review → gap-fill loop until coverage ≥ 90% |
| `engine/json_extract.py` | Public 4-level JSON extraction chain (fences → balanced braces → largest-first → strict=False) shared by testgen, grader and harness |
| `engine/runner.py` | Execution engine: with/without skill baseline comparison |
| `engine/grader.py` | Deterministic assertions + LLM-as-judge (temp=0, position debiasing) |
| `engine/metrics.py` | L1-L8 calculation (L2 uses normalized gain formula: Δ=(with-without)/without) |
| `engine/envelope.py` | Operating envelope checker: steps/tokens/timeout/tool_calls |
| `engine/drift.py` | Cross-model drift detection (severity: none/low/moderate/high) |
| `engine/security_probes.py` | 80 patterns across 6 categories (INJ/EXF/DCMD/CRD/OBF/PRIV_ESC) |
| `engine/dialogue_evaluator.py` | Multi-turn evaluation + `judge_with_llm()` for LLM-as-Judge |
| `engine/harness/taskgen.py` | Tasks + hidden rubrics generated from a SKILL.md (structured output) |
| `engine/harness/evaluator.py` | Double-run orchestration (with vs. without skill) on a real runtime |
| `engine/harness/judge.py` | Per-rubric LLM judge, temp=0, structured `response_format` scoring |
| `engine/harness/report.py` | Markdown + JSON rendering for harness evaluations |
| `adapters/harness/` | Runtime backends: `opencode` (JSON event stream) and `dsh` |
| `engine/calibration.py` | Golden eval set calibration (Cohen's Kappa, FPR/FNR) |
| `engine/reporter.py` + `engine/reporters/` | Markdown + JSON report generation (builders prepare sections) |
| `engine/observability.py` | EventBus + TraceExporter + SessionTelemetry |
| `engine/deadline.py` | Global pipeline timeout (`elapsed`/`remaining`/`must_stop`/`adapter_timeout`) |
| `skill_cert/cli/setup.py` | Interactive/non-interactive config wizard |

## L1-L8 METRICS

| Level | Metric | Threshold |
|-------|--------|-----------|
| L1 | Trigger Accuracy | ≥ 90% |
| L2 | With/Without Skill Normalized Gain | ≥ 20% |
| L3 | Step Adherence (weighted: 0.5×step_coverage + 0.3×tool_call_accuracy + 0.2×turn_relevance) | ≥ 85% |
| L4 | Execution Stability (std dev) | ≤ 10% |
| L5 | Step Efficiency (EnvelopeChecker) | passed=1.0, 1violation=0.7, 2+=0.3 |
| L6 | Trajectory Quality | dialogue mode only |
| L7 | Cost Efficiency | token→$ via adapters/pricing.py |
| L8 | Latency (P50/P95/P99) | — |

**Verdict:** PASS = L1≥90%, L2≥20%, L3≥85%, L4≤10%, drift none/low

## CONVENTIONS

- **Pydantic v2** for all data models (SkillSpec, WorkflowStep, EvalResult)
- **Type annotations** on all function signatures
- **ruff** for formatting and linting (line-length=100, target=py310)
- **pytest** with `asyncio_mode = "auto"` in pyproject.toml
- Test files mirror engine modules 1:1 (`test_analyzer.py` ↔ `engine/analyzer.py`)
- Prompt templates are `.md` files in `prompts/`, not Python strings
- Timing tests never assert clock advance from a short sleep: `time.monotonic()` on this host is `GetTickCount64()` with 15.625ms resolution, so waits must span ≥4 ticks or the clock must be mocked (`engine.deadline` tests do both)
- Results: each skill produces 3 files — report.md, result.json, evals-cache.json (a harness run writes 2 — {skill}-harness-report.md/.json)

## ANTI-PATTERNS

- Skip Phase 1 self-review loop (generate → review → gap-fill)
- Run with-skill without without-skill baseline (breaks L2 delta)
- Modify eval cases after Phase 2 execution begins (integrity rule)
- Use LLM-as-judge with temp > 0 (introduces nondeterminism)
- Coverage < 70% and still execute evaluation (should block)
- Single-model evaluation (minimum 2 providers for drift detection)

## NOTES

- 1594 tests collect (1 skipped)
- Security probes: 80 patterns across 6 categories
- L2 formula: normalized gain `Δ = (with - without) / without` (not absolute delta)
- EnvelopeChecker is wired into L5 step efficiency scoring
- `DialogueJudgeResult` supports both LLM-as-Judge and heuristic fallback
- API keys via environment variables (no hardcoded secrets)
- Pricing table: 19 models in 5 families (Anthropic, OpenAI, Qwen, DeepSeek, Gemini, plus whalecloud LOCAL entries priced at 0)
- No CI type-check job here: the mypy surface Gate 1 enforces is declared in `.xp-gate-mypy-scope`
- Wheel builds ship `prompts/`, `templates/` and `schemas/` because `[tool.setuptools.packages.find]` runs with `namespaces = true` — those dirs have no `__init__.py`, so a new top-level data directory must be added to that `include` list (guarded by `tests/test_packaging.py`)
