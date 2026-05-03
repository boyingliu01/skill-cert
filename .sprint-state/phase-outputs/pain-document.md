# Phase 0: Pain Document — skill-cert Self-Evaluation Findings

## Pain: skill-cert fails its own evaluation

The self-evaluation revealed skill-cert parses its own SKILL.md with **confidence 0.35 / verdict FAIL on schema**.

## Root Cause Analysis

Compared side-by-side against delphi-review (confidence 0.90):

| Dimension | skill-cert | Deltreview | Root Cause |
|-----------|-----------|------------|------------|
| triggers | 0 | 1 | No `triggers:` field in frontmatter, no `## Triggers` section |
| anti_patterns | 0 | 5 | Anti-Patterns section exists (4 items) but parser can't extract them — see below |
| output_format | 0 | 12 | No `## Output Format` section at all |
| schema_valid | False | False(non-interactive) | Missing Output Format section triggers schema penalty |

### Anti-Pattern extraction failure

The `## Anti-Patterns` section has 4 valid list items:
```
- 跳过 Phase 1 自审循环直接跑评测
- 只跑 with-skill 不跑 without-skill 基线
- 忽略 L4 稳定性只关注 L2 delta
- 漂移检测 high 仍给 PASS
```

But the parser returns 0. Investigation needed: parser might require a section header match pattern that differs from what's in the SKILL.md.

### Why confidence is 0.35 (not 0)

The parser scores 8 dimensions at weights:
- frontmatter: 0.30 -> name + description present but no triggers/tags -> ~0.15
- workflow: 0.25 -> 15 steps extracted (good) -> 0.25
- headings: 0.15 -> has headings -> 0.15
- anti_patterns: 0.10 -> **parser extracts 0** -> 0.00
- output_format: 0.08 -> **no OF section** -> 0.00
- triggers: 0.07 -> **0 triggers** -> 0.00
- examples: 0.05 -> none -> 0.00
- bonus: 0.05 -> content exists -> 0.00 (too short: 92 lines)

Total: ~0.35 (matches observed)

### The "Lighthouse without a light" problem

skill-cert was built to evaluate OTHER skills, but its own SKILL.md was written as a short user guide (92 lines), not a proper skill definition. The parser it enforces on others — it can't pass itself.

## Pain Points for Users

1. **Low confidence undermines trust**: A tool that fails its own evaluation isn't credible
2. **Missing OF prevents assertion generation**: Testgen can't generate output checks without Output Format definitions
3. **Missing triggers prevents trigger eval generation**: L1 accuracy can't really be measured
4. **Schema invalid**: Indicates structural incompleteness — can't auto-validate format compliance
