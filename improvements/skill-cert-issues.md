# skill-cert Methodology Improvements

> Generated after evaluating delphi-review — 7 concrete issues identified
> Evaluated: 2026-07-06

---

This document lists all methodology-level improvements for skill-cert's evaluation pipeline,
discovered during a live evaluation of the delphi-review skill. Each item describes the problem,
evidence, and proposed fix for filing as a GitHub issue.

---

## Issue 1: Coverage matching has false negatives — lacks fuzzy matching

### Problem

`_calculate_coverage` uses exact substring matching between eval assertion values and
SKILL.md specification fields (workflow_steps, anti_patterns, output_format). Regex
assertion values are expanded into branches and each branch is checked as a literal
substring. This misses:
- Case differences: `"Phase 0"` vs `"phase 0"` (SKILL.md field stores `"Phase 0: 准备"`)
- Punctuation/formatting differences: `"review this design"` vs `"review a design"`
- Synonyms: `"Prepare"` vs `"Setup"` vs `"Initialization"`

### Evidence

In the delphi-review eval, the workflow_step regex
`"(Phase 0|准备|Preparation|Preparing|Setup|Initialize|Phase Zero)"` should cover the spec
field `"Phase 0: 准备"` — and `"Phase 0"` is a literal substring. But coverage still
reported 76% (below 90% target), and subsequent analysis showed the coverage expander
was case-sensitive and not matching.

### Proposed Fix

Add a `_fuzzy_match(text, pattern)` step to the coverage matcher:
1. `text.lower() in pattern.lower()` (case-insensitive exact)
2. Levenshtein distance ≤ 2 if no exact match
3. Token overlap (Jaccard ≥ 0.5) for longer strings

---

## Issue 2: L2 delta should be category-weighted, not a single pooled rate

### Problem

L2 is computed as `(with_skill_pass_rate - without_skill_pass_rate)` across ALL eval cases
pooled together. This dilutes the delta because trigger and workflow_step evals behave
fundamentally differently from normal/boundary evals:
- Trigger evals: with-skill should trigger (pass), without-skill should not trigger (fail) → large delta
- Normal evals: both modes produce similar results → small delta
- Pooling them gives equal weight regardless of eval category

### Evidence

delphi-review eval: 22 evals mixed trigger (8), workflow_step (1), failure (4), normal (3+).
The single pooled L2 of 6.6% masks that trigger accuracy contributed meaningful improvement
while normal cases were flat.

### Proposed Fix

Compute L2 per category, then weight:
- trigger: 0.3
- workflow_step: 0.3
- normal/boundary/failure: 0.4 (pooled)

This gives a more realistic picture of where the skill actually adds value.

---

## Issue 3: L3 step adherence measures coverage but not execution quality

### Problem

L3 currently uses token-overlap matching to check whether the model's output "mentions"
each workflow step. This measures **coverage** (did the output include a step name/keyword?)
but not **quality** (did the model correctly execute that step?).
- Example: output mentions "Expert 1, Expert 2, Expert 3" → counts as covering "多专家" step
- But there's no check on whether the experts were anonymous, had diverse perspectives,
  or went through convergence rounds

### Evidence

delphi-review's L3 was 81.4% (coverage 68%) — all from keyword presence. Quality
judgment (were the steps executed correctly?) was never applied.

### Proposed Fix

Add a `step_quality` sub-metric to L3:
- `step_coverage` (current): did the output mention the step? — weight 0.5
- `step_quality`: did the step's output match expected structure? — weight 0.5
- Step quality can use regex/contains for structural validation, or LLM-as-judge
  for complex judgment

---

## Issue 4: Single-model L4 stability produces meaningless 0.0% score

### Problem

With a single model and single run (default mode), L4 std deviation is 0.0 because
there's nothing to compare. The report shows `L4=0.0%` and a FAIL verdict, which is
misleading — it doesn't mean the skill is unstable, it means L4 was never computed.

### Evidence

```
L4 calculated from single-run std_dev is deprecated. Use --runs >= 5 for Bootstrap CI-based L4.
...
L4 Execution Stability: 0.0% (std<=10%) FAIL
```

### Proposed Fix

- Auto-run 3 internal passes when `--runs` is not specified (cheap stability estimate)
- OR output `L4: N/A (single run)` instead of `0.0%`
- OR exclude L4 from verdict computation when only 1 model × 1 run is used

---

## Issue 5: Markdown report lacks drill-down into failed evals

### Problem

The Markdown report only shows aggregate scores (L1-L4, pass rates). Users who want
to understand *why* a particular metric failed must read the JSON file. The JSON
`eval_details[]` contains rich per-eval data (assertions passed/failed, actual output,
execution time) but none of it appears in the Markdown report.

### Evidence

Compare results/delphi-review/SKILL-report.md (summary only) vs
SKILL-result.json (eval_details with 22 entries × assertions).

### Proposed Fix

Add a "Failed Eval Cases" table to the Markdown report:
- Columns: eval_name, category, model, phase, score, failed_assertions
- Row per failed eval case
- Optional: truncated actual_output for context

---

## Issue 6: --models alias name is conflated with provider model_name

### Problem

The `--models` CLI format `name=url,key` uses the `name` as both the human-readable
alias AND the `model_name` sent to the API. When the provider's actual model name
differs (e.g., `LOCAL/Qwen3.5-122B-A10B` vs a short alias like `local-qwen`),
users must use the clunky Format 2 syntax: `name=provider_model,base_url,api_key`.

### Evidence

First run with `local-qwen` failed: `无效的模型名称 'local-qwen'`. Had to rewrite as
`local-qwen=LOCAL/Qwen3.5-122B-A10B,https://...` without documentation discovery.

### Proposed Fix

Add `--models-alias` parameter:
```
--models "local-qwen=https://url,key" --models-alias "local-qwen=LOCAL/Qwen3.5-122B-A10B"
```

Or align CLI parsing with models.yaml format, allowing explicit `provider_model` field.

---

## Issue 7: Single-model drift section is misleading

### Problem

When only one model is used, the report still shows:
```
### No Significant Drift Detected
- All model comparisons show consistent performance
```

This looks like a positive result but it's actually "not computed." A reader could
interpret "no drift" as the skill being cross-model consistent, when only one model
was tested.

### Evidence

delphi-review report with 1 model shows drift section as above.

### Proposed Fix

In Drift Analysis section, when model count < 2:
- Display: `**Skipped**: single model only. Use at least 2 models from different providers for drift detection.`
- Do NOT show "No Significant Drift Detected" or "consistent performance"

---

## Appendix: Evaluation Run Details

- Skill: delphi-review (`.qoder/skills/delphi-review/SKILL.md`)
- Verdict: PASS_WITH_CAVEATS (62.26%)
- Model: deepseek-v4-flash (g-deepseek-v4-flash via whalecloud proxy)
- Eval cases: 22 (with-skill 11, without-skill 11)
- Coverage: 76% (below 90% target, degraded mode)
- Phase 0.5: Progressive Disclosure FAIL (index 119t > 100t limit)
- Phase 0.5: Structure Quality 75/100
- Phase 0.5: Tool Permission 55/100
- Reliability: 100% success rate
- Date: 2026-07-06
