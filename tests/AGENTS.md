# tests/ — Test Suite

## OVERVIEW
pytest suite mirroring engine/ modules 1:1. 403 tests, 83% coverage. Tests use standard pytest patterns: fixtures, parametrize, mock patches.

## STRUCTURE
```
tests/
├── test_analyzer.py              # SKILL.md parsing + schema validation
├── test_security_probes.py       # Security scanner (19 patterns, 5 categories)
├── test_testgen.py               # Eval generation + review loop
├── test_runner.py                # Execution engine (with/without skill)
├── test_grader.py                # Assertion grading + LLM-as-judge
├── test_metrics.py               # L1-L8 metric calculation
├── test_drift.py                 # Cross-model drift detection
├── test_reporter.py              # Markdown + JSON report generation
├── test_envelope.py              # Operating envelope checks
├── test_integrations.py          # External integration providers
├── test_stability.py             # Multi-run stability (L4)
├── test_stress_test.py           # Concurrency stress testing
├── test_reliability.py           # Error classification + retry stats
├── test_maintainability.py       # SKILL.md readability scoring
├── test_multi_skill.py           # Multi-skill conflict detection
├── test_dialogue_evaluator.py    # Multi-turn evaluation
├── test_dialogue_runner.py       # Dialogue orchestration
├── test_replay.py                # Historical session replay
├── test_simulator.py             # LLM behavior simulation
├── test_config.py                # Configuration validation
├── test_cli.py                   # CLI entry point (35% coverage)
├── test_token_tracking.py        # Real token tracking + budget
├── test_pricing.py               # Model pricing table
├── test_cross_endpoint.py        # Cross-endpoint fallback
├── test_scalability.py           # Scalability scoring
└── conftest.py                   # Shared fixtures
```

## WHERE TO LOOK
| Task | File | Notes |
|------|------|-------|
| Core pipeline tests | `test_analyzer.py`, `test_testgen.py`, `test_runner.py`, `test_grader.py` | Main eval flow |
| Metrics + drift | `test_metrics.py`, `test_drift.py` | L1-L8 + cross-model |
| Security + envelope | `test_security_probes.py`, `test_envelope.py` | Phase 0.5 + limits |
| Advanced features | `test_stress_test.py`, `test_reliability.py`, `test_maintainability.py`, `test_multi_skill.py` | Non-core capabilities |
| Adapter tests | `test_pricing.py`, `test_cross_endpoint.py`, `test_token_tracking.py` | LLM provider layer |

## CONVENTIONS
- Test files mirror engine/ modules 1:1 (test_analyzer.py ↔ engine/analyzer.py)
- Standard pytest: `assert`, `pytest.raises`, `@pytest.mark.parametrize`
- Mock adapters in `conftest.py` — no real API calls in unit tests
- Coverage target: 83% overall, cli.py is the main gap (35%)

## ANTI-PATTERNS
- Do NOT skip Phase 1 self-review loop in testgen tests
- Do NOT test with-skill without without-skill baseline
- Do NOT modify eval cases after Phase 2 execution in test data
