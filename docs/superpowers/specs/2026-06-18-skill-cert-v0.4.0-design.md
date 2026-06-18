---
created: 2026-06-18
sprint: sprint-2026-06-18-01
issues: [47, 44, 43, 42]
status: draft
---

# v0.4.0 Sprint Design

## Overview

This sprint addresses 4 issues tagged with `iteration:v0.4.0`:

1. **#47** Bug Fix: analyzer.py `_calculate_confidence()` 置信度低估
2. **#44** Enhancement: 负向案例评测机制 (negative_cases + F1)
3. **#43** Enhancement: L1 触发准确性专项评测 (TriggerAccuracyEval)
4. **#42** Enhancement: Gotchas Flywheel 追加型经验积累

---

## Issue #47: Fix Confidence Calculation

### Problem

`_calculate_confidence()` only recognizes fixed section names:
- `## Workflow` → workflow_steps (0.25)
- `## Anti-Patterns` → anti_patterns (0.10)
- `## Output Format` → output_format (0.08)
- `## Triggers` → triggers (0.07)

Skills using non-standard but valid section names (e.g., `## How I Work`, `## What I Do`) are under-weighted.

### Solution

Expand pattern matching with semantic aliases:

| Section Name | Maps To | Weight |
|-------------|---------|-------|
| `## Workflow` | workflow_steps | 0.25 |
| `## How I Work` | workflow_steps | 0.25 |
| `## Process` | workflow_steps | 0.25 |
| `## Steps` | workflow_steps | 0.25 |
| `## Anti-Patterns` | anti_patterns | 0.10 |
| `## What Not To Do` | anti_patterns | 0.10 |
| `## Gotchas` | anti_patterns | 0.10 |
| `## Output Format` | output_format | 0.08 |
| `## Response Format` | output_format | 0.08 |
| `## Triggers` | triggers | 0.07 |
| `## What I Do` | triggers | 0.07 |
| `## When To Use` | triggers | 0.07 |

### Files Changed

- `engine/analyzer.py`: Expand `_SECTION_PATTERN_MAP`

---

## Issue #44: Negative Cases Evaluation

### Problem

Current evals only test positive cases (should_trigger). Missing:
- should_not_trigger cases
- boundary/confusion cases (close but not belonging)

### Solution

1. **Extend EvalCase schema** with `negative_case: bool` field
2. **Add category: "negative"** for should_not_trigger cases
3. **Add F1 scoring** to grader/metrics (precision + recall)

#### EvalCase Schema Extension

```python
class EvalCase(BaseModel):
    # ... existing fields ...
    negative_case: bool = False  # If True, expect NOT to trigger
    confusion_prompt: str | None = None  # Near-miss prompt for boundary testing
```

#### F1 Scoring

```
precision = TP / (TP + FP)
recall = TP / (TP + FN)
F1 = 2 * precision * recall / (precision + recall)
```

Where:
- TP = positive case triggered + correct
- FP = negative case triggered (wrong)
- FN = positive case NOT triggered (wrong)
- TN = negative case NOT triggered + correct

### Files Changed

- `engine/grader.py`: Add F1 scoring methods
- `engine/metrics.py`: Add `_calculate_f1_score()`
- `schemas/evals/` or `engine/testgen.py`: Support negative_cases

---

## Issue #43: L1 Trigger Accuracy Eval

### Problem

Currently no dedicated L1 trigger accuracy testing. Need:
- should_trigger cases
- should_not_trigger cases
- >= 90% threshold gate

### Solution

New class `TriggerAccuracyEval`:

```python
class TriggerAccuracyEval:
    """Dedicated L1 trigger accuracy evaluator."""
    
    def evaluate(self, eval_cases: list[EvalCase]) -> TriggerAccuracyResult:
        """Run trigger accuracy evaluation."""
        # Separate positive and negative cases
        positive_cases = [c for c in eval_cases if not c.negative_case]
        negative_cases = [c for c in eval_cases if c.negative_case]
        
        # Run with-skill vs without-skill
        with_skill_results = self._run_cases(positive_cases + negative_cases, with_skill=True)
        without_skill_results = self._run_cases(positive_cases + negative_cases, with_skill=False)
        
        # Calculate trigger accuracy
        tp = sum(1 for r in with_skill_results if r.triggered and r.expected)
        tn = sum(1 for r in without_skill_results if not r.triggered and not r.expected)
        fp = sum(1 for r in with_skill_results if r.triggered and not r.expected)
        fn = sum(1 for r in without_skill_results if r.triggered and r.expected)
        
        accuracy = (tp + tn) / (tp + tn + fp + fn)
        return TriggerAccuracyResult(accuracy=accuracy, threshold=0.90)
```

### Threshold Gate

If L1 accuracy < 90%, evaluation is BLOCKED with message:
```
L1 trigger accuracy {accuracy:.1%} < 90% threshold
```

### Files Changed

- `engine/trigger_accuracy_eval.py`: New class
- `engine/metrics.py`: Wire into `_calculate_l1_trigger_accuracy()`
- `engine/runner.py`: Call TriggerAccuracyEval

---

## Issue #42: Gotchas Flywheel

### Problem

Failed evals are not captured for future improvement. Need:
- Auto-extract gotchas from failures
- Store for future reference

### Solution

New class `GotchasFlywheel`:

```python
class GotchasFlywheel:
    """Accumulates experience from eval failures."""
    
    def __init__(self, skill_path: Path):
        self.gotchas_dir = skill_path / "references" / "gotchas.md"
    
    def extract_from_failure(self, eval_result: EvalResult) -> str | None:
        """Extract gotcha text from failed eval. Returns None if nothing worth capturing."""
        # Pattern: "Model expected X but got Y"
        # Or: "Failed assertion: ..."
        return gotcha_text
    
    def append(self, gotcha: str) -> None:
        """Append gotcha to gotchas.md."""
        with open(self.gotchas_dir, "a") as f:
            f.write(f"\n## Gotcha: {timestamp}\n{gotcha}\n")
    
    def load(self) -> list[str]:
        """Load all accumulated gotchas."""
        if not self.gotchas_dir.exists():
            return []
        return self.gotchas_dir.read_text().split("## Gotcha:")
```

### Trigger

After each eval run, `GotchasFlywheel` extracts patterns from failures and appends to `references/gotchas.md`.

### Files Changed

- `engine/gotchas_flywheel.py`: New class
- `engine/runner.py`: Integrate after eval run

---

## Implementation Order

Suggested dependency order:

1. **#47** (Bug Fix) — Fix confidence first, unblocks other evals
2. **#44** (Negative Cases) — Foundation for #43
3. **#43** (TriggerAccuracyEval) — Depends on #44 negative_cases
4. **#42** (GotchasFlywheel) — Independent, can parallel

---

## Acceptance Criteria

| Issue | Criteria |
|-------|----------|
| #47 | ffmpeg-video skill parses at >= 0.6 confidence |
| #44 | negative_cases field works; F1 scoring computed |
| #43 | TriggerAccuracyEval class exists; L1 >= 90% gate works |
| #42 | GotchasFlywheel extracts and persists gotchas |

---

## Files Summary

| File | Change |
|------|--------|
| `engine/analyzer.py` | Expand section patterns |
| `engine/grader.py` | Add F1 scoring |
| `engine/metrics.py` | Wire F1 and TriggerAccuracyEval |
| `engine/testgen.py` | Support negative_cases |
| `engine/trigger_accuracy_eval.py` | New class |
| `engine/gotchas_flywheel.py` | New class |
| `engine/runner.py` | Integrate new classes |