# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-05-14

Initial release of the skill-cert evaluation engine.

### Core Pipeline
- **Phase 0: Skill Parsing** — Regex + markdown-it-py AST parser for SKILL.md with LLM fallback, 8-dimension confidence scoring, and schema validation
- **Phase 1: Test Generation** — Auto-generate → review → gap-fill loop until coverage ≥ 90%, with templates/minimum-evals.json fallback
- **Phase 2: Cross-Validation Execution** — with-skill vs without-skill baseline comparison, deterministic assertions + LLM-as-judge (temp=0)
- **Phase 3: Progressive Gap-Fill** — Analyze weak areas, add targeted tests until convergence
- **Phase 4: Metrics (L1-L8)** — Full 8-tier metrics: trigger accuracy, delta, step adherence, stability, step efficiency, trajectory quality, cost efficiency, latency
- **Phase 5: Cross-Model Drift** — Pass-rate variance analysis across multiple LLM providers with severity classification (none/low/moderate/high)
- **Phase 6: Report Generation** — Markdown + JSON reports with verdict, metrics breakdown, drift analysis, security findings, cost analysis, and improvement suggestions

### Metrics
- **L1** Trigger Accuracy — eval_category='trigger' pass rate (≥90% threshold)
- **L2** With/Without Skill Delta — weighted score comparison (≥20% threshold)
- **L3** Step Adherence — workflow step coverage by passing evals (≥85% threshold)
- **L4** Execution Stability — std dev of deterministic assertion pass rates (≤10% threshold)
- **L5** Step Efficiency — envelope check scoring (passed: 1.0, 1violation: 0.7, 2+: 0.3)
- **L6** Trajectory Quality — dialogue mode only, turn relevancy + knowledge retention
- **L7** Cost Efficiency — token→$ conversion, cost delta, cost efficiency ratio (17 models across 5 providers)
- **L8** Latency — P50/P95/P99 request latency, with/without skill overhead, slow request detection

### Security
- **Security Scanning** — 19 probe patterns across 5 categories (INJ/EXF/DCMD/CRD/OBF), verdict PASS/WARN/BLOCK
- **Schema Enforcement** — Required Security Notes, Permissions, Scope sections with configurable strictness

### Advanced Features
- **Multi-Skill Conflict Detection** — Trigger overlap, prompt contamination, token overflow analysis
- **Stress Testing** — Concurrent fairness, memory tracking, scalability scoring
- **Reliability Tracking** — Error classification, retry statistics, graceful degradation reporting
- **Maintainability Scoring** — SKILL.md readability, completeness, freshness scoring
- **External Integration Framework** — BaseIntegration ABC with SkillLab/DeepEval providers, graceful degradation
- **Operating Envelope** — Steps/tokens/timeout/tool_calls limit enforcement
- **Real Token Tracking** — TokenUsage dataclass with real API counts (Anthropic, OpenAI)
- **Cross-Endpoint Fallback** — Secondary model endpoint when primary fails

### Evaluation Modes
- **Single Mode** (default) — All evals once per model
- **Dialogue Mode** — Multi-turn simulation with configurable turn limits
- **Replay Mode** — Historical session data (JSONL) regression testing

### LLM Providers
- **Anthropic** Claude adapter (Claude Sonnet 4.5, Opus 4, Haiku 4)
- **OpenAI-Compatible** adapter (OpenAI, Azure, local models)
- **Pricing Table** — 17 models: Anthropic (5), OpenAI (4), Qwen (4), DeepSeek (2), Gemini (2), Whalecloud LOCAL (2)

### CLI
- `--skill` Primary skill file parameter
- `--models` Model specification (single: `name` or multi: `name=url,key|name2=url,key`)
- `--mode` Evaluation mode: single, dialogue, replay
- `--max-turns` Dialogue turn limit
- `--session` Replay session file path
- `--runs` Multi-run count for L4 stability
- `--output-dir` Custom output directory
- Exit codes: 0 (PASS), 1 (FAIL), 2 (PASS_WITH_CAVEATS)
- Progress feedback: `[Phase X/7] ...` messages

### Quality
- **402 tests** across 26 test files, 83% coverage
- ruff for linting and formatting
- Pydantic v2 for all data models
- Type annotations on all function signatures

### Architecture
- Clean architecture: presentation (skill_cert/) → domain (engine/) → infrastructure (adapters/)
- architecture.yaml with configurable layer rules
- Circular dependency detection
- Zero hardcoded secrets
