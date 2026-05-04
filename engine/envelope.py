class EnvelopeResult:
    def __init__(self, passed: bool, violations: list, details: dict | None = None):
        self.passed = passed
        self.violations = violations
        self.details = details if details is not None else {}


class EnvelopeChecker:
    def __init__(self, max_steps: int = 20, max_tool_calls: int = 15, token_budget: int = 50000, timeout_s: int = 300, cost_budget: float = 0.0):
        self.max_steps = max_steps
        self.max_tool_calls = max_tool_calls
        self.token_budget = token_budget
        self.timeout_s = timeout_s
        self.cost_budget = cost_budget

    def check(self, trace) -> EnvelopeResult:
        violations = []
        details = {}

        steps = getattr(trace, "steps", 0)
        details["steps"] = steps
        if steps > self.max_steps:
            violations.append(f"max_steps exceeded: {steps} > {self.max_steps}")

        tc = getattr(trace, "tool_call_count", getattr(trace, "tool_calls", 0))
        details["tool_calls"] = tc
        if tc > self.max_tool_calls:
            violations.append(f"max_tool_calls exceeded: {tc} > {self.max_tool_calls}")

        tokens = getattr(trace, "tokens", 0)
        details["tokens"] = tokens
        if tokens > self.token_budget:
            violations.append(f"token_budget exceeded: {tokens} > {self.token_budget}")

        time_ms = getattr(trace, "time_ms", 0)
        time_s = time_ms / 1000.0
        details["time_s"] = time_s
        if time_s > self.timeout_s:
            violations.append(f"timeout exceeded: {time_s:.1f}s > {self.timeout_s}s")

        cost = getattr(trace, "cost", 0.0)
        details["cost"] = cost
        if self.cost_budget > 0 and cost > self.cost_budget:
            violations.append(f"cost_budget exceeded: ${cost:.2f} > ${self.cost_budget:.2f}")

        return EnvelopeResult(passed=len(violations) == 0, violations=violations, details=details)
