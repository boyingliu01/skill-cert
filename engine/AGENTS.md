# engine/ — Core Evaluation Pipeline (v2)

## OVERVIEW
16-module evaluation pipeline: parses SKILL.md skills, validates schema, runs security probes, generates eval tests via self-review loop, executes against LLM adapters, grades outputs, computes L1-L6 metrics, checks operating envelope, detects cross-model drift, integrates external tools, and produces standardized reports.

## STRUCTURE
```
engine/
├── analyzer.py        # SKILL.md parser → SkillSpec (regex + markdown-it-py AST, LLM fallback) + schema validation
├── security_probes.py # Security scanner: 19 patterns across 5 categories (INJ/EXF/DCMD/CRD/OBF), verdict PASS/WARN/BLOCK
├── testgen.py         # EvalGenerator: generate → review → gap-fill loop until coverage ≥90%
├── runner.py          # Execution engine: with/without skill, concurrency, rate limiting, timeout
├── grader.py          # Grader: deterministic assertions + LLM-as-judge (temp=0)
├── metrics.py         # L1-L6 calculation: trigger accuracy, delta, step adherence, stability, efficiency, trajectory quality
├── envelope.py        # Operating envelope checker: steps/tokens/timeout/tool_calls with config-driven thresholds
├── integrations.py    # External tool integration: Provider pattern (BaseIntegration ABC + dispatcher), ToolAvailability protocol
├── drift.py           # Cross-model drift detection: none/low/moderate/high severity
├── reporter.py        # Markdown + JSON report generation with verdict
├── replay.py          # Regression testing with historical session data
├── dialogue_evaluator.py  # Multi-turn skill assessment evaluator
├── dialogue_runner.py     # Orchestrates dialogue evaluation sessions
├── simulator.py       # LLM behavior simulation for testing without live API calls
├── config.py          # Configuration management and validation
└── __init__.py        # Public API: exports parse_skill_md
```

## WHERE TO LOOK
| Task | File | Notes |
|------|------|-------|
| Parse SKILL.md → dict | `analyzer.py` | `parse_skill_md()` entry, returns SkillSpec model_dump with schema_validation |
| Validate SKILL.md schema | `analyzer.py` | `_validate_schema()` checks Security Notes/Permissions/Scope/Description |
| Security scanning | `security_probes.py` | `SecurityScanner.scan()` — 19 patterns, 5 categories, severity_matrix |
| Generate evals | `testgen.py` | `EvalGenerator.generate_evals_with_convergence()` — main entry |
| Execute evals | `runner.py` | `Runner` class: manages with/without skill parallel runs |
| Grade outputs | `grader.py` | `Grader` class: supports contains, not_contains, regex, starts_with, json_valid |
| Compute metrics | `metrics.py` | `calculate_metrics()` → returns dict with L1-L6 breakdowns |
| Check operating envelope | `envelope.py` | `EnvelopeChecker.check()` — steps/tokens/timeout/tool_calls |
| External integrations | `integrations.py` | `IntegrationDispatcher` with `SkillLabIntegration` + `DeepEvalIntegration` |
| Detect drift | `drift.py` | `detect_drift()` → severity thresholds in CONSTANTS |

## CONVENTIONS
- All data models are Pydantic `BaseModel` subclasses
- Functions return dicts (not model instances) via `model_dump(by_alias=True)`
- `eval_cases` key flexible: also checks evals, cases, test_cases, evaluations, eval
- Coverage threshold: 0.9 (90%), degrade: 0.7, block: 0.7
- Max review rounds: 3, consecutive no-improvement limit: 2
- JSON parsing from LLM responses: extracts first `{` to last `}`
- Minimum evals fallback in `templates/minimum-evals.json`, hardcoded in testgen.py

## ANTI-PATTERNS (THIS MODULE)
- Call `generate_initial_evals()` without review loop — skips gap-filling
- Run `runner` without both with-skill AND without-skill contexts — delta breaks
- Modify eval_cases after Phase 2 execution (integrity violation)
- Use LLM-as-judge with temp > 0 — introduces grading nondeterminism
- Skip `_calculate_coverage()` before grading — coverage gating essential

## UNIQUE STYLES
- **Triple threshold system in testgen**: coverage (0.9), degrade (0.7), block (0.7)
- **Flexible eval_cases key**: checks 6 possible key names in each response parse
- **Coverage formula**: workflow × 0.5 + anti-pattern × 0.3 + output-format × 0.2
- **Drift severity**: none ≤0.10, low ≤0.20, moderate ≤0.35, high >0.35
- **Graceful degradation**: every LLM call wrapped in try/except → returns template fallback
