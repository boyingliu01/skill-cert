# Phase 1: Implementation Plan — skill-cert v2 Enhancement

## Gap Analysis Summary

### Codebase Health
- **207 tests PASS**, 30 warnings (all PydanticDeprecatedSince20 in grader.py)
- **24 mypy errors** across 9 files (mostly missing Optional annotations)
- **4 ruff lint issues** (unused imports/variables)
- **No TODOs/FIXMEs** in engine modules

### Specification Coverage by REQ

| REQ | Title | Implementation | Test Coverage | Gaps |
|-----|-------|---------------|---------------|------|
| REQ-001 | Skill Self-Parsing | ✅ Complete | ✅ 5+5 tests | Parser enhanced, CCN fixed |
| REQ-002 | Auto-Test Generation | ✅ Complete | ✅ 19 tests | None significant |
| REQ-003 | Self-Execution | ⚠️ Partial | ✅ 7 tests | AC-003-06: token_usage is approximate (len split), not real API token tracking |
| REQ-004 | Assertion-Based Grading | ✅ Complete | ✅ 16 tests | AC-004-08: LLM judge temp=0 enforced but not tested |
| REQ-005 | L1-L4 Metrics | ✅ Complete | ✅ 13 tests | None significant |
| REQ-006 | Cross-Model Drift | ✅ Complete | ✅ 11 tests | None significant |
| REQ-007 | Standardized Reporting | ✅ Complete | ✅ 6 tests | AC-007-07: config/benchmark info not in report |
| REQ-008 | Error Handling | ⚠️ Partial | ✅ 14+ tests | AC-008-01: exponential backoff in adapters but not tested; AC-008-06: config validation exists but limited |
| REQ-009 | Concurrency & Security | ⚠️ Partial | ✅ 21+16 tests | AC-009-01/02: rate limiter in runner but not per-model; AC-009-06: token budget not tracked |
| REQ-010 | CLI Entry Point | ❌ Stub | ⚠️ 1 test | Only Phase 0 (parse) works; Phases 1-6 not wired; no --mode, --max-turns, --session flags |

### Priority Fixes (Ordered by Impact)

#### P0 — CLI Not Functional (REQ-010)
The CLI only does Phase 0 (parse). It prints "Remaining phases require model API access" and exits.
No --mode (single/dialogue/replay), no --max-turns, no --session, no --replay flags.
Exit codes only support 1 (error), not 0 (pass) / 2 (fail with caveats).

#### P1 — Pre-existing Code Quality Issues
1. grader.py: `.dict()` → `.model_dump()` (Pydantic v2, 2 occurrences, 30 warnings)
2. adapters/anthropic_compat.py: unused `e` variable, missing return statement
3. adapters/openai_compat.py: unused `json` import
4. engine/dialogue_evaluator.py: unused `AsyncMock` import, unused `all_user_msgs`
5. engine/analyzer.py: 7 mypy errors (missing Optional, type annotations)
6. adapters/base.py, openai_compat.py: missing Optional annotations
7. engine/replay.py: Path vs str type mismatch
8. engine/runner.py: type incompatibility in error append

#### P2 — Token Tracking Placeholder (AC-003-06, AC-009-06)
Runner uses `len(response.split())` for token counting, not real API token counts.
No token budget enforcement. Adapters don't return usage data.

#### P3 — Missing Report Fields (AC-007-07)
Reporter doesn't include configuration details or benchmark information in reports.

## Implementation Plan (Phase 2 BUILD)

### Batch 1: Code Quality Cleanup (P1) — Low Risk
Fix all pre-existing lint/mypy/warning issues before adding new code.
- grader.py: `.dict()` → `.model_dump()`
- adapters: unused imports, missing return, Optional annotations
- dialogue_evaluator.py: unused imports/variables
- analyzer.py: type annotations (current_list, triggers, step_type)
- replay.py: Path/str type fixes
- runner.py: error append type fix

### Batch 2: CLI Full Implementation (P0) — High Impact
Wire the full pipeline through the CLI:
- Add --mode flag (single/dialogue/replay)
- Add --max-turns for dialogue mode
- Add --session for replay mode
- Wire Phase 1-6 pipeline (testgen → runner → grader → metrics → drift → reporter)
- Add proper exit codes (0=pass, 1=error, 2=fail_with_caveats)
- Add progress feedback (phase markers)

### Batch 3: Token Tracking Enhancement (P2) — Medium Risk
- Adapters return token usage from API responses
- Runner tracks real token counts
- Add token budget config option
- Token budget enforcement with warning/block

### Batch 4: Report Enhancement (P3) — Low Risk
- Add configuration section to reports
- Add benchmark information section
- Add coverage statistics section

## Verification Criteria
- All 207+ tests pass
- mypy errors < 5 (from 24)
- ruff check clean
- No Pydantic deprecation warnings
- CLI produces full pipeline output for single mode
- CLI --mode dialogue and --mode replay work
