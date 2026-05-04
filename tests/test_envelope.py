from engine.envelope import EnvelopeChecker, EnvelopeResult


class MockExecutionTrace:
    def __init__(self, steps=5, tool_calls=3, tokens=10000, time_ms=5000, tool_call_count=3):
        self.steps = steps
        self.tool_calls = tool_calls
        self.tokens = tokens
        self.time_ms = time_ms
        self.tool_call_count = tool_call_count


class TestEnvelopeResult:
    def test_passed_result(self):
        result = EnvelopeResult(passed=True, violations=[], details={"steps": 3})
        assert result.passed is True
        assert len(result.violations) == 0

    def test_failed_result(self):
        result = EnvelopeResult(passed=False, violations=["max_steps exceeded: 25 > 20"])
        assert result.passed is False
        assert len(result.violations) > 0

    def test_multiple_violations(self):
        result = EnvelopeResult(
            passed=False,
            violations=[
                "max_steps exceeded: 25 > 20",
                "token_budget exceeded: 60000 > 50000"
            ]
        )
        assert len(result.violations) == 2


class TestEnvelopeChecker:
    def test_default_constructor(self):
        checker = EnvelopeChecker()
        assert checker.max_steps == 20
        assert checker.max_tool_calls == 15
        assert checker.token_budget == 50000
        assert checker.timeout_s == 300

    def test_custom_constructor(self):
        checker = EnvelopeChecker(max_steps=10, max_tool_calls=5, token_budget=10000, timeout_s=60)
        assert checker.max_steps == 10
        assert checker.max_tool_calls == 5
        assert checker.token_budget == 10000
        assert checker.timeout_s == 60

    def test_check_within_bounds_passes(self):
        checker = EnvelopeChecker()
        trace = MockExecutionTrace(steps=5, tool_call_count=3, tokens=10000, time_ms=5000)
        result = checker.check(trace)
        assert result.passed is True

    def test_check_exceeds_max_steps(self):
        checker = EnvelopeChecker(max_steps=20)
        trace = MockExecutionTrace(steps=25, tool_call_count=3, tokens=10000, time_ms=5000)
        result = checker.check(trace)
        assert result.passed is False
        assert any("max_steps" in v for v in result.violations)

    def test_check_exceeds_token_budget(self):
        checker = EnvelopeChecker(token_budget=50000)
        trace = MockExecutionTrace(steps=5, tool_call_count=3, tokens=60000, time_ms=5000)
        result = checker.check(trace)
        assert result.passed is False
        assert any("token_budget" in v for v in result.violations)

    def test_check_exceeds_timeout(self):
        checker = EnvelopeChecker(timeout_s=120)
        trace = MockExecutionTrace(steps=5, tool_call_count=3, tokens=10000, time_ms=150000)
        result = checker.check(trace)
        assert result.passed is False
        assert any("timeout" in v for v in result.violations)

    def test_check_exceeds_max_tool_calls(self):
        checker = EnvelopeChecker(max_tool_calls=15)
        trace = MockExecutionTrace(steps=5, tool_call_count=20, tokens=10000, time_ms=5000)
        result = checker.check(trace)
        assert result.passed is False
        assert any("tool_calls" in v for v in result.violations)

    def test_check_at_exact_boundary_passes(self):
        checker = EnvelopeChecker(max_steps=20)
        trace = MockExecutionTrace(steps=20, tool_call_count=3, tokens=50000, time_ms=300000)
        result = checker.check(trace)
        assert result.passed is True

    def test_check_returns_details(self):
        checker = EnvelopeChecker()
        trace = MockExecutionTrace(steps=8, tool_call_count=4, tokens=20000, time_ms=30000)
        result = checker.check(trace)
        assert "steps" in result.details
        assert result.details["steps"] == 8

    def test_constructor_partial_overrides(self):
        checker = EnvelopeChecker(max_steps=30)
        assert checker.max_steps == 30
        assert checker.max_tool_calls == 15
        assert checker.token_budget == 50000
        assert checker.timeout_s == 300
