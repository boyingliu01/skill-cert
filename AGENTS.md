# PROJECT KNOWLEDGE BASE

**Generated:** 2026-05-01
**Project:** skill-cert — AI Skill Evaluation Engine

## OVERVIEW
Automated evaluation engine for AI skills (SKILL.md files). Parses arbitrary skill definitions, generates eval tests, executes them across multiple LLM models, calculates L1-L4 metrics, detects cross-model drift, and produces standardized reports with PASS/FAIL verdicts.

## STRUCTURE
```
skill-cert/
├── engine/          # Core pipeline: parser, testgen, runner, grader, metrics, reporter, drift, dialogue, replay, simulator
├── skill_cert/      # CLI entry point (cli.py)
├── adapters/        # LLM provider adapters: anthropic_compat, openai_compat, base protocol
├── prompts/         # LLM prompt templates (judge, dialogue, drift-detect, testgen, test-review, test-gap)
├── schemas/         # JSON schemas: evals.schema.json, skillspec.schema.json
├── templates/       # Eval fallback: minimum-evals.json
├── scripts/         # UAT utilities: run_uat.py, verify_uat.py
├── tests/           # pytest suite — mirrors engine/modules 1:1
├── results/         # Output: {skill}-report.md, {skill}-result.json, {skill}-evals-cache.json
├── examples/        # Sample eval files (evals.json with assertion types)
├── docs/            # Project documentation (CLAUDE.md, ARCHITECTURE.md, CHANGELOG.md)
├── pyproject.toml   # Python project config
├── SKILL.md         # This project's own skill definition
└── specification.yaml  # 10 requirements (REQ-001 to REQ-010), acceptance criteria
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Parse SKILL.md → SkillSpec | `engine/analyzer.py` | Regex + markdown-it-py AST, fallback to LLM |
| Generate eval tests | `engine/testgen.py` | Generate → Review → Gap-fill loop until coverage >= 90% |
| Execute with/without skill | `engine/runner.py` | Concurrency control, rate limiting, timeout handling |
| Grade outputs (deterministic) | `engine/grader.py` | Assertion types: contains, not_contains, regex, starts_with, json_valid |
| LLM-as-judge grading | `engine/grader.py` | Activated when deterministic checks insufficient, temp=0 |
| Calculate L1-L4 metrics | `engine/metrics.py` | Trigger accuracy, delta, step adherence, stability (std dev) |
| Cross-model drift | `engine/drift.py` | Severity: none/low/moderate/high based on variance thresholds |
| Dialogue evaluation | `engine/dialogue_evaluator.py` + `dialogue_runner.py` | Multi-turn skill assessment |
| Replay mode | `engine/replay.py` | Regression testing with historical session data |
| LLM prompt templates | `prompts/` | .md files with system prompts for judge, dialogue, drift, testgen |
| Eval schemas | `schemas/evals.schema.json` | Defines eval case structure |
| SkillSpec schema | `schemas/skillspec.schema.json` | Defines parsed skill model |
| API adapters | `adapters/` | Anthropic + OpenAI compatible interfaces via base protocol |
| Reports output | `results/` | Markdown + JSON per skill evaluated |

## CODE MAP
| Symbol | Type | Location | Role |
|--------|------|----------|------|
| `SkillSpec` | Pydantic model | `engine/analyzer.py:17` | Parsed skill semantic model |
| `WorkflowStep` | Pydantic model | `engine/analyzer.py:11` | Single workflow step in skill |
| `parse_skill_md()` | function | `engine/analyzer.py:30` | Main SKILL.md parser entry |
| `generate_evals()` | function | `engine/testgen.py` | Eval test generation |
| `Runner` | class | `engine/runner.py` | Eval execution engine |
| `Grader` | class | `engine/grader.py` | Output assertion checker |
| `calculate_metrics()` | function | `engine/metrics.py` | L1-L4 metric computation |
| `detect_drift()` | function | `engine/drift.py` | Cross-model drift analysis |

## CONVENTIONS
- **Pydantic** for all data models (SkillSpec, WorkflowStep, EvalResult)
- **Type annotations** on all function signatures
- **black** for formatting, **isort** for imports, **ruff** for linting
- **pytest** for testing, test files mirror module structure 1:1
- Prompt templates are `.md` files in `prompts/`, not Python strings
- JSON schemas in `schemas/` validate eval and SkillSpec structures
- Results: each skill gets 3 files — report.md, result.json, evals-cache.json

## ANTI-PATTERNS (THIS PROJECT)
- Skip Phase 1 self-review loop (generate → review → gap-fill)
- Run with-skill without without-skill baseline
- Ignore L4 stability (std dev) while focusing only on L2 delta
- Give PASS verdict when drift severity is high
- Modify eval cases after Phase 2 execution begins (integrity rule)

## UNIQUE STYLES
- **4-tier metrics**: L1 (trigger), L2 (delta), L3 (step adherence), L4 (stability std<=10%)
- **Drift severity thresholds**: none ≤0.10, low ≤0.20, moderate ≤0.35, high >0.35
- **Verdict logic**: PASS = L1≥90%, L2≥20%, L3≥85%, L4 std≤10%, drift none/low
- **Evaluator protocol**: adapters/ define LLM interface via base protocol, swap providers transparently
- **3 evaluation modes**: single (default), dialogue (multi-turn), replay (historical sessions)
- **Self-review loop**: testgen generates → reviews → fills gaps → reviews until coverage ≥ 90%

## COMMANDS
```bash
# Install dependencies
pip install -e .

# Run skill evaluation
skill-cert --skill /path/to/SKILL.md --models m1,m2 --output ./results/

# Dialogue mode (for orchestration skills)
skill-cert --skill /path/to/SKILL.md --mode dialogue --max-turns 10

# Replay mode (regression testing)
skill-cert --skill /path/to/SKILL.md --mode replay --session session.jsonl

# Run tests
pytest

# Run tests with coverage
pytest --cov=engine --cov=skill_cert --cov=adapters --cov-report=term-missing

# Format + lint
black . && isort . && ruff check .
```

## NOTES
- Project freshly extracted from monorepo — some paths may still reference old parent
- WSL environment — watch for line ending issues
- `results/` contains pre-existing eval outputs from prior runs (delphi-review, plan-eng-review, sprint-flow, test-specification-alignment)
- `templates/minimum-evals.json` is the eval fallback when generation fails completely
- Engine uses `markdown-it-py` for AST parsing, `pydantic` for models, `yaml` for frontmatter
- API keys expected via environment variables (no hardcoded secrets)
- Rate limiting and concurrency control built into runner
