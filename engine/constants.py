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


# ── Metric Metadata ────────────────────────────────────────────
# Each metric has purpose (Chinese) and method (Chinese) for use in reports.

METRIC_METADATA: dict[str, dict[str, str]] = {
    "L1": {
        "purpose": "验证模型是否在正确场景触发该Skill，而非误触发或遗漏触发",
        "method": (
            "生成正例和反例触发用例，通过混淆矩阵（TP/TN/FP/FN）计算综合准确率，"
            "精确匹配 + LLM-as-Judge补充验证语义触发"
        ),
    },
    "L2": {
        "purpose": "验证Skill是否确实提升了模型表现，而非只是增加了上下文成本",
        "method": (
            "在有Skill和无Skill两种条件下执行相同评测集，"
            "计算归一化增益Δ=(with-without)/without，增益≥20%为PASS"
        ),
    },
    "L3": {
        "purpose": "验证模型是否遵循Skill定义的工作流步骤",
        "method": "通过步骤覆盖度(0.5)、工具调用准确度(0.3)和轮次相关性(0.2)三个维度综合评估",
    },
    "L4": {
        "purpose": "验证多次执行结果的一致性，确保Skill不是偶然有效",
        "method": "多次执行评测并计算确定性断言通过率的标准差，标准差≤10%为PASS",
    },
    "L5": {
        "purpose": "验证Skill执行是否在操作边界内",
        "method": (
            "EnvelopeChecker检查每次执行的步骤数、token消耗、"
            "超时和工具调用数是否在限制范围内"
        ),
    },
    "L6": {
        "purpose": "验证多轮对话场景下的交互质量",
        "method": "LLM-as-Judge(temp=0)评估对话轨迹的连贯性、相关性和目标达成度",
    },
    "L7": {
        "purpose": "验证Skill带来的增益是否值得其产生的额外成本",
        "method": "基于真实token消耗和定价表计算成本，对比with/without Skill的成本增量",
    },
    "L8": {
        "purpose": "验证Skill是否引入不可接受的延迟",
        "method": "统计P50/P95/P99/均值延迟，计算with/without Skill的延迟开销百分比",
    },
    "drift": {
        "purpose": "验证Skill在不同模型上的表现一致性",
        "method": "在至少2个不同provider的模型上执行相同评测集，计算通过率方差",
    },
    "security": {
        "purpose": "检测Skill定义中是否包含安全风险",
        "method": "通过52个内置探针横跨6个类别(INJ/EXF/DCMD/CRD/OBF/PRIV_ESC)的模式匹配扫描",
    },
    "cost": {
        "purpose": "量化评测过程的总成本和单位成本",
        "method": "基于实际API调用中记录的token消耗和adapters/pricing.py的定价表计算",
    },
    "reliability": {
        "purpose": "评估评测过程本身的可靠性",
        "method": "统计总执行次数、成功/失败率、平均/最大重试次数，按错误类型分类",
    },
}
