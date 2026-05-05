# Skill-Cert Full Sprint: CLI + Latency + Token Tracking

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Wire the full 6-phase CLI pipeline, add P50/P95 latency metrics, and replace token approximation with real API usage tracking.

**Architecture:** Three parallel enhancement threads that merge into one cohesive pipeline. CLI wires existing engine modules end-to-end. Latency and token tracking both require runner.py instrumentation but are otherwise independent.

**Tech Stack:** Python, argparse, pytest, Pydantic v2, adapters (Anthropic/OpenAI-compat), engine/ modules

---

## Task 1: Baseline — Code Quality (P1 Pre-existing)

**Files:**
- Modify: `engine/grader.py` (`.dict()` → `.model_dump()` — already done, verify)
- Modify: `*` (remaining mypy/type fixes)

**Step 1:** Verify existing 265 tests pass, note any remaining type issues.
**Step 2:** `pytest → pass`, `ruff check engine/ → clean`
**Step 3:** Commit checkpoint if changes made.

---

## Task 2: REQ-010 — CLI Full Pipeline Wire (P0)

**Files:**
- Modify: `skill_cert/cli.py` (full pipeline wire)
- Test: `tests/test_cli_pipeline.py` (new, 15+ tests)

**Step 1: Add CLI flags**

```python
# Extend argparse in cli.py:
parser.add_argument("--mode", choices=["single", "dialogue", "replay"], default="single")
parser.add_argument("--max-turns", type=int, default=5)
parser.add_argument("--session", type=str, default=None)
parser.add_argument("--runs", type=int, default=1)
parser.add_argument("--output-dir", type=str, default="./results")
```

**Step 2: Wire Phase 1-5** — Replace stub `"Remaining phases require model API access"` with real pipeline calls:
1. `parse_skill_md()` → Phase 0 ✅ already works
2. `generate_evals()` → Phase 1
3. `runner.run_with_skill()` + `runner.run_without_skill()` → Phase 2
4. `grader.grade_all()` → Phase 3
5. `calculate_metrics()` → Phase 4
6. `detect_drift()` → Phase 5
7. `generate_report()` → Phase 6

**Step 3: Exit codes** — `sys.exit(0)` pass, `sys.exit(1)` fail, `sys.exit(2)` pass_with_caveats

**Step 4: Progress feedback** — `[Phase 1/6] Generating eval cases...`

**Step 5: Mode dispatch** — dialogue → `dialogue_runner()`, replay → `replay_runner(session)`, single → standard runner

**Step 6:** Write CLI integration tests (mocked).
**Step 7:** `pytest → pass`, `skill-cert --skill ./SKILL.md --models LOCAL/Qwen3.5-122B-A10B --output ./results/` → full report
**Step 8:** Commit.

---

## Task 3: Latency Metrics (P1)

**Files:**
- Modify: `engine/metrics.py` (add latency calculations)
- Modify: `engine/reporter.py` (add latency section)
- Modify: `engine/runner.py` (aggregate timing)
- Test: `tests/test_metrics_latency.py` (new)

**Step 1: Latency stats**

```python
# In metrics.py:
def calculate_latency(execution_times: list[float]) -> dict:
    times = sorted(execution_times)
    n = len(times)
    return {
        "p50": times[n // 2],
        "p95": times[int(n * 0.95)],
        "p99": times[int(n * 0.99)] if n > 1 else times[0],
        "mean": sum(times) / n,
        "min": times[0],
        "max": times[-1],
        "count": n,
        "slow": [t for t in times if t > 30.0],
    }
```

**Step 2: Latency overhead** — `overhead_pct = (t_with - t_without) / max(t_without, 0.001) * 100`

**Step 3: Reporter** — Add Latency Analysis section to markdown output.

**Step 4:** Write tests.
**Step 5:** `pytest → pass`
**Step 6:** Commit.

---

## Task 4: Real Token Tracking (P2)

**Files:**
- Modify: `adapters/base.py` (LLMResponse + TokenUsage dataclass)
- Modify: `adapters/anthropic_compat.py` (extract usage)
- Modify: `adapters/openai_compat.py` (extract usage)
- Modify: `engine/runner.py` (use real counts)
- Test: `tests/test_token_tracking.py` (new)

**Step 1: TokenUsage dataclass**

```python
@dataclass
class TokenUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int
```

**Step 2: LLMResponse extension**

```python
@dataclass
class LLMResponse:
    text: str
    token_usage: TokenUsage | None = None
    latency_ms: float = 0.0
```

**Step 3: Anthropic adapter**

```python
# Extract from Anthropic API response.usage
```

**Step 4: OpenAI adapter**

```python
# Extract from OpenAI API response.usage
```

**Step 5: Runner** — Replace `len(response.split())` with real token_usage.

**Step 6:** Wire token_budget in envelope.py to real counts.

**Step 7:** Write tests.
**Step 8:** `pytest → pass`
**Step 9:** Commit.

---

## Task 5: Integration + Final Verification

**Files:**
- Full `pytest` suite (300+ tests expected)
- `ruff check . --fix`

**Step 1:** End-to-end test with mocked adapters.
**Step 2:** Full suite: `pytest → all pass`
**Step 3:** Lint: `ruff check . → clean`
**Step 4:** Smoke test: `skill-cert --skill ./SKILL.md --models LOCAL/Qwen3.5-122B-A10B`
**Step 5:** Commit.
