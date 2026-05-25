# Skill-Cert: AI Skill Evaluation Engine

**Automated evaluation engine for AI agent skills (SKILL.md files).**

Self-parse → self-generate tests → self-execute → self-evaluate → produce PASS/FAIL verdicts.

---

## What It Does

Skill-Cert takes any `SKILL.md` file — the instruction format used by Claude Code, Codex, OpenCode, Cursor, and other AI coding agents — and evaluates it through a rigorous 6-phase pipeline:

1. **Parse** — Extract semantic structure from SKILL.md (regex + AST, LLM fallback)
2. **Generate** — Auto-create eval test cases, then review and gap-fill until coverage ≥ 90%
3. **Execute** — Run all evals in both *with-skill* and *without-skill* modes for baseline comparison
4. **Grade** — Deterministic assertion checks (contains, regex, json_valid) + optional LLM-as-judge
5. **Measure** — Calculate L1–L4 metrics: trigger accuracy, delta, step adherence, stability
6. **Detect Drift** — Run across multiple LLM models, detect performance variance, flag cross-model failures

The result: a standardized report with a **PASS / PASS_WITH_CAVEATS / FAIL** verdict backed by quantitative evidence.

---

## Quick Start

```bash
# Install
pip install -e .

# Evaluate a skill on a single model
skill-cert --skill path/to/SKILL.md --models claude-sonnet-4-5 --output ./results/

# Compare across multiple models
skill-cert --skill path/to/SKILL.md --models claude-sonnet-4-5,gpt-5.1 --output ./results/

# Dialogue mode (for orchestration skills)
skill-cert --skill path/to/SKILL.md --mode dialogue --max-turns 10

# Replay mode (regression testing)
skill-cert --skill path/to/SKILL.md --mode replay --session session.jsonl

# Multi-run for stability metrics
skill-cert --skill path/to/SKILL.md --models ... --runs 5
```

---

## Metrics

Skill-Cert uses an 8-tier metric system:

| Tier | Name | What It Measures | Threshold |
|------|------|-----------------|-----------|
| **L1** | Trigger Accuracy | Does the agent know *when* to use the skill? | ≥ 90% |
| **L2** | Output Delta | Does the skill actually *improve* output quality? | ≥ 20% |
| **L3** | Step Adherence | Does the agent *follow* the skill's workflow? | ≥ 85% |
| **L4** | Stability | How *consistent* are results across runs? | std ≤ 10% |
| **L5** | Step Efficiency | Does the skill operate within resource envelopes? | All pass |
| **L6** | Trajectory Quality | Is the multi-turn dialogue coherent? (dialogue mode only) | N/A |
| **L7** | Cost Efficiency | Token → $ conversion, cost delta with/without skill | ≤ budget |
| **L8** | Latency | P50/P95/P99 request latency, with/without overhead | No slow req |

L1 and L2 measure the skill's **effectiveness**. L3 and L4 measure the skill's **reliability**. L7 and L8 measure **efficiency**.

### Security Scanning

Built-in security detection runs as Phase 0.5 (after parse, before eval generation):
- **5 categories**: Injection (INJ), Exfiltration (EXF), Dangerous Commands (DCMD), Credential Access (CRD), Obfuscation (OBF)
- **19 probe patterns** with severity classification (CRITICAL/HIGH/MEDIUM/LOW)
- **Verdict**: PASS / WARN / BLOCK — BLOCK verdict causes immediate FAIL

### Multi-Skill Conflict Detection

When multiple skills load simultaneously, the engine detects:
- **Trigger overlap** — same trigger words activating different skills
- **Prompt contamination** — shared workflow steps, anti-patterns, or output formats
- **Token overflow** — combined skill content exceeding context budget

### Additional Capabilities

| Capability | Module | Description |
|-----------|--------|-------------|
| **Stress Testing** | `stress_test.py` | Concurrent fairness, memory tracking, scalability scoring |
| **Reliability Tracking** | `reliability.py` | Error classification, retry statistics, graceful degradation |
| **Maintainability** | `maintainability.py` | SKILL.md readability, completeness, freshness scoring |
| **External Integrations** | `integrations.py` | SkillLab + DeepEval providers with graceful degradation |
| **Operating Envelope** | `envelope.py` | Steps/tokens/timeout/tool_calls limit enforcement |
| **Real Token Tracking** | `adapters/` | TokenUsage dataclass with real API counts (not approximations) |
| **Cost Analysis** | `adapters/pricing.py` | 17 models across 5 providers: Anthropic, OpenAI, Qwen, DeepSeek, Gemini |

---

### Cross-Model Drift

The same eval suite runs against multiple LLM models. Variance in pass rates is classified as:

- **None** (≤0.10) — Consistent across models
- **Low** (≤0.20) — Minor differences, acceptable
- **Moderate** (≤0.35) — Significant variance, skill needs attention
- **High** (>0.35) — Skill fails across models, needs redesign

---

## Evaluation Modes

### Single Mode (default)
For simple skills — quick verification of basic functionality. Runs all evals once per model.

### Dialogue Mode
For orchestration/agent skills that involve multi-turn interactions. Simulates real conversational workflows with configurable turn limits.

### Replay Mode
For regression testing. Replays historical session data (JSONL format) through the skill's workflow and compares expected vs actual behavior.

---

## Project Structure

```
skill-cert/
├── engine/          # Core pipeline: parser, testgen, runner, grader, metrics, reporter, drift,
│                    # dialogue, replay, simulator, security_probes, envelope, integrations,
│                    # reliability, maintainability, multi_skill, stress_test, stability, config
├── skill_cert/      # CLI entry point (cli.py)
├── adapters/        # LLM provider adapters (Anthropic, OpenAI-compatible) + pricing table
├── prompts/         # LLM prompt templates (judge, dialogue, drift, testgen, test-review, test-gap)
├── schemas/         # JSON schemas for eval cases and SkillSpec
├── templates/       # Fallback eval template (minimum-evals.json)
├── tests/           # pytest suite — 402 tests, mirrors engine/ modules 1:1
└── results/         # Output directory: {skill}-report.md, {skill}-result.json
```

### Clean Architecture

Skill-Cert follows clean architecture with explicit layer boundaries:

```
skill_cert/ (presentation — CLI)
  → engine/ (domain — core pipeline)
  → adapters/ (infrastructure — LLM APIs)
prompts/schemas/templates/ (support — reference data)
```

---

## Development

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

---

## API Keys

Skill-Cert requires API keys to call LLM providers during evaluation. Set them as environment variables:

```bash
# Anthropic
export ANTHROPIC_API_KEY=sk-ant-...

# OpenAI-compatible
export OPENAI_API_KEY=sk-...
export OPENAI_BASE_URL=https://api.openai.com/v1
```

No hardcoded secrets. No API keys committed to the repository.

---

## Verdict Logic

| Verdict | Conditions |
|---------|-----------|
| **PASS** | L1 ≥ 90%, L2 ≥ 20%, L3 ≥ 85%, L4 std ≤ 10%, drift none/low |
| **PASS_WITH_CAVEATS** | Core metrics pass, but drift is moderate |
| **FAIL** | Any core metric fails, or drift is high |

---

## License

This project is licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.
