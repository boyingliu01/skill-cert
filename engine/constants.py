"""Central constants for skill-cert engine — all hardcoded thresholds, limits, and magic numbers."""

import os


class CoverageThresholds:
    """Coverage thresholds for eval test generation."""

    COVERAGE_TARGET = 0.9
    COVERAGE_DEGRADE = 0.7
    COVERAGE_BLOCK = float(os.environ.get("SKILL_CERT_COVERAGE_BLOCK", "0.5"))


# TestGen logic version - bump when test generation logic changes
TESTGEN_LOGIC_VERSION = "2.0"


class TestGenLimits:
    """Limits for eval generation self-review loop."""

    MAX_REVIEW_ROUNDS = 3
    MAX_NO_IMPROVEMENT = 2
    MIN_EVAL_CASES = 4
    MIN_TRIGGER_CASES = 5
    GAP_FILL_TIMEOUT = 300


class SecurityLimits:
    """Security scanning limits and counts."""

    MAX_PATTERN_CATEGORIES = 6
    PATTERN_COUNT = 80
    MAX_OUTPUT_LENGTH = 100000


class StabilityThresholds:
    """L4 stability thresholds for multi-run evaluation."""

    L4_STD_MAX = 0.1
    L4_PASS_THRESHOLD = 0.8
    DEFAULT_RUNS = 5
    DEFAULT_TRIALS = 5
    CONFIDENCE_LEVEL = 0.95
    MIN_SAMPLES_FOR_L4 = 5


class VerdictThresholds:
    """Minimum scores required for PASS verdict."""

    L1_MIN = 0.9
    L2_MIN = 0.2
    L3_MIN = 0.85


class DriftThresholds:
    """Cross-model drift severity thresholds."""

    NONE = 0.10
    LOW = 0.20
    MODERATE = 0.35
    HIGH = 0.35


class TimingLimits:
    """Timeout and rate limit defaults (in seconds unless noted)."""

    DEFAULT_TIMEOUT = 120
    REQUEST_TIMEOUT = 120
    GLOBAL_TIMEOUT = 3600
    RATE_LIMIT_RPM = 60
    SLOW_REQUEST_THRESHOLD = 30.0


class ConcurrencyLimits:
    """Concurrency limits for execution."""

    MAX_CONCURRENCY = 5
    DEFAULT_STRESS_CONCURRENCY = 50
    DEFAULT_STRESS_EVALS = 100


class TokenLimits:
    """Token budget defaults."""

    DEFAULT_TOKEN_BUDGET = 100000


class MaintainabilityWeights:
    """Weights for maintainability scoring components."""

    READABILITY_WEIGHT = 0.4
    COMPLETENESS_WEIGHT = 0.3
    FRESHNESS_WEIGHT = 0.3


class EnvelopeDefaults:
    """Default operating envelope limits."""

    MAX_STEPS = 20
    MAX_TOKENS = 50000
    MAX_TOOL_CALLS = 15
    TIMEOUT_S = 300
    COST_BUDGET = 0.0


class ObservabilityDefaults:
    """Default observability settings."""

    TRACE_FORMAT = "jsonl"  # jsonl | otlp | none
    TRACE_DIR = None  # None = same as output dir
    OTLP_ENDPOINT = None


class TokenBudgetDefaults:
    """Token budget alert thresholds."""

    WARNING_THRESHOLD = 0.8  # 80% of budget triggers warning
    CRITICAL_THRESHOLD = 1.0  # 100% of budget triggers critical
    DEFAULT_COST_BUDGET = 0.0  # 0 = no limit


class ReportDefaults:
    """Default report settings."""

    FORMAT = "both"  # markdown | json | both
    SCHEMA_VERSION = "1.0"
    JSON_SCHEMA_VALIDATE = False


class TraceFormats:
    """Trace export format options."""

    JSONL = "jsonl"
    NONE = "none"
