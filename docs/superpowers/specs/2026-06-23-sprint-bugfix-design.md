# Sprint 2026-06-23 — Bug-Fix + Enhancement Design Document

**Branch:** `sprint/2026-06-23-01`
**Baseline:** 1134 tests pass, 0 failures
**Scope:** 11 GitHub issues (#54–#64) across P0/P1/P2 priorities

---

## 1. Executive Summary

This sprint addresses 3 foundational bugs (P0) that corrupt evaluation output, 5 critical fixes including a refactoring (P1), and 3 enhancements (P2). The P0 bugs are independent of each other and can be fixed in parallel. P1 issues depend on P0 stability. P2 issues are standalone.

**Key finding:** All 3 P0 bugs are data-flow disconnects — data is produced correctly during execution but lost before reaching the final report. The fixes are surgical, not architectural.

---

## 2. P0 — Foundational Bugs

### 2.1 Issue #54: eval_details 为空 (Phase 2 results not backfilled)

**Symptom:** `StructuredReport.eval_details` is always `[]` in JSON output.

**Root Cause Analysis:**

`Reporter.build_structured_report()` (`engine/reporter.py:767–830`) constructs a `StructuredReport` but never populates the `eval_details` field. The method receives `metrics`, `drift`, `config`, `token_analysis`, `observability`, and `session_telemetry` — but NOT the raw execution results from `EvalRunner`.

The execution results (per-eval dicts with `eval_id`, `eval_name`, `output`, `assertion_results`, etc.) exist in the pipeline but are never mapped to `EvalDetail` Pydantic models.

**Data flow gap:**
```
EvalRunner._run_single() → dict results  →  MetricsCalculator  → metrics dict
                                            ↘ (lost)            → StructuredReport.eval_details = []
```

**Fix approach:**

1. **`engine/reporter.py` — `Reporter.build_structured_report()`**: Add `eval_results: list[dict[str, Any]] | None = None` parameter.
2. **`engine/reporter.py` — new method `_build_eval_details()`**: Map raw execution result dicts to `EvalDetail` Pydantic models. Extract: `eval_id`, `eval_name`, `eval_category`, `model`, `phase` (from `run` field), `input`, `output`, `passed` (from `final_passed`), `score` (from `pass_rate`), `assertions` (map from `assertion_results`), `execution_time`, `tokens_used`, `cost`, `error`.
3. **`skill_cert/cli/evals.py` — `_generate_and_write_reports()`**: Pass execution results to `build_structured_report()`. The results are available from `runner.run_with_skill()` / `runner.run_without_skill()` return values, currently consumed by `MetricsCalculator` but not forwarded to the reporter.

**Files to change:**
- `engine/reporter.py`: Add `_build_eval_details()` method, update `build_structured_report()` signature
- `skill_cert/cli/evals.py`: Thread eval results through to `build_structured_report()`
- `tests/test_reporter.py`: Add tests for eval_details population

**Risk:** Low. Additive change — `eval_details` defaults to `[]` so existing behavior is preserved when param is not passed.

---

### 2.2 Issue #55: Token 成本计算失效 (model name = "unknown")

**Symptom:** All costs in reports are `$0.0000`.

**Root Cause Analysis — Three compounding failures:**

1. **`engine/runner.py:176`**: `model_name = getattr(model_adapter, "model_name", "unknown")` — when adapter doesn't expose `model_name`, defaults to `"unknown"`.

2. **`engine/runner.py:195`**: `cost = self._calc_cost(token_usage) if self.model_name else 0.0` — uses `self.model_name` (constructor param), NOT the per-call model_name from line 176. If `EvalRunner` is constructed without `model_name`, cost is always 0.0 even when the adapter has a valid model name.

3. **`adapters/pricing.py:36–37`**: `get_model_price()` does exact dict lookup: `self.models.get(model_name)`. Any name mismatch (e.g., `"qwen3.6-plus"` vs `"qwen3.6-plus-v2"`, or `"unknown"`) returns `None` → cost = 0.0.

**Fix approach:**

1. **`engine/runner.py:195`**: Change to use the per-call `model_name` from line 176, not `self.model_name`:
   ```python
   cost = self._calc_cost(token_usage, model_name) if model_name != "unknown" else 0.0
   ```
2. **`engine/runner.py:351–358`**: Update `_calc_cost()` to accept `model_name` parameter instead of using `self.model_name`.
3. **`adapters/pricing.py` — `ModelPricing.get_model_price()`**: Add fuzzy matching fallback:
   - Try exact match first (current behavior)
   - If no match, try prefix match (e.g., `"qwen3.6-plus-v2"` matches `"qwen3.6-plus"`)
   - If still no match, try case-insensitive match
   - Log a warning when falling back to fuzzy match
4. **`adapters/pricing.py` — `ModelPricing.calculate_cost()`**: Return a sentinel value or log warning when model is unrecognized, rather than silently returning 0.0.

**Files to change:**
- `engine/runner.py`: Fix model_name threading in `_run_single()` and `_calc_cost()`
- `adapters/pricing.py`: Add fuzzy matching in `get_model_price()`
- `tests/test_runner.py`: Add tests for cost calculation with fuzzy model names
- `tests/test_pricing.py`: Add tests for fuzzy matching

**Risk:** Low. Fuzzy matching is additive — exact matches still take priority.

---

### 2.3 Issue #56: LLM-as-Judge JudgeResult validation fails

**Symptom:** All LLM-as-Judge evaluations fall back to assertion-based grading.

**Root Cause Analysis — Two failure modes:**

1. **Pydantic validation error** (`engine/grader.py:315–322`): `JudgeResult.confidence` has `Field(ge=0.0, le=1.0)`. LLMs sometimes return `confidence: 1.5` or `confidence: -0.1`. Pydantic raises `ValidationError`, caught by the blanket `except Exception` at line 276, falling back to `_llm_judge_error_fallback()`.

2. **JSON parsing failure** (`engine/grader.py:302–309`): `_parse_judge_response()` handles ` ```json ` fences but doesn't handle: (a) LLM returning prose before/after JSON, (b) nested JSON strings (double-encoded), (c) JSON with trailing commas or comments. Any parse failure triggers the same fallback.

**Fix approach:**

1. **`engine/grader.py` — `_execute_llm_judge()`**: Pre-validate and clamp before Pydantic construction:
   ```python
   raw_confidence = float(judge_data.get("confidence", 0.5))
   clamped_confidence = max(0.0, min(1.0, raw_confidence))
   ```
2. **`engine/grader.py` — `_parse_judge_response()`**: Add robust JSON extraction:
   - Try current markdown fence stripping
   - Fallback: find outermost `{...}` pair in the response
   - Fallback: try `json.loads()` with `strict=False`
   - Log the raw response when all extraction attempts fail
3. **`engine/grader.py` — `_llm_judge_with_call()`**: Split the catch block:
   - Catch `json.JSONDecodeError` → retry once with explicit "respond ONLY with JSON" prompt
   - Catch `pydantic.ValidationError` → clamp and reconstruct
   - Catch other `Exception` → current fallback behavior

**Files to change:**
- `engine/grader.py`: Clamp confidence, improve JSON parsing, split exception handling
- `tests/test_grader.py`: Add tests for confidence clamping, malformed JSON, retry logic

**Risk:** Low. Clamping is strictly better than crashing. Retry adds one LLM call in failure cases only.

---

## 3. P1 — Critical Fixes + Refactoring

### 3.1 Issue #57: SKILL.md self-eval semantic 错位

**Symptom:** When evaluating skill-cert's own SKILL.md, eval cases test for agent-behavior patterns (triggers, workflow steps) instead of CLI tool patterns (flags, exit codes).

**Root Cause:**

`EvalGenerator._prepare_generation_prompt()` (`engine/testgen.py:271–315`) uses a single prompt template that assumes all skills are "agent behavior guides" — skills that tell an AI agent what to do. It generates eval cases checking for trigger conditions, workflow step coverage, and anti-pattern adherence.

But some SKILL.md files describe CLI tools (like skill-cert itself) where the relevant eval dimensions are: accepted flags, exit codes, output format, error handling — not "trigger accuracy" or "workflow step coverage."

**Fix approach:**

1. **`engine/analyzer.py` — `SkillSpec`**: Add `skill_type: str = "agent_guide"` field. Values: `"agent_guide"` | `"cli_tool"` | `"library"` | `"unknown"`.
2. **`engine/analyzer.py` — `parse_skill_md()`**: Detect skill type from content signals:
   - CLI tool: has `## Usage` with `skill-cert --flag` patterns, has `## Commands` or `## CLI Flags` sections, has argparse/click patterns
   - Library: has `## API` or `## Functions` sections, has import statements
   - Default: `"agent_guide"` (current behavior)
3. **`engine/testgen.py` — `_prepare_generation_prompt()`**: Branch on `skill_spec["skill_type"]`:
   - `"agent_guide"`: current prompt (unchanged)
   - `"cli_tool"`: generate eval cases for flag parsing, exit codes, output format, error messages
   - `"library"`: generate eval cases for API contracts, return types, error handling

**Files to change:**
- `engine/analyzer.py`: Add `skill_type` to `SkillSpec`, add detection logic in `parse_skill_md()`
- `engine/testgen.py`: Branch prompt on `skill_type`
- `tests/test_analyzer.py`: Add tests for skill_type detection
- `tests/test_testgen.py`: Add tests for CLI tool eval generation

**Risk:** Medium. New field is additive (defaults to current behavior). Prompt branching needs careful testing.

---

### 3.2 Issue #58: Testgen LLM JSON parse failures (coverage 82% → target 90%)

**Symptom:** Frequent JSON parse failures during eval generation cause fallback to minimal template (1–3 cases), dragging coverage to ~82%.

**Root Cause:**

`EvalGenerator._parse_evals_response()` (`engine/testgen.py:317–355`) and `_strip_markdown_fences()` (line 358–373) have fragile JSON extraction:

1. `_strip_markdown_fences()` uses a line-by-line state machine that drops fence lines but keeps content — it can miss edge cases like nested fences or fences with extra text after ` ``` `.
2. `_parse_evals_response()` finds first `{` and last `}` — this breaks when LLM output contains multiple JSON objects or trailing text with `}` characters.
3. On any `json.JSONDecodeError`, immediately falls back to `minimum_evals_template` — no retry.

**Fix approach:**

1. **`engine/testgen.py` — `_parse_evals_response()`**: Multi-strategy JSON extraction:
   - Strategy 1: Current `_strip_markdown_fences()` + `json.loads()`
   - Strategy 2: Regex extraction of outermost `{...}` with balanced brace counting
   - Strategy 3: Find all `{...}` blocks, try each from largest to smallest
   - Strategy 4: Try `json.loads()` with `strict=False` on the full response
2. **`engine/testgen.py` — `generate_initial_evals()`**: Add retry on parse failure:
   - First attempt: standard prompt
   - On failure: retry with explicit "Respond ONLY with a JSON object. No prose, no explanation." system hint
   - On second failure: fall back to template (current behavior)
3. **`engine/testgen.py` — `_parse_review_response()`** (line 664–692): Apply same multi-strategy extraction.

**Files to change:**
- `engine/testgen.py`: Improve JSON extraction, add retry logic
- `tests/test_testgen.py`: Add tests for malformed JSON, retry behavior, multi-strategy extraction

**Risk:** Low. All changes are additive — existing parse path is tried first.

---

### 3.3 Issue #59: reporter.py 1003 lines — split into submodules

**Symptom:** `engine/reporter.py` is 1003 lines, handling Markdown generation, JSON generation, structured report building, suggestion generation, and data preparation — all in one class.

**Root Cause:** God-class anti-pattern. The `Reporter` class has 20+ methods spanning distinct responsibilities.

**Fix approach — Extract 3 submodules behind a facade:**

1. **`engine/reporter_markdown.py`** — `MarkdownReportRenderer`:
   - Jinja2 template string (243 lines)
   - `render_markdown(context: dict) -> str`
   - Extracted from: current `__init__()` template setup + `generate_report()` markdown path

2. **`engine/reporter_structured.py`** — `StructuredReportBuilder`:
   - `build(metrics, drift, config, ...) -> StructuredReport`
   - `_build_metrics_section()`, `_build_token_section()`, `_build_observability_section()`, `_build_eval_details()`, `_build_verdict_reasons()`, `_build_blocking_issues()`, `_build_caveats()`
   - Extracted from: current `build_structured_report()` and helpers

3. **`engine/reporter_suggestions.py`** — `SuggestionGenerator`:
   - `_generate_suggestions()`, `_get_metric_suggestions()`, `_get_overall_suggestions()`, `_get_cost_suggestions()`, `_get_latency_suggestions()`, `_get_reliability_suggestions()`, `_convert_suggestions()`
   - Extracted from: current suggestion methods

4. **`engine/reporter.py`** — `Reporter` (facade, ~200 lines):
   - `generate_report()` → delegates to `MarkdownReportRenderer` + `SuggestionGenerator`
   - `build_structured_report()` → delegates to `StructuredReportBuilder`
   - `generate_report_with_multi_skill()`, `generate_report_with_stress()` → compose submodules
   - Preserves all existing public method signatures

**Files to change:**
- New: `engine/reporter_markdown.py`, `engine/reporter_structured.py`, `engine/reporter_suggestions.py`
- Modified: `engine/reporter.py` (reduced to facade)
- `tests/test_reporter.py`: Existing tests should pass unchanged (facade preserves API)
- New: `tests/test_reporter_markdown.py`, `tests/test_reporter_structured.py`, `tests/test_reporter_suggestions.py`

**Risk:** Medium. Must preserve exact public API. Existing 1134 tests are the safety net — run full suite after refactor.

---

### 3.4 Issue #60: LLM-as-Judge lacks calibration

**Symptom:** No position bias handling by default, no golden calibration set wired into pipeline.

**Root Cause:**

1. `engine/calibration.py` exists with full `GoldenEvalSet` + `CalibrationRunner` + Cohen's Kappa — but it's never called from the main pipeline (`skill_cert/cli/evals.py`).
2. `engine/grader.py` has `_debias_position()` (line 408–500) but it's only triggered when `confidence < 0.8` (reactive, not proactive).
3. The judge prompt (`_build_judge_prompt()`, line 324–369) presents options in a fixed order — no swap randomization.

**Fix approach:**

1. **`engine/grader.py` — `_llm_judge_with_call()`**: Always run position debiasing (not just for borderline cases). Run both original and swapped prompts, compare results. If disagreement → reduce confidence by 30% and mark `position_sensitive=True`.
2. **`skill_cert/cli/evals.py`**: Add optional calibration step after grading:
   - If `--calibration-set <path>` is provided, run `CalibrationRunner.calibrate()` with the golden set
   - Include calibration report in the final output (add to `StructuredReport.extras`)
3. **`engine/reporter.py` — `build_structured_report()`**: Include calibration data in the report when available.

**Files to change:**
- `engine/grader.py`: Make position debiasing default behavior
- `skill_cert/cli/evals.py`: Wire optional calibration step
- `engine/reporter.py`: Include calibration in structured report
- `tests/test_grader.py`: Update tests for always-on debiasing
- `tests/test_calibration.py`: Add integration tests

**Risk:** Medium. Always-on debiasing doubles LLM judge calls (2x cost). Make it configurable via `--debias-position` flag (default: true).

---

### 3.5 Issue #61: L2 formula denominator zero unprotected

**Symptom:** When `without_skill_avg` is near-zero, L2 normalized gain explodes but is silently clamped to [0,1].

**Root Cause:**

`MetricsCalculator._compute_normalized_gain()` (`engine/metrics.py:174–177`):
```python
if without_avg > 0:
    return (with_avg - without_avg) / without_avg
return with_avg - without_avg
```

When `without_avg` is very small (e.g., 0.001), the gain explodes: `(0.5 - 0.001) / 0.001 = 499`. Line 188 clamps to `max(0.0, min(1.0, ...))` → L2 = 1.0. This is misleading — it says "perfect improvement" when actually the baseline was just trivially bad.

**Fix approach:**

1. **`engine/metrics.py` — `_compute_normalized_gain()`**: Add epsilon guard:
   ```python
   EPSILON = 1e-6
   if abs(without_avg) < EPSILON:
       # Baseline is effectively zero — normalized gain is meaningless
       # Return absolute delta with a flag
       return with_avg - without_avg  # Already the current fallback
   ```
2. **`engine/metrics.py` — `_get_l2_details()`**: Add `denominator_warning: bool` field to details dict when `without_avg < 0.01`, indicating the normalized gain may be unreliable.
3. **`engine/reporter.py`**: Surface the warning in the report when `denominator_warning` is True.

**Files to change:**
- `engine/metrics.py`: Add epsilon guard, add warning flag to L2 details
- `engine/reporter.py`: Surface warning in report
- `tests/test_metrics.py`: Add tests for near-zero denominator cases

**Risk:** Low. Additive warning flag, no behavior change for normal cases.

---

## 4. P2 — Enhancements

### 4.1 Issue #62: L4 stability stats method behind

**Symptom:** Base L4 uses single-round std dev; `StabilityRunner` has proper CI-based calculation but is disconnected.

**Root Cause:**

`MetricsCalculator._calculate_l4_execution_stability()` (`engine/metrics.py:347–354`) computes `1.0 - std_dev` from deterministic pass rates within a single run. This is a within-run metric.

`engine/stability.py` has `StabilityRunner` + `calculate_l4_stability()` that uses multi-run confidence intervals, t-distribution, and CV-based scoring — but it's only activated with `--runs N` flag.

**Fix approach:**

1. **`engine/metrics.py` — `MetricsCalculator.calculate_metrics()`**: Accept optional `stability_data: dict | None = None` parameter. When provided (from `StabilityRunner`), use `calculate_l4_stability()` from `stability.py` instead of the simple std dev approach.
2. **`skill_cert/cli/evals.py`**: When `--runs N` is used, pass `StabilityRunner` results to `MetricsCalculator.calculate_metrics()`.
3. **Backward compat:** When `stability_data` is None (single-run mode), use current behavior unchanged.

**Files to change:**
- `engine/metrics.py`: Accept optional stability_data, use CI-based L4 when available
- `skill_cert/cli/evals.py`: Thread stability data into metrics calculator
- `tests/test_metrics.py`: Add tests for CI-based L4

**Risk:** Low. Fully backward compatible.

---

### 4.2 Issue #63: SKILL.md missing Freshness tracking

**Symptom:** Freshness dimension only has 4 regex patterns, easily scores 100%.

**Root Cause:**

`engine/maintainability.py:129–134` — `FRESHNESS_PATTERNS` has only 4 patterns:
1. Old model names (Claude 1/2, GPT-3.5, GPT-4)
2. Old Python versions (3.0–3.6)
3. Old SDK package names
4. Semver version strings

Missing: date-based freshness, API version tracking, dependency version staleness.

**Fix approach:**

1. **`engine/maintainability.py` — `FRESHNESS_PATTERNS`**: Expand to ~15 patterns:
   - Add: old API versions (`v1beta`, `v2alpha`), old framework versions (LangChain <0.1, etc.)
   - Add: deprecated function patterns (`text-davinci-003`, `code-davinci-002`)
   - Add: old date patterns (`202[0-3]` in "Last updated" context)
2. **`engine/maintainability.py` — `freshness_score()`**: Add date-based scoring:
   - Check for "Last updated" / "Revision date" fields
   - If found and > 6 months old, apply 0.1 penalty per 6-month increment
   - If no date found, apply 0.05 penalty (unknown freshness)
3. **Add `has_last_updated: bool` and `days_since_update: int | None` to freshness result dict.**

**Files to change:**
- `engine/maintainability.py`: Expand patterns, add date-based scoring
- `tests/test_maintainability.py`: Add tests for new patterns and date scoring

**Risk:** Low. Additive patterns, existing scores preserved for content without dates.

---

### 4.3 Issue #64: security_probes patterns need expansion

**Symptom:** 52 patterns may be insufficient; industry recommends 100+.

**Root Cause:**

Current coverage by category:
| Category | Count | Gap |
|----------|-------|-----|
| INJECTION | 12 | Missing: tool-based injection, multi-turn injection |
| DANGEROUS_CMD | 12 | Missing: `kubectl`, `helm`, `terraform` destructive ops |
| CREDENTIAL | 10 | Missing: GCP, Azure credential paths |
| EXFILTRATION | 8 | Missing: GraphQL introspection, WebSocket exfil |
| OBFUSCATION | 5 | Missing: RTL override, homograph attacks |
| PRIV_ESC | 5 | Missing: namespace escaping, capability abuse |

**Fix approach:**

Add ~30 new patterns to reach 80+ total:

1. **INJECTION (+5):** tool-result injection, multi-turn context poisoning, system-reminder spoofing, config-file injection, environment variable injection
2. **DANGEROUS_CMD (+8):** `kubectl delete`, `helm uninstall`, `terraform destroy`, `docker rm -f`, `podman --privileged`, `ansible -m shell`, `puppet apply`, `chef-client`
3. **CREDENTIAL (+5):** GCP service account keys, Azure connection strings, Vault tokens, HashiCorp secrets, Confluent API keys
4. **EXFILTRATION (+5):** GraphQL data exfil, WebSocket outbound, IRC bot, SMTP exfil, FTP upload
5. **OBFUSCATION (+4):** RTL override chars, more homoglyphs, PowerShell encoding, variable expansion tricks
6. **PRIV_ESC (+3):** Kubernetes namespace escape, Linux capability abuse, cgroup escape

**Files to change:**
- `engine/security_probes.py`: Add new pattern lists
- `tests/test_security_probes.py`: Add tests for each new pattern (positive + negative cases)

**Risk:** Low. Purely additive. Each new pattern needs negative tests to avoid false positives on legitimate content.

---

## 5. Dependency Chain & Execution Order

```
Phase 1 (P0 — parallel):
  #54 eval_details     #55 Token cost      #56 JudgeResult
       │                     │                    │
       └─────────────────────┴────────────────────┘
                             │
Phase 2 (P1 — sequential after P0):
  #57 skill_type ──→ #58 testgen JSON ──→ #59 reporter split
                             │
                    #60 calibration ──→ #61 L2 epsilon
                             │
Phase 3 (P2 — parallel, after P1):
  #62 L4 stability     #63 Freshness      #64 Security patterns
```

**Parallelization opportunities:**
- **Phase 1:** All 3 P0 issues can be fixed in parallel (different files, no overlap)
- **Phase 2:** #57 and #61 can start in parallel. #58 depends on #57 (skill_type affects testgen). #59 depends on #54 (reporter needs eval_details wiring). #60 depends on #56 (calibration needs working judge).
- **Phase 3:** All 3 P2 issues are independent and can be parallelized.

**Recommended execution order for single developer:**
1. #55 (cost) — simplest, highest user-visible impact
2. #56 (judge) — second simplest, unblocks calibration
3. #54 (eval_details) — requires reporter + CLI changes
4. #61 (L2 epsilon) — quick fix in metrics.py
5. #57 (skill_type) — analyzer + testgen changes
6. #58 (testgen JSON) — builds on #57
7. #60 (calibration) — builds on #56
8. #59 (reporter split) — refactor, do after all reporter changes are stable
9. #62 (L4 stability) — metrics + CLI wiring
10. #63 (freshness) — standalone
11. #64 (security patterns) — standalone, can be done anytime

---

## 6. Risk Matrix

| Issue | Risk | Mitigation |
|-------|------|------------|
| #54 eval_details | Low | Additive param, defaults to `[]` |
| #55 Token cost | Low | Fuzzy match is additive, exact match still priority |
| #56 JudgeResult | Low | Clamping strictly better than crashing |
| #57 skill_type | Medium | New field defaults to current behavior |
| #58 testgen JSON | Low | Multi-strategy extraction tries current method first |
| #59 reporter split | Medium | 1134 tests are the safety net; run full suite |
| #60 calibration | Medium | 2x LLM judge cost; make configurable |
| #61 L2 epsilon | Low | Additive warning flag |
| #62 L4 stability | Low | Fully backward compatible |
| #63 freshness | Low | Additive patterns |
| #64 security | Low | Additive patterns, need negative tests |

---

## 7. Testing Strategy

**For each fix:**
1. Write failing tests FIRST that reproduce the bug
2. Implement the fix
3. Verify failing tests pass
4. Run full `pytest tests/` to ensure no regressions (1134 tests must still pass)
5. Run `ruff check . && ruff format .` for lint compliance

**Cross-cutting concerns:**
- #54 + #59: After reporter split, verify eval_details still populates correctly
- #55 + #60: After cost fix, verify calibration doesn't break cost tracking
- #56 + #60: After judge fix, verify calibration works with debiased judge
- #57 + #58: After skill_type detection, verify testgen JSON parsing works for both skill types

**Regression prevention:**
- Add integration test that runs full pipeline on a sample SKILL.md and verifies:
  - `eval_details` is non-empty in JSON output
  - Cost is non-zero when model is recognized
  - LLM-as-Judge results are present (not all fallback)
  - L2 details include `denominator_warning` when appropriate

---

## 8. Files Changed Summary

| File | Issues | Change Type |
|------|--------|-------------|
| `engine/runner.py` | #55 | Bug fix (model_name threading) |
| `adapters/pricing.py` | #55 | Enhancement (fuzzy matching) |
| `engine/grader.py` | #56, #60 | Bug fix + enhancement (clamp, debias) |
| `engine/reporter.py` | #54, #59, #61 | Bug fix + refactor + enhancement |
| `engine/report_models.py` | #54 | No change (schema already has eval_details) |
| `skill_cert/cli/evals.py` | #54, #60, #62 | Enhancement (thread results, calibration, stability) |
| `engine/analyzer.py` | #57 | Enhancement (skill_type detection) |
| `engine/testgen.py` | #57, #58 | Enhancement (prompt branching, JSON parsing) |
| `engine/metrics.py` | #61, #62 | Bug fix + enhancement (epsilon, CI-based L4) |
| `engine/stability.py` | #62 | No change (already has CI logic) |
| `engine/maintainability.py` | #63 | Enhancement (freshness patterns) |
| `engine/security_probes.py` | #64 | Enhancement (new patterns) |
| New: `engine/reporter_markdown.py` | #59 | Refactor extraction |
| New: `engine/reporter_structured.py` | #59 | Refactor extraction |
| New: `engine/reporter_suggestions.py` | #59 | Refactor extraction |

**Estimated total new/modified LOC:** ~800 lines of implementation, ~600 lines of tests.
