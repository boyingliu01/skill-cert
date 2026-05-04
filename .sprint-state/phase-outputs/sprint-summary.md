# Sprint Summary — 2026-05-04

## Shipping Commit: `2dc146f`

**Branch**: `feature/skill-cert-v2-enhancement`
**Status**: Ready to ship

## What Shipped

### Parser Enhancement (Phase 0 — prior work)
- Workflow extraction: Chinese section names, Phase N: patterns, line-start anchoring
- Trigger extraction: 4-tier fallback (frontmatter field → raw YAML → body → description)
- Anti-pattern extraction: skip Chinese table headers
- Output format extraction: JSON keys + list items + assertion lines, noise filtering
- Confidence scoring: 8-dimensional (0.17 → 0.90 range)
- Schema validation: conditional security/permissions penalties

### Code Quality Cleanup (Phase 2 — Batch 1)
- Pydantic v2 migration: .dict() → .model_dump() (30 warnings fixed)
- Unused imports removed: json, AsyncMock, asyncio, Any, Optional
- Type annotations: current_list, triggers, step_type, Optional
- Path/str consistency: replay.py
- error append type fix: runner.py

### CLI Full Pipeline (Phase 2 — Batch 2)
- Full Phase 0-5 pipeline: parse → testgen → run → grade → metrics → drift → report
- --mode flag: single/dialogue/replay
- --max-turns, --session for dialogue/replay
- Exit codes: 0=pass, 1=error, 2=fail_with_caveats
- Adapter factory: auto-detect OpenAI vs Anthropic
- CCN reduction: run_single_mode split into 5 helpers

### Token Tracking (Phase 2 — Batch 3)
- adapters: chat_with_usage() returns (content, token_usage)
- Real usage data from API responses
- Graceful fallback to len(split) for non-API adapters
- Mock-compatible runner interface

### Report Enhancement (Phase 2 — Batch 4)
- Configuration section in Markdown/JSON reports
- Benchmark Information section (timestamp, coverage stats)
- Token usage tracking in reports

## Verification
- 207 tests passing
- ruff check: clean
- Test-spec alignment: 90.8/100
- mypy: 2 env-level errors only (missing stub packages)

## Deferred to Sprint 2
- testgen.py _calculate_coverage: CCN 21 → refactor
- dialogue_evaluator.py evaluate_conversation: CCN 16 → refactor
- Integration tests with real API keys
- CLI dialogue/replay end-to-end tests
