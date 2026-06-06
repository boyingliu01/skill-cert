"""Execution trace models for skill-cert observability and token monitoring.

This module defines the core data models for:
- ExecutionTrace: per-eval execution timeline with token accounting
- TraceEvent: discriminated union of typed events (LLMCall, ToolCall, etc.)
- TokenAccounting: token usage and cost tracking
- EnvelopeTraceDTO: compatibility layer for EnvelopeChecker

Design decisions (Delphi Review consensus, 2/2 APPROVED):
- ExecutionTrace is the SINGLE source of truth for token data
- TokenLedger is a read-only aggregator that consumes ExecutionTrace list
- TraceEvent uses Discriminated Union (not loose dict) for type safety
- EnvelopeTraceDTO is a frozen dataclass (not dynamic _Compat class)
- schema_version field for forward compatibility
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

# ── Token Accounting ──────────────────────────────────────────


class TokenAccounting(BaseModel):
    """Token usage and cost tracking."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0
    model: str = ""

    def merge(self, other: TokenAccounting) -> TokenAccounting:
        """Merge two TokenAccounting instances (returns new instance)."""
        return TokenAccounting(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cost=self.cost + other.cost,
            model=self.model or other.model,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any], model: str = "") -> TokenAccounting:
        """Create from a token usage dict (e.g., from adapter response)."""
        return cls(
            input_tokens=data.get("prompt_tokens", data.get("input_tokens", 0)),
            output_tokens=data.get("completion_tokens", data.get("output_tokens", 0)),
            total_tokens=data.get("total_tokens", 0),
            cost=data.get("cost", 0.0),
            model=model,
        )


# ── Budget Alert ──────────────────────────────────────────────


class BudgetAlert(BaseModel):
    """Alert when token/cost budget threshold is crossed."""

    level: Literal["warning", "critical"] = "warning"
    message: str
    used: float = 0.0
    budget: float = 0.0


# ── Trace Events (Discriminated Union) ───────────────────────


class _BaseTraceEvent(BaseModel):
    """Base class for all trace events."""

    timestamp: float = Field(default_factory=time.time)
    latency_ms: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMCallEvent(_BaseTraceEvent):
    """An LLM API call (request + response)."""

    event_type: Literal["LLMCall"] = "LLMCall"
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    success: bool = True
    error: str | None = None


class ToolCallEvent(_BaseTraceEvent):
    """A tool/function call during execution."""

    event_type: Literal["ToolCall"] = "ToolCall"
    tool_name: str = ""
    arguments: dict[str, Any] = Field(default_factory=dict)
    success: bool = True
    error: str | None = None


class ToolResultEvent(_BaseTraceEvent):
    """Result of a tool call."""

    event_type: Literal["ToolResult"] = "ToolResult"
    tool_name: str = ""
    result_summary: str = ""
    success: bool = True


class StepCompleteEvent(_BaseTraceEvent):
    """A workflow step completed."""

    event_type: Literal["StepComplete"] = "StepComplete"
    step_name: str = ""
    step_index: int = 0


class TurnStartEvent(_BaseTraceEvent):
    """A dialogue turn started."""

    event_type: Literal["TurnStart"] = "TurnStart"
    turn_index: int = 0


class ErrorEvent(_BaseTraceEvent):
    """An error occurred during execution."""

    event_type: Literal["Error"] = "Error"
    error_type: str = ""
    error_message: str = ""
    recoverable: bool = False


# Discriminated union type for all trace events
TraceEvent = (
    LLMCallEvent | ToolCallEvent | ToolResultEvent | StepCompleteEvent | TurnStartEvent | ErrorEvent
)


# ── Envelope Compatibility DTO ───────────────────────────────


@dataclass(frozen=True)
class EnvelopeTraceDTO:
    """Frozen DTO for EnvelopeChecker compatibility.

    Replaces the dynamic _Compat class with a proper typed dataclass.
    EnvelopeChecker.check() accesses these attributes via getattr().
    """

    steps: int
    tool_call_count: int
    tokens: int
    time_ms: float
    cost: float


# ── Execution Trace ──────────────────────────────────────────


class ExecutionTrace(BaseModel):
    """Complete execution trace for a single eval run.

    This is the SINGLE source of truth for token data.
    TokenLedger aggregates from ExecutionTrace instances (read-only).
    """

    schema_version: str = "1.0"
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    eval_id: int | str = 0
    phase: str = "with_skill"  # with_skill | without_skill | grading | judge
    events: list[TraceEvent] = Field(default_factory=list)
    token_usage: TokenAccounting = Field(default_factory=TokenAccounting)
    start_time: float = 0.0
    end_time: float = 0.0
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        """Total duration in milliseconds."""
        if self.end_time and self.start_time:
            return (self.end_time - self.start_time) * 1000
        return 0.0

    @property
    def step_count(self) -> int:
        """Number of completed steps."""
        return sum(1 for e in self.events if isinstance(e, StepCompleteEvent))

    @property
    def tool_call_count(self) -> int:
        """Number of tool calls."""
        return sum(1 for e in self.events if isinstance(e, ToolCallEvent))

    def add_event(self, event: TraceEvent) -> None:
        """Add an event to the trace timeline."""
        self.events.append(event)

    def record_llm_call(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: float,
        success: bool = True,
        error: str | None = None,
    ) -> LLMCallEvent:
        """Convenience: record an LLM call event and update token_usage."""
        total = input_tokens + output_tokens
        event = LLMCallEvent(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total,
            latency_ms=latency_ms,
            success=success,
            error=error,
        )
        self.events.append(event)
        # Update token_usage (single source of truth)
        self.token_usage = self.token_usage.merge(
            TokenAccounting(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total,
                model=model,
            )
        )
        return event

    def to_envelope_dto(self) -> EnvelopeTraceDTO:
        """Convert to EnvelopeTraceDTO for EnvelopeChecker compatibility."""
        return EnvelopeTraceDTO(
            steps=self.step_count,
            tool_call_count=self.tool_call_count,
            tokens=self.token_usage.total_tokens,
            time_ms=self.duration_ms,
            cost=self.token_usage.cost,
        )

    # Backward-compatible alias (existing code may call to_envelope_trace)
    to_envelope_trace = to_envelope_dto
