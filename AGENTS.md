# AGENTS.md

This file provides guidance to Qoder (qoder.com) when working with code in this repository.

**Project:** skill-cert — AI Skill Evaluation Engine  
**Version:** 0.3.0  
**Python:** 3.10+  
**Framework:** Pydantic v2, pytest, httpx, markdown-it-py

## OVERVIEW

Automated evaluation engine for AI skills (SKILL.md files). Parses skill definitions via regex + AST (LLM fallback), generates eval tests via self-review loop (coverage ≥ 90%), executes with/without-skill baseline comparison across multiple LLM models, grades outputs via deterministic assertions + LLM-as-judge (temp=0), computes L1–L8 metrics, detects cross-model drift, security probes, multi-skill conflicts, and produces standardized PASS/FAIL verdicts.

## ARCHITECTURE

```
skill-cert/
├── engine/            # Core domain: parser, testgen, runner, grader, metrics, reporter, drift,
│                      # dialogue, replay, security, envelope, integrations, reliability,
│                      # maintainability, multi_skill, stress_test, stability, calibration,
│                      # goal_change, golden_dataset, skills_bench
├── skill_cert/cli/    # CLI entry point: main.py, setup.py
├── adapters/          # LLM provider adapters: base protocol, anthropic, openai, pricing
├── prompts/           # LLM prompt templates (.md files)
├── schemas/           # JSON schemas: evals, skillspec
├── templates/         # Eval fallback: minimum-evals.json
├── tests/             # pytest suite — 684 tests, mirrors engine/ 1:1
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

# Setup wizard (interactive config)
skill-cert setup

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
| `engine/runner.py` | Execution engine: with/without skill baseline comparison |
| `engine/grader.py` | Deterministic assertions + LLM-as-judge (temp=0, position debiasing) |
| `engine/metrics.py` | L1-L8 calculation (L2 uses normalized gain formula: Δ=(with-without)/without) |
| `engine/envelope.py` | Operating envelope checker: steps/tokens/timeout/tool_calls |
| `engine/drift.py` | Cross-model drift detection (severity: none/low/moderate/high) |
| `engine/security_probes.py` | 52 patterns across 6 categories (INJ/EXF/DCMD/CRD/OBF/PRIV_ESC) |
| `engine/dialogue_evaluator.py` | Multi-turn evaluation + `judge_with_llm()` for LLM-as-Judge |
| `engine/goal_change.py` | AgentChangeBench-style mid-turn goal adaptation testing |
| `engine/golden_dataset.py` | 50+ human-anchored test cases for calibration |
| `engine/skills_bench.py` | Multi-skill cognitive overload detection (sweet spot analysis) |
| `engine/calibration.py` | Golden eval set calibration (Cohen's Kappa, FPR/FNR) |
| `engine/reporter.py` | Markdown + JSON report generation |
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
- Results: each skill produces 3 files — report.md, result.json, evals-cache.json

## ANTI-PATTERNS

- Skip Phase 1 self-review loop (generate → review → gap-fill)
- Run with-skill without without-skill baseline (breaks L2 delta)
- Modify eval cases after Phase 2 execution begins (integrity rule)
- Use LLM-as-judge with temp > 0 (introduces nondeterminism)
- Coverage < 70% and still execute evaluation (should block)
- Single-model evaluation (minimum 2 providers for drift detection)

## NOTES

- 684 tests pass, 1 skipped
- Security probes: 52 patterns across 6 categories
- L2 formula: normalized gain `Δ = (with - without) / without` (not absolute delta)
- EnvelopeChecker is wired into L5 step efficiency scoring
- `DialogueJudgeResult` supports both LLM-as-Judge and heuristic fallback
- API keys via environment variables (no hardcoded secrets)
- Pricing table: 17 models across 5 providers (Anthropic, OpenAI, Qwen, DeepSeek, Gemini, Whalecloud LOCAL)
