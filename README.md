# Skill-Cert: AI Skill Evaluation Engine

> Automated evaluation engine for AI agent skills (SKILL.md files).

Skill-Cert takes any `SKILL.md` file — the instruction format used by Claude Code, Codex, OpenCode, Cursor, and other AI coding agents — and evaluates it through a rigorous automated pipeline. It parses skill structure, generates test cases, executes with-skill vs without-skill comparisons, computes L1-L8 metrics, detects cross-model drift, and produces standardized PASS / PASS_WITH_CAVEATS / FAIL verdicts.

In one sentence:

> Skill-Cert turns "does this skill actually work?" from a subjective feeling into repeatable, quantifiable, comparable evaluation results.

[English](README.md) | [简体中文](README.zh.md)

---

## Table of Contents

- [1. Why Skill-Cert?](#1-why-skill-cert)
- [2. What It Does](#2-what-it-does)
- [3. Core Philosophy](#3-core-philosophy)
- [4. Evaluation Pipeline](#4-evaluation-pipeline)
- [5. Architecture](#5-architecture)
- [6. Usage](#6-usage)
- [7. Configuration](#7-configuration)
- [8. Development](#8-development)
- [9. Limitations & Caveats](#9-limitations--caveats)
- [10. License](#10-license)

---

## 1. Why Skill-Cert?

Teams write Skills for AI coding agents all the time — code review skills, security audit skills, documentation skills, debugging skills, PR workflows, browser QA, project-specific conventions.

But after writing a Skill, you face several problems:

### 1.1 You don't know if the Skill actually works

The Skill looks thorough on paper. But does the model trigger it in the right scenarios? Does it follow the workflow? Is the output actually better than without the Skill?

Without evaluation, you're relying on a few manual trials. Conclusions are easily skewed by sample selection, model state, and reviewer subjectivity.

### 1.2 You don't know if the Skill is stable

Does the same Skill perform consistently across Claude, GPT, Qwen, DeepSeek, and Gemini? Do multiple runs produce stable results? Is the Skill only effective on one model and useless on others?

These require systematic cross-model, cross-run evaluation.

### 1.3 You don't know if the Skill is safe

A Skill is essentially high-priority operational guidance for the model. If it contains dangerous commands, credential access, prompt injection, or data exfiltration instructions, it poses a security risk.

Skill-Cert runs security scanning before evaluation to catch risks early.

### 1.4 You don't know the cost and latency impact

Skills typically increase context length, tool calls, and reasoning steps. This may improve output quality but also increase cost and response time.

Skill-Cert tracks tokens, cost, and latency, and evaluates whether the benefit justifies the overhead.

---

## 2. What It Does

Skill-Cert takes a `SKILL.md` file and runs a complete evaluation pipeline:

```
SKILL.md
  ↓
Parse skill structure
  ↓
Security scan
  ↓
Auto-generate eval tests
  ↓
Self-review + gap-fill
  ↓
with-skill / without-skill execution
  ↓
Assertion grading + LLM-as-judge
  ↓
L1-L8 metrics calculation
  ↓
Cross-model drift detection
  ↓
Markdown + JSON report
```

Output:

- `{skill}-report.md` — human-readable evaluation report
- `{skill}-result.json` — machine-readable structured results
- `{skill}-evals-cache.json` — eval cases and execution cache

---

## 3. Core Philosophy

Skill-Cert's core assumption:

> A good Skill shouldn't just "look reasonable" — it must demonstrably improve model performance on real tasks.

Evaluation isn't about checking the `SKILL.md` text. It's about answering four questions:

| Question | Metric |
|---|---|
| Does the model know *when* to use this Skill? | L1 Trigger Accuracy |
| Does the Skill actually *improve* results? | L2 Output Delta |
| Does the model *follow* the Skill's workflow? | L3 Step Adherence |
| Are results *stable* across runs and models? | L4 Stability / Drift |

Beyond these, we extend to efficiency, security, cost, latency, and multi-turn dialogue quality.

---

## 4. Evaluation Pipeline

### Phase 0: Skill Parsing

Implementation: `engine/analyzer.py` — `SkillSpec`, `WorkflowStep`, `parse_skill_md()`.

Skill-Cert reads `SKILL.md` and extracts a structured semantic model (`SkillSpec`):

- `name`, `description`, triggers
- workflow steps, anti-patterns
- output format, examples
- content length, parse method, parse confidence

Parsing methods:

1. YAML frontmatter extraction
2. Markdown AST parsing (via `markdown-it-py`)
3. Regex-based section extraction
4. LLM-assisted fallback when needed

An 8-dimension confidence score is computed: frontmatter(0.30) + workflow(0.25) + headings(0.15) + anti-patterns(0.10) + output-format(0.08) + triggers(0.07) + examples(0.05) + bonus(0.05). Low confidence flags the results as unreliable.

### Phase 0.5: Security Scanning

Implementation: `engine/security_probes.py` — `SecurityScanner`.

Security scanning runs before test generation. It checks 5 categories:

| Category | Meaning |
|---|---|
| INJ | Prompt Injection |
| EXF | Data Exfiltration |
| DCMD | Dangerous Commands |
| CRD | Credential Access |
| OBF | Obfuscation |

80 built-in probe patterns across 6 categories (INJ/EXF/DCMD/CRD/OBF/PRIV_ESC). Results: PASS / WARN / BLOCK. A BLOCK verdict causes immediate evaluation failure.

### Phase 1: Auto-Generate Eval Tests

Implementation: `engine/testgen.py` — `EvalGenerator`, fallback: `templates/minimum-evals.json`.

Skill-Cert auto-generates evaluation test cases from `SkillSpec`. Generation is not one-shot — it's a self-review loop:

```
Generate initial tests → Review coverage → Identify gaps → Fill gaps → Re-review → until coverage >= 90%
```

Coverage includes: trigger cases (should/should-not trigger), workflow step cases, anti-pattern cases, output format cases, security/robustness cases.

Key thresholds:

| Threshold | Meaning |
|---|---|
| coverage target = 90% | Ideal coverage |
| coverage degrade = 70% | Below this, degrade |
| coverage block = 70% | Too low, block evaluation |

If generation fails, `minimum-evals.json` is used as a fallback.

### Phase 2: With-Skill / Without-Skill Execution

Implementation: `engine/runner.py` — `EvalRunner`.

The core insight: don't just look at Skill output — run a controlled experiment:

```
Same eval suite
  ├── without-skill: model without Skill loaded
  └── with-skill: model with Skill loaded
```

Then compare the two sets of results. If the model can already do the task well, the Skill adds no value. Only when with-skill significantly outperforms without-skill does the Skill demonstrate real improvement.

The Runner handles: concurrent execution, rate limiting, timeouts, token tracking, security scanning, operating envelope checks, partial failure preservation.

Default limits:

| Item | Default |
|---|---|
| max steps | 20 |
| max tool calls | 15 |
| token budget | 50,000 |
| timeout | 300s |
| max concurrency | 5 |
| rate limit | 60 RPM |

### Phase 3: Grading

Implementation: `engine/grader.py` — `Grader`, `JudgeResult`, `EvalAssertion`.

Two grading approaches:

#### Deterministic Assertions

Supports `contains`, `not_contains`, `regex`, `starts_with`, `json_valid`. Weighted: Normal(1), Important(2), Critical(3). Deterministic assertions are stable, cheap, and repeatable.

#### LLM-as-Judge

For complex behaviors (e.g., "did the model make a reasonable architectural trade-off?"), deterministic assertions may be insufficient. Skill-Cert can enable LLM-as-judge. Constraints: temperature must be 0, only used when deterministic checks are insufficient, L4 stability calculation excludes LLM judge results to avoid randomness.

### Phase 4: L1-L8 Metrics

Implementation: `engine/metrics.py` — `MetricsCalculator`.

8-tier metric system:

| Tier | Name | Measures | Threshold |
|---|---|---|---|
| L1 | Trigger Accuracy | Does the model know when to use the Skill? | >= 90% |
| L2 | Output Delta | Does with-skill outperform without-skill? | >= 20% |
| L3 | Step Adherence | Does the model follow the workflow? | >= 85% |
| L4 | Stability | Are results consistent across runs? | std <= 10% |
| L5 | Step Efficiency | Within step/token/tool call limits? | All pass |
| L6 | Trajectory Quality | Is multi-turn dialogue coherent? | dialogue mode |
| L7 | Cost Efficiency | Is the cost justified? | Under budget |
| L8 | Latency | Is latency acceptable? | No slow requests |

L1/L2 measure effectiveness. L3/L4 measure reliability. L5/L7/L8 measure efficiency. L6 measures multi-turn interaction quality.

### Phase 5: Cross-Model Drift Detection

Implementation: `engine/drift.py` — `DriftDetector`.

Skill-Cert runs the same eval suite across multiple models and compares pass rate variance.

Drift severity:

| Level | Variance | Meaning |
|---|---|---|
| none | <= 0.10 | Consistent |
| low | <= 0.20 | Minor, acceptable |
| moderate | <= 0.35 | Significant, needs attention |
| high | > 0.35 | Unstable, cannot release |

Verdict impact: none/low → no effect on PASS, moderate → downgrade to PASS_WITH_CAVEATS, high → FAIL.

### Phase 6: Report Generation

Implementation: `engine/reporter.py` — `Reporter`.

Two output formats:

**Markdown report**: human-readable, includes executive summary, verdict, overall score, L1-L8 metrics, drift analysis, security scan, cost analysis, latency analysis, improvement suggestions, config summary.

**JSON report**: machine-readable structured data:

```json
{
  "verdict": "PASS",
  "overall_score": 0.82,
  "metrics": {
    "l1_trigger_accuracy": 0.90,
    "l2_with_without_skill_delta": 0.25,
    "l3_step_adherence": 0.88,
    "l4_execution_stability": 0.93
  },
  "drift_analysis": {
    "highest_severity": "none",
    "average_variance": 0.0,
    "overall_verdict": "PASS"
  },
  "evaluation_coverage": {
    "total_evaluations": 207,
    "avg_pass_rate": 1.0
  }
}
```

### Extended Capabilities

| Capability | Module | Description |
|---|---|---|
| Multi-Skill Conflict Detection | `multi_skill.py` | Trigger overlap, prompt contamination, token overflow |
| Stress Testing | `stress_test.py` | Concurrency fairness, memory tracking, scalability scoring |
| Reliability Tracking | `reliability.py` | Error classification, retry stats, graceful degradation |
| Maintainability Scoring | `maintainability.py` | SKILL.md readability, completeness, freshness |
| External Integrations | `integrations.py` | SkillLab / DeepEval providers (graceful degradation) |
| Operating Envelope | `envelope.py` | Steps/tokens/timeout/tool_calls limit enforcement |
| Cost Analysis | `adapters/pricing.py` | 17 models across 6 provider families |
| OTel Telemetry | `engine/observability.py` | SessionTelemetry, record_trace, session summary |
| Token Ledger | `engine/token_ledger.py` | Real-time token usage tracking (not approximations) |

---

## 5. Architecture

Skill-Cert follows Clean Architecture with explicit layer boundaries:

```
skill_cert/       Presentation layer: CLI entry
    ↓
engine/           Domain layer: core evaluation logic
    ↓
adapters/         Infrastructure layer: LLM provider adapters
    ↓
prompts/
schemas/
templates/        Support layer: prompts, schemas, templates
```

### 5.1 Presentation: CLI Layer

Location: `skill_cert/cli/`. Responsibilities: parse CLI arguments, load configuration, invoke core pipeline, emit exit codes, generate report files. Entry point: `main.py`, config wizard: `setup.py`.

### 5.2 Domain: Core Evaluation Layer

Location: `engine/`.

| File | Responsibility |
|---|---|
| `analyzer.py` | Parse SKILL.md into SkillSpec |
| `testgen.py` | Auto-generate eval tests |
| `runner.py` | Execute with-skill / without-skill |
| `grader.py` | Grade model outputs |
| `metrics.py` | Calculate L1-L8 metrics |
| `drift.py` | Cross-model drift detection |
| `reporter.py` | Generate Markdown / JSON reports |
| `security_probes.py` | Security scanning |
| `envelope.py` | Operating envelope checks |
| `config.py` | Configuration loading and validation |
| `dialogue_evaluator.py` | Multi-turn dialogue evaluation |
| `dialogue_runner.py` | Dialogue execution with OTel trace recording |
| `replay.py` | Historical session replay |
| `simulator.py` | LLM behavior simulation for testing |
| `multi_skill.py` | Multi-skill conflict detection |
| `stress_test.py` | Stress testing |
| `reliability.py` | Reliability tracking |
| `maintainability.py` | SKILL.md maintainability scoring |
| `skills_bench.py` | Multi-skill cognitive overload detection |
| `calibration.py` | Golden eval set calibration (Cohen's Kappa) |
| `stability.py` | Execution stability analysis |
| `integrations.py` | SkillLab / DeepEval external integrations |
| `observability.py` | OTel GenAI session telemetry |
| `token_ledger.py` | Real-time token usage tracking |
| `trigger_accuracy_eval.py` | L1 trigger accuracy evaluation |
| `trajectory_evaluator.py` | L6 trajectory quality evaluation |
| `adversarial.py` | Adversarial testing support |
| `gotchas_flywheel.py` | Gotcha patterns accumulation |
| `progressive_disclosure.py` | Progressive disclosure evaluation |
| `deadline.py` | Global deadline enforcement |
| `constants.py` | Shared constants and defaults |
| `report_models.py` | Report data models |
| `trace_models.py` | Telemetry trace data models |

### 5.3 Infrastructure: Model Adapter Layer

Location: `adapters/base.py`, `adapters/anthropic_compat.py`, `adapters/openai_compat.py`, `adapters/pricing.py`.

Responsibilities: define unified LLM calling protocol, adapt Anthropic / OpenAI-compatible APIs, track real token usage, compute cost from pricing table.

Pricing supports multiple model families: Anthropic, OpenAI, Qwen, DeepSeek, Gemini.

### 5.4 Support: Templates and Schemas

Location: `prompts/`, `schemas/`, `templates/`.

Responsibilities: LLM judge prompt, testgen prompt, test-review prompt, test-gap prompt, eval JSON schema, SkillSpec schema, minimum eval fallback template.

---

## 6. Usage

### 6.1 Installation

```bash
pip install -e .
```

Development mode:

```bash
pip install -e ".[dev]"
```

### 6.2 Single-Model Evaluation

```bash
skill-cert --skill path/to/SKILL.md \
  --models "m1=https://api.example.com/v1,$API_KEY" \
  --output ./results/
```

Best for: quick check if a Skill is functional, local debugging, generating a preliminary report.

### 6.3 Multi-Model Drift Detection

```bash
skill-cert --skill path/to/SKILL.md \
  --models "m1=url,key|m2=url,key" \
  --output ./results/
```

Best for: pre-release cross-model stability verification, comparing provider performance, discovering model dependencies.

### 6.4 Dialogue Mode

```bash
skill-cert --skill path/to/SKILL.md \
  --mode dialogue \
  --max-turns 10
```

Best for: Orchestration Skills, Debug Skills, QA Skills, Code Review Skills — any Skill requiring multi-turn decision-making.

### 6.5 Replay Regression Testing

```bash
skill-cert --skill path/to/SKILL.md \
  --mode replay \
  --session session.jsonl
```

Best for: historical session replay, before/after Skill change comparison, regression prevention.

### 6.6 Multi-Run Stability Testing

```bash
skill-cert --skill path/to/SKILL.md \
  --models "m1=url,key|m2=url,key" \
  --runs 5
```

Best for: computing L4 stability, detecting random variance, verifying Skill repeatability.

### 6.7 Stress Testing

```bash
skill-cert --skill path/to/SKILL.md \
  --stress \
  --stress-concurrency 50 \
  --stress-evals 100
```

Best for: validating high-concurrency behavior, detecting resource leaks, assessing scalability.

### 6.8 Verdict Logic

| Verdict | Conditions |
|---|---|
| **PASS** | L1 >= 90%, L2 >= 20%, L3 >= 85%, L4 std <= 10%, drift none/low |
| **PASS_WITH_CAVEATS** | Core metrics pass, but drift moderate |
| **FAIL** | Any core metric fails, or drift high, or coverage < 70% |

---

## 7. Configuration

### 7.1 Environment Variables

| Variable | Description |
|---|---|
| `SKILL_CERT_MODELS` | Model config: `name=url,key[,fallback]\|name2=url,key` |
| `SKILL_CERT_MAX_CONCURRENCY` | Max concurrency (default: 5) |
| `SKILL_CERT_RATE_LIMIT_RPM` | Rate limit RPM (default: 60) |
| `SKILL_CERT_TIMEOUT` | Timeout in seconds (default: 300) |
| `ANTHROPIC_API_KEY` | Anthropic API Key |
| `OPENAI_API_KEY` | OpenAI-compatible API Key |
| `OPENAI_BASE_URL` | OpenAI-compatible Base URL |

### 7.2 Config File

`~/.skill-cert/models.yaml`:

```yaml
models:
  - model_name: "qwen3.6-plus"
    base_url: "https://api.example.com/v1"
    api_key: "$API_KEY"
    fallback_model: "qwen3-coder-plus"
```

Priority: CLI args > environment variables > config file > defaults.

---

## 8. Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run with coverage
pytest --cov=engine --cov=skill_cert --cov=adapters --cov-report=term-missing

# Format and lint
ruff check . && ruff format .
```

**Conventions:**

- Pydantic v2 for all data models
- Type annotations on all function signatures
- ruff for linting and formatting
- pytest for testing (test files mirror engine/ module structure 1:1)
- Prompt templates are `.md` files, not Python strings
- No hardcoded secrets — API keys via environment variables or config file

**Project structure:**

```
skill-cert/
├── engine/          # Core pipeline: 33 modules — parser, testgen, runner, grader, metrics, reporter, drift,
│                    # dialogue_evaluator, dialogue_runner, replay, simulator, security_probes, envelope,
│                    # integrations, reliability, maintainability, multi_skill, stress_test, stability, config,
│                    # skills_bench, calibration, observability, token_ledger, trigger_accuracy_eval,
│                    # trajectory_evaluator, adversarial, gotchas_flywheel, progressive_disclosure,
│                    # deadline, constants, report_models, trace_models
├── skill_cert/cli/  # CLI entry (main.py, setup.py)
├── adapters/        # LLM provider adapters (Anthropic, OpenAI-compatible) + pricing table
├── prompts/         # LLM prompt templates (judge, dialogue, drift, testgen, test-review, test-gap)
├── schemas/         # JSON schemas (eval cases, SkillSpec)
├── templates/       # Fallback eval template (minimum-evals.json)
├── tests/           # pytest suite — 1134 tests, mirrors engine/ modules 1:1
└── results/         # Output: {skill}-report.md, {skill}-result.json, {skill}-evals-cache.json
```

Note: `skill_cert/cli.py` was deleted (shadowed by `cli/` package directory).

---

## 9. Limitations & Caveats

### 9.1 Known Limitations

**L3 Step Adherence granularity**

L3 only checks "are steps covered", not intermediate decision quality (tool call correctness, turn-level relevance). A Skill can pass L3 while producing poor intermediate decisions.

**L4 Stability needs more samples**

Single-run `--runs N` computes std dev. Industry standard typically requires 5-10 independent trials for reliable confidence intervals.

**LLM-as-judge lacks calibration**

Current LLM-as-judge lacks:
- Position bias handling (option order may affect judgment)
- Human-annotated calibration (golden eval set)
- Specific failure reasons (binary judgment only)

**Dialogue evaluation relies on word overlap**

Multi-turn dialogue evaluation currently over-relies on word overlap rather than semantic understanding, potentially missing or misclassifying quality issues.

**Security scan coverage is limited**

80 probe patterns across 6 categories (INJ/EXF/DCMD/CRD/OBF/PRIV_ESC). Industry recommendation is 100+ (e.g., SpecWeave). Some attack vectors may still be uncovered.

**Single-model evaluation is insufficient**

While multi-model is supported, single-model evaluation cannot detect model dependencies. A Skill may only work on one model.

### 9.2 Usage Notes

- **Requires API keys**: Skill-Cert depends on LLM API calls. At least one model's API key must be configured. Evaluation incurs API costs.
- **Evaluation takes time**: Full evaluation (multi-model, dialogue) may take tens of minutes to hours, depending on eval count and model response speed.
- **Results are model-dependent**: The same Skill may produce different results on different models. Use at least 2 models from different providers.
- **Not 100% accurate**: Automated evaluation cannot fully replace human review, especially for complex behavior judgment. Use Skill-Cert as a supplement to human review.
- **Coverage < 70% blocks evaluation**: If the Skill structure is too simple or vague, sufficient tests may not be generated, blocking evaluation.
- **Do not modify eval cases after execution**: Eval cases are locked after Phase 2 execution. Modification breaks evaluation integrity.

### 9.3 Industry Comparison Gaps

| Dimension | Current State | Industry Reference |
|---|---|---|
| L1 trigger granularity | Binary trigger judgment | CodeIF's 50 sub-dimensions |
| L3 trajectory quality | Missing turn-level quality metrics | Turn-level evaluation needed |
| L4 statistical method | Single-run std | 5-10 trial confidence intervals |
| Uncertainty detection | No CMP/CME | Cross-model perplexity/entropy |
| Calibration dataset | No human-annotated golden set | Human-annotated calibration needed |

---

## 10. License

This project is licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.
