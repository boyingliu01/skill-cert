# engine/ — Core Evaluation Pipeline

## OVERVIEW
13-module evaluation pipeline: parses SKILL.md skills, generates eval tests via self-review loop, executes against LLM adapters, grades outputs, computes L1-L4 metrics, detects cross-model drift, and produces standardized reports.

## STRUCTURE
```
engine/
├── analyzer.py        # SKILL.md parser → SkillSpec (regex + markdown-it-py AST, LLM fallback)
├── testgen.py         # EvalGenerator: generate → review → gap-fill loop until coverage ≥90%
├── runner.py          # Execution engine: with/without skill, concurrency, rate limiting, timeout
├── grader.py          # Grader: deterministic assertions + LLM-as-judge (temp=0)
├── metrics.py         # L1-L4 calculation: trigger accuracy, delta, step adherence, stability
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
| Parse SKILL.md → dict | `analyzer.py` | `parse_skill_md()` entry, returns SkillSpec model_dump |
| Generate evals | `testgen.py` | `EvalGenerator.generate_evals_with_convergence()` — main entry |
| Execute evals | `runner.py` | `Runner` class: manages with/without skill parallel runs |
| Grade outputs | `grader.py` | `Grader` class: supports contains, not_contains, regex, starts_with, json_valid |
| Compute metrics | `metrics.py` | `calculate_metrics()` → returns dict with L1-L4 breakdowns |
| Detect drift | `drift.py` | `detect_drift()` → severity thresholds in CONSTANTS |
| Generate reports | `reporter.py` | Produces .md + .json output files |
| Dialogue mode | `dialogue_evaluator.py` + `dialogue_runner.py` | Multi-turn orchestration |
| Replay mode | `replay.py` | Loads .jsonl sessions, replays evals |
| Config | `config.py` | Validates CLI settings, rate limits, model configs |
| Simulator | `simulator.py` | Mock LLM responses for unit testing engine |

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
