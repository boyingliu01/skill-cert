"""Structured report models for skill-cert evaluation output.

These Pydantic models define the schema for structured JSON reports.
The models support:
- Metadata (skill, models, timestamp, version)
- Verdict summary (PASS/FAIL with reasons)
- L1-L8 metrics
- Per-eval details with assertions
- Token analysis (by phase, model, eval)
- Observability section (trace summary, export path)
- Improvement suggestions (structured)

Design decisions (Delphi Review consensus):
- ImprovementSuggestion has __str__() for backward compat with existing reporter
- Token analysis data comes from TokenLedger (read-only aggregator)
- Observability section references trace export files
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ── Metadata ──────────────────────────────────────────────────


class ReportMetadata(BaseModel):
    """Report metadata: skill, models, timestamp."""

    skill_name: str = ""
    skill_path: str = ""
    skill_version: str = ""
    models: list[str] = Field(default_factory=list)
    timestamp: str = ""
    schema_version: str = "1.0"
    engine_version: str = ""


# ── Verdict ───────────────────────────────────────────────────


class VerdictSummary(BaseModel):
    """Overall verdict and reasons."""

    verdict: Literal["PASS", "PASS_WITH_CAVEATS", "FAIL"] = "FAIL"
    confidence: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    blocking_issues: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


# ── Metrics ───────────────────────────────────────────────────


class MetricDimension(BaseModel):
    """Evaluation dimension with five-field analysis for each metric."""

    purpose: str = ""
    method: str = ""
    result: str = ""
    analysis: str = ""
    improvement: str = ""


class MetricsSection(BaseModel):
    """L1-L8 metrics section."""

    l1_trigger_accuracy: float = 0.0
    l1_detail: MetricDimension = Field(default_factory=MetricDimension)
    l2_output_delta: float = 0.0
    l2_detail: MetricDimension = Field(default_factory=MetricDimension)
    l3_step_adherence: float = 0.0
    l3_detail: MetricDimension = Field(default_factory=MetricDimension)
    l4_stability_std: float = 0.0
    l4_detail: MetricDimension = Field(default_factory=MetricDimension)
    l5_step_efficiency: float = 0.0
    l5_detail: MetricDimension = Field(default_factory=MetricDimension)
    l6_trajectory_quality: float = 0.0
    l6_detail: MetricDimension = Field(default_factory=MetricDimension)
    l7_cost_efficiency: float = 0.0
    l7_detail: MetricDimension = Field(default_factory=MetricDimension)
    l8_latency_p50: float = 0.0
    l8_latency_p95: float = 0.0
    l8_latency_p99: float = 0.0
    l8_detail: MetricDimension = Field(default_factory=MetricDimension)
    extras: dict[str, Any] = Field(default_factory=dict)


# ── Eval Details ──────────────────────────────────────────────


class AssertionResult(BaseModel):
    """Single assertion result."""

    type: str = ""
    expected: str = ""
    actual: str = ""
    passed: bool = False
    weight: float = 1.0


class EvalDetail(BaseModel):
    """Per-eval detail with assertions."""

    eval_id: int | str = 0
    eval_name: str = ""
    eval_category: str = ""
    model: str = ""
    phase: str = ""  # with_skill | without_skill
    input: str = ""
    output: str = ""
    passed: bool = False
    score: float = 0.0
    assertions: list[AssertionResult] = Field(default_factory=list)
    execution_time: float = 0.0
    tokens_used: int = 0
    cost: float = 0.0
    error: str | None = None
    workflow_step: str | None = None
    negative_case: bool = False


# ── Token Analysis ────────────────────────────────────────────


class TokenBreakdown(BaseModel):
    """Token breakdown for a single dimension."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0
    model: str = ""


class TokenAnalysisSection(BaseModel):
    """Token analysis section with per-phase/model/eval breakdown."""

    total_tokens: int = 0
    total_cost: float = 0.0
    by_phase: dict[str, TokenBreakdown] = Field(default_factory=dict)
    by_model: dict[str, TokenBreakdown] = Field(default_factory=dict)
    by_eval: list[dict[str, Any]] = Field(default_factory=list)
    budget_utilization: float = 0.0
    alerts: list[dict[str, Any]] = Field(default_factory=list)


# ── Observability ─────────────────────────────────────────────


class ObservabilitySection(BaseModel):
    """Observability section with trace summary."""

    trace_count: int = 0
    total_events: int = 0
    total_duration_ms: float = 0.0
    total_tool_calls: int = 0
    trace_export_path: str = ""
    trace_format: str = "jsonl"


# ── Improvement Suggestions ───────────────────────────────────


class ImprovementSuggestion(BaseModel):
    """Structured improvement suggestion.

    __str__() provides backward compatibility with existing reporter
    that expects list[str] from _generate_suggestions().
    """

    category: str = ""  # prompt, workflow, evals, security, performance
    priority: Literal["high", "medium", "low"] = "medium"
    title: str = ""
    description: str = ""
    expected_impact: str = ""

    def __str__(self) -> str:
        """Backward-compatible string representation."""
        return f"[{self.priority.upper()}] {self.category}: {self.title} - {self.description}"


# ── Structured Report (Top-Level) ─────────────────────────────


class StructuredReport(BaseModel):
    """Top-level structured evaluation report.

    This is the canonical schema for skill-cert JSON output.
    """

    metadata: ReportMetadata = Field(default_factory=ReportMetadata)
    verdict: VerdictSummary = Field(default_factory=VerdictSummary)
    metrics: MetricsSection = Field(default_factory=MetricsSection)
    eval_details: list[EvalDetail] = Field(default_factory=list)
    token_analysis: TokenAnalysisSection = Field(default_factory=TokenAnalysisSection)
    observability: ObservabilitySection = Field(default_factory=ObservabilitySection)
    improvements: list[ImprovementSuggestion] = Field(default_factory=list)
    security: dict[str, Any] = Field(default_factory=dict)
    drift: dict[str, Any] = Field(default_factory=dict)
    envelope: dict[str, Any] = Field(default_factory=dict)
    reliability: dict[str, Any] = Field(default_factory=dict)
    calibration: dict[str, Any] | None = None
    extras: dict[str, Any] = Field(default_factory=dict)

    # Backward compatibility: these mirror verdict fields at top level
    # (existing code may access report["verdict"] as string)
    @property
    def verdict_str(self) -> str:
        return self.verdict.verdict

    @property
    def overall_score(self) -> float:
        """Compute overall score from metrics (for backward compat)."""
        weights = {
            "l1": 0.25,
            "l2": 0.20,
            "l3": 0.20,
            "l4": 0.10,
            "l5": 0.10,
            "l6": 0.15,
        }
        score = (
            self.metrics.l1_trigger_accuracy * weights["l1"]
            + min(self.metrics.l2_output_delta / 50.0, 1.0) * 100 * weights["l2"]
            + self.metrics.l3_step_adherence * weights["l3"]
            + max(0, 100 - self.metrics.l4_stability_std * 10) * weights["l4"]
            + self.metrics.l5_step_efficiency * weights["l5"]
            + self.metrics.l6_trajectory_quality * weights["l6"]
        )
        return round(score, 1)
