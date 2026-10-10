# tests/ — Test Suite

## OVERVIEW
pytest suite mirroring engine/ modules 1:1 — **63 test modules, 1594 tests** (1 skipped). Tests use standard pytest patterns: fixtures, parametrize, mock patches.

## STRUCTURE
```
tests/
├── test_<module>.py              # 1:1 mirror — one file per engine/ or adapters/ module
│                                 # (analyzer, testgen, runner, grader, json_extract, metrics, drift, envelope,
│                                 # reporter, builders, deadline, observability, token_ledger,
│                                 # stability, stress_test, reliability, maintainability,
│                                 # multi_skill, calibration, classifier, hooks_detector,
│                                 # structure_quality, progressive_disclosure, replay, config,
│                                 # constants, trace_models, report_models, pricing, integrations,
│                                 # openai_compat, anthropic_compat, adapters, …)
├── test_harness_{taskgen,judge,llm_json,evaluator,opencode,util}.py   # real-harness path
├── *_p0 / *_p1 / *_routing / *_l7 / *_latency / *_cost  # behaviour-level extras
├── smoke / integration / cli_* / evals / single          # pipeline-level suites
└── conftest.py                   # Shared fixtures (mock adapters — no live API in unit tests)
```

## RUNNING TESTS

```bash
# All tests
pytest tests/

# Single file
pytest tests/test_metrics.py -v

# Single test
pytest tests/test_metrics.py::TestMetricsCalculator::test_l2_with_greater_than_without_exact_delta -v

# With coverage
pytest --cov=engine --cov=skill_cert --cov=adapters --cov-report=term-missing
```

## CONVENTIONS
- Test files mirror engine/ modules 1:1 (`test_analyzer.py` ↔ `engine/analyzer.py`)
- Standard pytest: `assert`, `pytest.raises`, `@pytest.mark.parametrize`
- Mock adapters in `conftest.py` — no real API calls in unit tests
- `asyncio_mode = "auto"` in pyproject.toml
- Never assert clock advance from a short sleep: `time.monotonic()` on Windows is `GetTickCount64()` with 15.625ms resolution, so `sleep(0.01)` can leave it unchanged — span ≥4 ticks (`tests/test_deadline.py::_MONOTONIC_TICK`) or mock `engine.deadline.time.monotonic`
- Timing thresholds must exceed the host clock resolution, not a fixed wall duration

## ANTI-PATTERNS
- Do NOT skip Phase 1 self-review loop in testgen tests
- Do NOT test with-skill without without-skill baseline
- Do NOT modify eval cases after Phase 2 execution in test data
