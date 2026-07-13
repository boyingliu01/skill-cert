# Design: Instruction-Type Skill Parser Extension

> Issue: #84 — skill-cert fails on instruction/orchestration-type skills
> Date: 2026-07-10
> Status: APPROVED (Delphi Round 1 consensus 95%+)

## Problem

`parse_skill_md()` in `engine/analyzer.py` assumes all skills follow a declarative structure:

- `## Workflow Steps` section → workflow_steps
- `## Triggers` section → triggers
- `## Anti-Patterns` section → anti_patterns

Instruction-type skills (e.g., gstack autoplan — 1839 lines, 24K tokens) are long-form prose
with phases, triggers, and anti-patterns embedded inline. The parser extracts nothing →
parse_confidence 0.10 → all L1/L2/L3 metrics FAIL.

## Root Cause

The extraction functions (`_extract_workflow_steps`, `_extract_triggers`, `_extract_anti_patterns`)
only search within section boundaries (`## Section Name`). They have no fallback for skills
where this information is embedded in prose.

## Delphi Consensus (Round 1)

**Expert A (Architecture)**: REQUEST_CHANGES → consensus on revised approach
**Expert B (Technical)**: REQUEST_CHANGES → consensus on revised approach
**Consensus ratio**: 95%+ — both experts agree on revised direction

### Key Revisions from Delphi Review

1. **REMOVE content-richness bonus** (Expert A Critical, Expert B agrees): Let fallback
   extraction functions return results that naturally flow into `_calculate_confidence` via
   existing `has_workflow`, `has_anti_patterns`, `has_triggers` booleans. This naturally
   awards +0.25 + +0.10 + +0.07 = +0.42 without a parallel scoring channel.

2. **Phase regex must handle heading format** (Expert B Critical): Real skills like autoplan
   use `## Phase N: NAME` headings, not just inline `Phase N:` text. Regex must match both.

3. **Contextual anchors for regex** (Expert A/B Major): Prose triggers and anti-patterns
   must appear in list items, table cells, or bold markers — not bare narrative text.

4. **Single-pass extraction** (Expert B Major): Combine instruction-type pattern extraction
   into `_extract_instruction_patterns(content)` returning (phases, triggers, anti_patterns)
   in one scan to avoid multiple O(n) passes on 1800+ line files.

5. **Expand test plan** (Expert A/B): 10+ tests covering boundary conditions, false positive
   prevention, and references/ merging.

## Design (Revised)

All changes are in `engine/analyzer.py`.

### 1. Single-Pass Instruction Pattern Extraction

**New function**: `_extract_instruction_patterns(content: str) -> tuple[list[WorkflowStep], list[str], list[str]]`

Scans content once for all instruction-type patterns:

**Phase extraction** (workflow steps):
- Match `## Phase N: NAME` headings (markdown heading format)
- Match inline `Phase N: NAME` or `Phase N/M: NAME` (body text format)
- Contextual anchor: must be followed by `:` then a capitalized word
- Regex: `r'^(?:##\s+)?Phase\s+(\d+(?:/\d+)?):\s*([A-Z][^\n]*)'` with MULTILINE

**Trigger extraction** (prose triggers):
- Match `**Triggers**:` or `**Trigger**:` followed by list items
- Match trigger table rows: `| **English** | ... |` / `| **中文** | ... |`
- Match `Use when asked to "..."` or `Use when:` followed by quoted phrases
- Contextual anchor: must appear in list item, table cell, or bold marker

**Anti-pattern extraction** (directive patterns):
- Match `MUST NOT` / `NEVER` / `Do NOT` in list items or table cells
- Contextual anchor: must be preceded by `-`, `*`, or `|` (list/table context)
- Regex: `r'(?:^|\n)\s*(?:[-*|])\s*.*?(?:MUST NOT|NEVER|Do NOT)\s+(.+)'`

### 2. Integration into parse_skill_md

In `parse_skill_md`, after structured extraction returns empty results:
```python
if not workflow_steps and not anti_patterns and not triggers:
    instr_phases, instr_triggers, instr_anti = _extract_instruction_patterns(content)
    if instr_phases:
        workflow_steps = instr_phases
    if instr_triggers:
        triggers = instr_triggers
    if instr_anti:
        anti_patterns = instr_anti
```

This runs on `merged_content` when references/ are present (same as existing extraction).

### 3. Confidence — Natural Flow (No Bonus)

No changes to `_calculate_confidence`. The fallback extraction results naturally set
`has_workflow=True`, `has_anti_patterns=True`, `has_triggers=True` → confidence gains
+0.25 + +0.10 + +0.07 = +0.42 automatically.

### 4. Skill Type Detection — "instruction" Type

**Change**: Add `"instruction"` detection in `_detect_skill_type`:
- Check if `_extract_instruction_patterns` found ≥3 phases
- AND content > 500 lines
- AND no CLI/library signals
- Return `"instruction"` if all conditions met

### 5. Regex Precision

All instruction-type patterns require **contextual anchors**:
- Phase patterns: must be at line start (with optional `##` prefix) + colon + capitalized word
- Trigger patterns: must be in list item, table cell, or bold marker
- Anti-pattern directives: must be in list item or table cell (not bare narrative)

This prevents false positives from narrative text that happens to mention "Phase" or "MUST NOT".

## Test Plan (10+ tests)

1. `test_parse_instruction_type_extracts_phase_steps` — basic Phase N: extraction
2. `test_parse_instruction_type_extracts_heading_phases` — `## Phase N:` heading format
3. `test_parse_instruction_type_extracts_prose_triggers` — trigger table + bold triggers
4. `test_parse_instruction_type_extracts_list_anti_patterns` — MUST NOT in list items
5. `test_parse_instruction_type_confidence_via_natural_flow` — confidence ≥ 0.60 without bonus
6. `test_parse_instruction_type_detected` — skill_type == "instruction"
7. `test_instruction_type_no_false_positive_phase_in_narrative` — "Phase" in prose not extracted
8. `test_instruction_type_no_false_positive_must_not_in_narrative` — bare "MUST NOT" not extracted
9. `test_instruction_type_structured_preferred_over_prose` — when ## Workflow exists, prose ignored
10. `test_instruction_type_with_references_merging` — fallback runs on merged_content
11. `test_instruction_type_short_content_not_detected` — <500 lines stays agent_guide
12. `test_instruction_type_mixed_phase_formats` — both `Phase 1:` and `## Phase 2:` extracted

## Scope

**In scope**: P0 — Parser extension for instruction-type skills
**Out of scope** (deferred to future sprints):
- P1: Orchestration skill eval mode (decision completeness, phase completion metrics)
- P2: Relaxed structure quality checks for instruction-type skills (first-person prose, inline tools)
