# tests/ — Test Suite

## OVERVIEW
pytest suite mirroring engine/ modules 1:1. **684 tests**, 1 skipped. Tests use standard pytest patterns: fixtures, parametrize, mock patches.

## STRUCTURE
```
tests/
├── test_analyzer.py              # SKILL.md parsing + schema validation + strict_schema
├── test_security_probes.py       # Security scanner (52 patterns, 6 categories)
├── test_testgen.py               # Eval generation + review loop
├── test_runner.py                # Execution engine (with/without skill)
├── test_grader.py                # Assertion grading + LLM-as-judge
├── test_metrics.py               # L1-L8 metric calculation (L2 normalized gain, L5 envelope)
├── test_drift.py                 # Cross-model drift detection
├── test_reporter.py              # Markdown + JSON report generation
├── test_envelope.py              # Operating envelope checks
├── test_integrations.py          # External integration providers
├── test_stability.py             # Multi-run stability (L4)
├── test_stress_test.py           # Concurrency stress testing
├── test_reliability.py           # Error classification + retry stats
├── test_maintainability.py       # SKILL.md readability scoring
├── test_multi_skill.py           # Multi-skill conflict detection
├── test_dialogue_evaluator.py    # Multi-turn evaluation + judge_with_llm
├── test_dialogue_runner.py       # Dialogue orchestration
├── test_replay.py                # Historical session replay
├── test_simulator.py             # LLM behavior simulation
├── test_config.py                # Configuration validation
├── test_cli.py                   # CLI entry point
├── test_cli_setup.py             # Setup subcommand tests
├── test_token_tracking.py        # Real token tracking + budget
├── test_pricing.py               # Model pricing table
├── test_cross_endpoint.py        # Cross-endpoint fallback
├── test_scalability.py           # Scalability scoring
└── conftest.py                   # Shared fixtures
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

## ANTI-PATTERNS
- Do NOT skip Phase 1 self-review loop in testgen tests
- Do NOT test with-skill without without-skill baseline
- Do NOT modify eval cases after Phase 2 execution in test data
