# engine/ — Core Evaluation Pipeline

## OVERVIEW
31 top-level modules plus the `harness/` and `reporters/` packages: parses SKILL.md skills, validates schema, runs security probes, generates eval tests via self-review loop, executes against LLM adapters, grades outputs, computes L1-L8 metrics, checks operating envelope, detects cross-model drift, integrates external tools, runs stress/stability/reliability/maintainability/multi-skill analysis, golden dataset calibration, OTel telemetry, token ledger, deadline enforcement, progressive disclosure / structure-quality / hooks analysis, output-type classification, and produces standardized reports. `harness/` is the separate real-runtime path (taskgen → double-run → LLM judge → report).

## STRUCTURE
```
engine/
├── analyzer.py            # SKILL.md parser → SkillSpec (regex + AST, LLM fallback, SchemaValidationError)
├── security_probes.py     # Security scanner: 80 patterns across 6 categories (INJ/EXF/DCMD/CRD/OBF/PRIV_ESC)
├── testgen.py             # EvalGenerator: generate → review → gap-fill loop until coverage ≥90%
├── runner.py              # Execution engine: with/without skill, concurrency, rate limiting, deadline
├── grader.py              # Grader: deterministic assertions + LLM-as-judge (temp=0)
├── metrics.py             # L1-L8 calculation (L2 normalized gain, L5 envelope wired)
├── envelope.py            # Operating envelope checker: steps/tokens/timeout/tool_calls
├── integrations.py        # External tool integration: SkillLab/DeepEval providers
├── drift.py               # Cross-model drift detection: none/low/moderate/high severity
├── reporter.py            # Markdown + JSON report generation with verdict
├── stability.py           # L4 stability: multi-run execution with --runs flag
├── stress_test.py         # Concurrency stress testing: fairness, memory, scalability
├── reliability.py         # Error classification, retry stats, graceful degradation
├── maintainability.py     # SKILL.md readability, completeness, freshness scoring
├── multi_skill.py         # Multi-skill conflict: trigger overlap, prompt contamination, token overflow
├── replay.py              # Regression testing with historical session data
├── dialogue_evaluator.py  # Multi-turn evaluation + judge_with_llm() LLM-as-Judge
├── dialogue_runner.py     # Dialogue execution with OTel trace recording
├── simulator.py           # LLM behavior simulation for testing without live API
├── calibration.py         # Golden eval set calibration (Cohen's Kappa, FPR/FNR)
├── harness/               # Real-runtime path: taskgen → evaluator (double run) → judge → report
│   ├── taskgen.py         # Tasks + hidden rubrics from a SKILL.md (structured output)
│   ├── evaluator.py       # With/without-skill orchestration over adapters/harness backends
│   ├── judge.py           # Per-rubric LLM judge (temp=0, response_format)
│   ├── llm_json.py        # chat_json(): structured call + typed degradation to prompt-embedded JSON
│   ├── models.py          # Task / Rubric / RunRecord / HarnessEvalReport (Pydantic v2)
│   ├── util.py            # Prompt-template rendering + traversal-free path components
│   └── report.py          # Markdown + JSON rendering for harness runs
├── reporters/             # builders.py — section preparation for reporter.py
├── classifier.py          # Output-type classifier routing assertion strategy
├── structure_quality.py   # Tool-permission isolation + script usage detection
├── hooks_detector.py      # Hook/guardrail detection in SKILL.md files
├── config.py              # Configuration management and validation
├── observability.py       # OTel GenAI session telemetry: SessionTelemetry, record_trace
├── token_ledger.py        # Real-time token usage tracking (not approximations)
├── progressive_disclosure.py # Progressive disclosure evaluation
├── deadline.py            # Global deadline enforcement
├── constants.py           # Shared constants and defaults
├── report_models.py       # Report data models (Pydantic)
├── trace_models.py        # Telemetry trace data models
└── __init__.py            # Public API: parse_skill_md, Deadline, PhaseTimer
```

## KEY SYMBOLS

| Symbol | Purpose |
|--------|---------|
| `SkillSpec` | Pydantic model for parsed skill semantics |
| `SchemaValidationError` | Raised when `strict_schema=True` and required fields missing |
| `parse_skill_md(path, strict_schema=False)` | Main parser entry point |
| `EvalGenerator` | Generate → review → gap-fill loop |
| `Runner` | Eval execution engine (with/without skill) |
| `Grader` | Output assertion checker (deterministic + LLM-as-judge) |
| `MetricsCalculator` | L1-L8 metric computation |
| `EnvelopeChecker` | Operating envelope validation (wired into L5) |
| `SecurityScanner` | 80-pattern security probe suite (6 categories) |
| `DialogueJudgeResult` | LLM-as-Judge result with per-dimension scores |
| `HarnessEvaluator` | Double-run orchestration for the real-harness path |
| `HarnessJudge` | Per-rubric structured-output judge (scores clamped 0–10) |
| `Task` / `Rubric` / `JudgeResult` | Harness models — hidden rubrics and verdicts (`harness/models.py`) |
| `GoldenEvalSet` / `CalibrationRunner` | Human-anchored calibration framework |

## CONVENTIONS
- All data models are Pydantic `BaseModel` subclasses
- Functions return dicts via `model_dump(by_alias=True)`
- `eval_cases` key flexible: also checks evals, cases, test_cases, evaluations, eval
- Coverage threshold: 0.9 (90%), degrade: 0.7, block: 0.7
- L2 formula: normalized gain `Δ = (with - without) / without` (capped [0,1])
- Graceful degradation: every LLM call wrapped in try/except → returns template fallback
