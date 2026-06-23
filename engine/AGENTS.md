# engine/ — Core Evaluation Pipeline

## OVERVIEW
22-module evaluation pipeline: parses SKILL.md skills, validates schema, runs security probes, generates eval tests via self-review loop, executes against LLM adapters, grades outputs, computes L1-L8 metrics, checks operating envelope, detects cross-model drift, integrates external tools, runs stress/stability/reliability/maintainability/multi-skill analysis, golden dataset calibration, skills bench analysis, and produces standardized reports.

## STRUCTURE
```
engine/
├── analyzer.py            # SKILL.md parser → SkillSpec (regex + AST, LLM fallback, SchemaValidationError)
├── security_probes.py     # Security scanner: 52 patterns across 6 categories
├── testgen.py             # EvalGenerator: generate → review → gap-fill loop until coverage ≥90%
├── runner.py              # Execution engine: with/without skill, concurrency, rate limiting
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
├── multi_skill.py         # Multi-skill conflict: trigger overlap, prompt contamination
├── replay.py              # Regression testing with historical session data
├── dialogue_evaluator.py  # Multi-turn evaluation + judge_with_llm() LLM-as-Judge
├── dialogue_runner.py     # Orchestrates dialogue evaluation sessions
├── simulator.py           # LLM behavior simulation for testing without live API
├── calibration.py         # Golden eval set calibration (Cohen's Kappa, FPR/FNR)
├── skills_bench.py        # Multi-skill cognitive overload detection (sweet spot)
├── config.py              # Configuration management and validation
└── __init__.py            # Public API: exports parse_skill_md
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
| `SecurityScanner` | 52-pattern security probe suite |
| `DialogueJudgeResult` | LLM-as-Judge result with per-dimension scores |
| `SkillsBenchAnalyzer` | Multi-skill cognitive overload detection |
| `GoldenEvalSet` / `CalibrationRunner` | Human-anchored calibration framework |

## CONVENTIONS
- All data models are Pydantic `BaseModel` subclasses
- Functions return dicts via `model_dump(by_alias=True)`
- `eval_cases` key flexible: also checks evals, cases, test_cases, evaluations, eval
- Coverage threshold: 0.9 (90%), degrade: 0.7, block: 0.7
- L2 formula: normalized gain `Δ = (with - without) / without` (capped [0,1])
- Graceful degradation: every LLM call wrapped in try/except → returns template fallback
