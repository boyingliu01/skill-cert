# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] — 2026-06-03

Open issues resolution sprint — 9 issues fixed (3×P0 + 3×P1 + 3×P2).

### CLI Enhancements
- **#24** `--version` flag using importlib.metadata
- **REQ-P0-002** `--strict-schema` flag — reject SKILL.md on required field violations (SchemaValidationError)
- **REQ-P0-004** `--with-skill-lab`, `--with-deepeval` integration flags + `--envelope` custom thresholds

### Metrics Improvements
- **P1: L2 Normalized Gain** — Formula changed from `abs(with - without)` to `(with - without) / without`
- **P1: L5 Envelope Wiring** — EnvelopeChecker now integrated into L5 step efficiency scoring

### Dialogue Evaluation
- **P1: LLM-as-Judge** — `judge_with_llm()` method with structured scoring, heuristic fallback
- New `DialogueJudgeResult` class with per-dimension scores and reasoning

### New Modules
- **P2: Goal Change Testing** — `engine/goal_change.py` (AgentChangeBench style mid-turn adaptation)
- **P2: Golden Dataset** — `engine/golden_dataset.py` (50+ human-anchored test cases)
- **P2: SkillsBench Analysis** — `engine/skills_bench.py` (multi-skill cognitive overload detection)

## [0.2.0] — 2026-06-03

Comprehensive engine optimization: coverage improvements, new metrics, security expansion, and calibration framework.

### Coverage (T1-T3)
- **metrics.py** — Coverage 79% → 100%, fixed dead code in L5/L6 detail paths
- **reporter.py** — Coverage 80% → 100%, added suggestions/multi-skill/stress report paths
- **dialogue_runner.py** — Coverage 82% → 100%, added exception fallback paths

### LLM-as-Judge Enhancement (T4)
- **Failure Reasons** — Structured `failure_reasons` field in JudgeResult for actionable diagnostics
- **Position Debiasing** — Swap augmentation: evaluate both orderings, average scores to reduce bias

### L3 Trajectory Quality (T5)
- **Turn-Level Metrics** — `tool_call_accuracy` and `turn_relevance` per-turn scoring
- **Weighted Composite** — L3 = 0.5×step_coverage + 0.3×tool_call_accuracy + 0.2×turn_relevance

### L4 Multi-Trial Confidence Intervals (T6)
- **t-Distribution** — Manual t-table + Abramowitz & Stegun approximation (no scipy dependency)
- **Confidence Interval** — `num_trials` parameter, CI reporting, CV-based scoring

### Security Probes Expansion (T7)
- **19 → 52 Patterns** — Multi-language injection (CN/JP/ES), indirect injection, encoding bypass
- **New Category** — PRIVILEGE_ESCALATION (sudo su, --privileged, container escape)
- **Expanded Coverage** — Credential (kube/config, JWT, private keys), exfiltration (DNS tunnel, webhook)

### Dialogue Semantic Matching (T8)
- **SequenceMatcher** — Zero-dependency semantic similarity via `difflib.SequenceMatcher`
- **Hybrid Scoring** — Intent recognition: 0.6×semantic + 0.4×keyword; Output quality uses semantic overlap

### Cross-Model Uncertainty (T9)
- **CMP (Cross-Model Agreement)** — Agreement rate + pairwise agreement tracking
- **CME (Cross-Model Entropy)** — Coefficient of variation + max-min spread for pass rate uncertainty

### Golden Eval Set Calibration (T10)
- **Calibration Framework** — `GoldenEvalSet` + `CalibrationRunner` for human-anchored evaluation
- **Metrics** — Agreement rate, FPR, FNR, Cohen's Kappa (κ) for measuring auto-vs-human alignment

### Quality
- **651 tests** (+159 from 492), 1 skipped
- New modules: `engine/calibration.py`
- ruff clean on all modified files

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
