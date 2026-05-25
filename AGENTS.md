# PROJECT KNOWLEDGE BASE

**Generated:** 2026-05-25
**Project:** skill-cert — AI Skill Evaluation Engine
**Version:** 0.1.0 (main: 33 commits since May 2026-05-01)

## OVERVIEW
Automated evaluation engine for AI skills (SKILL.md files). Parses arbitrary skill definitions via regex + AST (LLM fallback), generates eval tests via self-review loop (coverage ≥ 90%), executes with/without-skill baseline comparison across multiple LLM models, grades outputs via deterministic assertions + LLM-as-judge (temp=0), computes L1–L8 metrics (trigger accuracy → cost efficiency → latency), detects cross-model drift, security probes, multi-skill conflicts, reliability patterns, and maintainability scores, producing standardized PASS/FAIL verdicts.

## STRUCTURE
```
skill-cert/
├── engine/            # Core pipeline: parser, testgen, runner, grader, metrics, reporter, drift, dialogue, replay, simulator,
│                      # security_probes, envelope, integrations, reliability, maintainability, multi_skill, stress_test, stability, config
├── skill_cert/        # CLI entry point (cli.py)
├── adapters/          # LLM provider adapters: base protocol, anthropic_compat, openai_compat, pricing
├── prompts/           # LLM prompt templates (judge, dialogue, drift-detect, testgen, test-review, test-gap)
├── schemas/           # JSON schemas: evals.schema.json, skillspec.schema.json
├── templates/         # Eval fallback: minimum-evals.json
├── scripts/           # UAT utilities: run_uat.py, verify_uat.py
├── tests/             # pytest suite — 402 tests across 26 files, mirrors engine/modules 1:1
├── results/           # Output: {skill}-report.md, {skill}-result.json, {skill}-evals-cache.json
├── examples/          # Sample eval files (evals.json with assertion types)
├── docs/              # Project documentation (audit, evaluation review, v2 spec, plans)
├── pyproject.toml     # Python project config
├── SKILL.md           # This project's own skill definition
├── specification.yaml # 11 requirements (REQ-001 to REQ-011), 74 acceptance criteria
└── architecture.yaml  # Clean architecture layer definitions
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Parse SKILL.md → SkillSpec | `engine/analyzer.py` | Regex + markdown-it-py AST, LLM fallback, 8-dimension confidence scoring, schema validation |
| Validate SKILL.md schema | `engine/analyzer.py` | `_validate_schema()` checks Security Notes/Permissions/Scope/Description |
| Generate eval tests | `engine/testgen.py` | Generate → Review → Gap-fill loop until coverage >= 90%, fallback to minimum-evals.json |
| Execute with/without skill | `engine/runner.py` | Concurrency control, rate limiting, timeout, real token tracking, execution trace |
| Grade outputs (deterministic) | `engine/grader.py` | Assertion types: contains, not_contains, regex, starts_with, json_valid, weighted assertions |
| LLM-as-judge grading | `engine/grader.py` | Activated when deterministic checks insufficient, temp=0, binary judgment |
| Calculate L1-L8 metrics | `engine/metrics.py` | Trigger, delta, step adherence, stability, efficiency, trajectory, cost, latency |
| Cross-model drift | `engine/drift.py` | Severity: none/low/moderate/high based on pass-rate variance thresholds |
| Security scanning | `engine/security_probes.py` | 19 patterns, 5 categories (INJ/EXF/DCMD/CRD/OBF), verdict PASS/WARN/BLOCK |
| Operating envelope | `engine/envelope.py` | Steps/tokens/timeout/tool_calls limits with config-driven thresholds |
| External integrations | `engine/integrations.py` | BaseIntegration ABC + SkillLab/DeepEval providers, graceful degradation |
| Multi-skill conflicts | `engine/multi_skill.py` | Trigger overlap, prompt contamination, token overflow detection |
| Stress testing | `engine/stress_test.py` | Concurrency fairness, memory tracking, scalability scoring |
| Reliability tracking | `engine/reliability.py` | Error classification, retry stats, graceful degradation |
| Maintainability scoring | `engine/maintainability.py` | Readability, completeness, freshness scores for SKILL.md |
| Stability (multi-run) | `engine/stability.py` | L4 std dev execution stability with --runs flag |
| Dialogue evaluation | `engine/dialogue_evaluator.py` + `dialogue_runner.py` | Multi-turn skill assessment |
| Replay mode | `engine/replay.py` | Regression testing with historical session data |
| Simulation | `engine/simulator.py` | LLM behavior simulation for testing without live API |
| Cost efficiency (L7) | `engine/metrics.py` + `adapters/pricing.py` | Token→$ conversion, 17 models across 5 providers, cost delta, budget |
| Latency metrics (L8) | `engine/metrics.py` | P50/P95/P99, with/without skill overhead, slow request detection |
| Configuration | `engine/config.py` | Env vars, YAML config, CLI arg validation |
| Report generation | `engine/reporter.py` | Markdown + JSON reports with verdict, metrics, drift, cost, latency |
| LLM prompt templates | `prompts/` | .md files with system prompts for judge, dialogue, drift, testgen |
| Model pricing | `adapters/pricing.py` | Anthropic, OpenAI, Qwen, DeepSeek, Gemini, Whalecloud LOCAL |
| API adapters | `adapters/` | Base protocol, Anthropic, OpenAI-compatible, cross-endpoint fallback |
| Reports output | `results/` | Markdown + JSON per skill evaluated |

## CODE MAP
| Symbol | Type | Location | Role |
|--------|------|----------|------|
| `SkillSpec` | Pydantic model | `engine/analyzer.py:17` | Parsed skill semantic model |
| `WorkflowStep` | Pydantic model | `engine/analyzer.py:11` | Single workflow step in skill |
| `parse_skill_md()` | function | `engine/analyzer.py:30` | Main SKILL.md parser entry |
| `EvalGenerator` | class | `engine/testgen.py` | Generate → review → gap-fill loop |
| `Runner` | class | `engine/runner.py` | Eval execution engine (with/without skill) |
| `Grader` | class | `engine/grader.py` | Output assertion checker |
| `MetricsCalculator` | class | `engine/metrics.py` | L1-L8 metric computation |
| `detect_drift()` | function | `engine/drift.py` | Cross-model drift analysis |
| `SecurityScanner` | class | `engine/security_probes.py` | 19-pattern security probe suite |
| `EnvelopeChecker` | class | `engine/envelope.py` | Operating envelope checker |
| `ReliabilityTracker` | class | `engine/reliability.py` | Error classification + retry stats |
| `readability_score()` | function | `engine/maintainability.py` | SKILL.md readability scoring |
| `MultiSkillAnalyzer` | class | `engine/multi_skill.py` | Multi-skill conflict detection |
| `StressTester` | class | `engine/stress_test.py` | Concurrency stress testing |
| `ModelPricing` | class | `adapters/pricing.py` | Token → $ cost conversion |

## CONVENTIONS
- **Pydantic** for all data models (SkillSpec, WorkflowStep, EvalResult)
- **Type annotations** on all function signatures
- **ruff** for formatting and linting (replaces black+isort)
- **pytest** for testing, test files mirror engine modules 1:1 — 402 tests, 83% coverage
- Prompt templates are `.md` files in `prompts/`, not Python strings
- JSON schemas in `schemas/` validate eval and SkillSpec structures
- Results: each skill gets 3 files — report.md, result.json, evals-cache.json

## ANTI-PATTERNS (THIS PROJECT)
- Skip Phase 1 self-review loop (generate → review → gap-fill)
- Run with-skill without without-skill baseline
- Ignore L4 stability (std dev) while focusing only on L2 delta
- Give PASS verdict when drift severity is high
- Modify eval cases after Phase 2 execution begins (integrity rule)
- Use LLM-as-judge with temp > 0 (introduces nondeterminism in grading)
- Coverage < 70% and still execute evaluation (should block)
- Single-model evaluation (minimum 2 providers for drift detection)
- `as any`/`@ts-ignore` equivalent in Python (suppress type/lint errors)

## UNIQUE STYLES
- **8-tier metrics**: L1 (trigger), L2 (delta), L3 (step adherence), L4 (stability std≤10%), L5 (step efficiency), L6 (trajectory quality), L7 (cost efficiency), L8 (latency P50/P95/P99)
- **Drift severity thresholds**: none ≤0.10, low ≤0.20, moderate ≤0.35, high >0.35
- **Verdict logic**: PASS = L1≥90%, L2≥20%, L3≥85%, L4 std≤10%, drift none/low
- **Security scanning**: 5 categories (INJ/EXF/DCMD/CRD/OBF), verdict PASS/WARN/BLOCK, runs Phase 0.5
- **Self-review loop**: testgen generates → reviews → fills gaps → reviews until coverage ≥ 90%
- **3 evaluation modes**: single (default), dialogue (multi-turn), replay (historical sessions)
- **Multi-skill conflict detection**: trigger overlap, prompt contamination, token overflow
- **Pricing table**: 17 models across 5 providers (Anthropic, OpenAI, Qwen, DeepSeek, Gemini)
- **Evaluator protocol**: adapters/ define LLM interface via base protocol, cross-endpoint fallback
- **Triple threshold system** in testgen: coverage (0.9), degrade (0.7), block (0.7)
- **Maintainability score**: readability (line length, nesting, TODOs), completeness, freshness

## COMMANDS
```bash
# Install dependencies
pip install -e .

# Simplest: one skill, one model
skill-cert --skill /path/to/SKILL.md --models "m1=url,key" --output ./results/

# Multi-model drift detection
skill-cert --skill /path/to/SKILL.md --models "m1=url,key|m2=url,key" --output ./results/

# Dialogue mode (for orchestration skills)
skill-cert --skill /path/to/SKILL.md --mode dialogue --max-turns 10

# Replay mode (regression testing)
skill-cert --skill /path/to/SKILL.md --mode replay --session session.jsonl

# Multi-run for L4 stability
skill-cert --skill /path/to/SKILL.md --models ... --runs 5

# Run tests
pytest

# Run tests with coverage
pytest --cov=engine --cov=skill_cert --cov=adapters --cov-report=term-missing

# Format + lint
ruff check . && ruff format .
```

## NOTES
- 402 tests pass, 1 skipped, 83% coverage (cli.py at 35% is the main gap)
- REQ-011 (cost evaluation) implemented — L7 metric with pricing table
- L8 latency metrics implemented (P50/P95/P99)
- Security probes: 19 patterns, 5 categories — integrated into eval pipeline
- Multi-skill conflict detection: trigger overlap, prompt contamination, token overflow
- Stress testing: concurrency fairness, memory tracking, scalability scoring
- Real token tracking: TokenUsage dataclass in adapters, runner uses real counts
- Cross-endpoint fallback for model adapter
- `results/` contains pre-existing eval outputs from prior runs
- `templates/minimum-evals.json` is the eval fallback when generation fails completely
- Engine uses `markdown-it-py` for AST parsing, `pydantic` for models, `yaml` for frontmatter
- API keys expected via environment variables (no hardcoded secrets)
- Rate limiting and concurrency control built into runner
- WSL environment — watch for line ending issues
