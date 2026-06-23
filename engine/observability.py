"""Observability layer: EventBus + TraceExporter + SessionTelemetry for skill-cert.

Design decisions (Delphi Review consensus):
- EventBus is a lightweight pub/sub for trace events
- TraceExporter supports JSONL (default) and optional OTLP
- Exceptions in EventBus are LOGGED (not silently swallowed)
- OTLP export failure raises ClickException when explicitly configured
- SessionTelemetry extends observability.py (not a new telemetry.py module)
- SessionTelemetry follows TokenLedger consumption pattern (record_trace)
"""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from engine.trace_models import ExecutionTrace

logger = logging.getLogger(__name__)


# ── EventBus ──────────────────────────────────────────────────


class EventBus:
    """Lightweight pub/sub for trace events.

    Thread-safe: uses threading.Lock for subscriber management.
    Exceptions in handlers are logged, not swallowed.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable]] = {}
        self._lock = threading.Lock()

    def subscribe(self, event_type: str, handler: Callable) -> None:
        """Subscribe a handler to an event type.

        Args:
            event_type: Event type string (e.g., "LLMCall", "ToolCall", "*")
            handler: Callable that accepts (event_type, payload)
        """
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(handler)

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        """Publish an event to all subscribers.

        Exceptions in handlers are logged as errors, not silently swallowed.
        """
        with self._lock:
            handlers = list(self._subscribers.get(event_type, []))
            handlers += list(self._subscribers.get("*", []))

        for handler in handlers:
            try:
                handler(event_type, payload)
            except Exception as e:
                logger.error(f"EventBus handler error for {event_type}: {type(e).__name__}: {e}")

    def publish_trace_event(self, trace: ExecutionTrace) -> None:
        """Publish a summary event from an ExecutionTrace."""
        payload = {
            "run_id": trace.run_id,
            "eval_id": trace.eval_id,
            "phase": trace.phase,
            "event_count": len(trace.events),
            "duration_ms": trace.duration_ms,
            "tokens": trace.token_usage.total_tokens,
            "cost": trace.token_usage.cost,
            "error": trace.error,
            "timestamp": time.time(),
        }
        self.publish("TraceComplete", payload)

    def clear(self) -> None:
        """Remove all subscribers."""
        with self._lock:
            self._subscribers.clear()


# ── TraceExporter ─────────────────────────────────────────────


class BaseTraceExporter(ABC):
    """Abstract base for trace exporters."""

    output_path: str | Path = ""  # LSP compat: satisfies access in SessionTelemetry.get_summary()

    @abstractmethod
    def export(self, traces: list[ExecutionTrace]) -> None:
        """Export a list of traces."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Clean up resources."""
        ...


class JSONLTraceExporter(BaseTraceExporter):
    """Export traces to JSONL file (one JSON object per line).

    Default format for local observability.
    """

    def __init__(self, output_path: str | Path) -> None:
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = None
        self._lock = threading.Lock()

    def export(self, traces: list[ExecutionTrace]) -> None:
        """Append traces to JSONL file."""
        with self._lock:
            with open(self.output_path, "a", encoding="utf-8") as f:
                for trace in traces:
                    f.write(trace.model_dump_json() + "\n")

    def close(self) -> None:
        """No-op for file-based exporter."""
        pass


class OTLPTraceExporter(BaseTraceExporter):
    """Export traces via OpenTelemetry Protocol (optional).

    Requires opentelemetry-exporter-otlp to be installed.
    Raises ImportError if not available when explicitly configured.
    """

    def __init__(self, endpoint: str, service_name: str = "skill-cert") -> None:
        self.endpoint = endpoint
        self.service_name = service_name
        self._initialized = False
        self._tracer = None

        try:
            from opentelemetry import trace
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,  # type: ignore[import-untyped,import-not-found]
            )
            from opentelemetry.sdk.resources import (
                Resource,  # type: ignore[import-untyped,import-not-found]
            )
            from opentelemetry.sdk.trace import (
                TracerProvider,  # type: ignore[import-untyped,import-not-found]
            )
            from opentelemetry.sdk.trace.export import (
                BatchSpanProcessor,  # type: ignore[import-untyped,import-not-found]
            )

            resource = Resource.create({"service.name": service_name})
            provider = TracerProvider(resource=resource)
            exporter = OTLPSpanExporter(endpoint=endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(provider)
            self._tracer = trace.get_tracer(service_name)
            self._initialized = True
        except ImportError:
            raise ImportError(
                "OTLP export requires: pip install opentelemetry-exporter-otlp opentelemetry-sdk"
            )

    def export(self, traces: list[ExecutionTrace]) -> None:
        """Export traces as OTLP spans."""
        if not self._initialized or not self._tracer:
            return

        for trace in traces:
            with self._tracer.start_as_current_span(
                f"eval:{trace.eval_id}",
                attributes={
                    "eval.id": str(trace.eval_id),
                    "eval.phase": trace.phase,
                    "eval.run_id": trace.run_id,
                    "eval.tokens": trace.token_usage.total_tokens,
                    "eval.cost": trace.token_usage.cost,
                    "eval.duration_ms": trace.duration_ms,
                },
            ) as span:
                for event in trace.events:
                    span.add_event(
                        name=event.event_type,
                        attributes={"latency_ms": event.latency_ms, **event.metadata},
                    )

    def close(self) -> None:
        """Shutdown OTLP exporter."""
        pass


class NoOpTraceExporter(BaseTraceExporter):
    """No-op exporter (traces disabled)."""

    output_path: str | Path = ""  # type: ignore[assignment]  # LSP compatibility: satisfies access in get_summary()

    def export(self, traces: list[ExecutionTrace]) -> None:
        pass

    def close(self) -> None:
        pass


def create_trace_exporter(
    format: str = "none",
    output_path: str | Path | None = None,
    otlp_endpoint: str | None = None,
) -> BaseTraceExporter:
    """Factory for trace exporters.

    Args:
        format: "jsonl", "otlp", or "none"
        output_path: Path for JSONL output
        otlp_endpoint: OTLP endpoint URL

    Returns:
        Configured trace exporter instance.
    """
    if format == "jsonl":
        path = output_path or "traces.jsonl"
        return JSONLTraceExporter(path)
    elif format == "otlp":
        if not otlp_endpoint:
            raise ValueError("OTLP export requires --otlp-endpoint")
        return OTLPTraceExporter(otlp_endpoint)
    else:
        return NoOpTraceExporter()


# ── SessionTelemetry ───────────────────────────────────────────



class LLMCallRecord(BaseModel):
    """A single LLM call record within a session."""

    role: Literal["simulator", "evaluator", "skill"] = "skill"
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    total_tokens: int = 0
    timestamp: float = Field(default_factory=time.time)


class SessionTelemetryTrace(BaseModel):
    """Per-session trace data aggregated from ExecutionTrace objects."""

    session_id: str = ""
    eval_case_id: int | str = 0
    llm_calls: list[LLMCallRecord] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)


class TelemetrySummary(BaseModel):
    """Aggregated token summary for a session."""

    total_input: int = 0
    total_output: int = 0
    total_cached: int = 0
    total: int = 0
    by_role: dict[str, dict[str, int]] = Field(default_factory=dict)
    session_id: str = ""
    eval_case_id: int | str = 0


class SessionTelemetry:
    """Session-level token aggregation consuming ExecutionTrace objects.

    Uses the same consumption pattern as TokenLedger — accepts ExecutionTrace
    objects directly (not EventBus events). This avoids creating a new event
    type and keeps SessionTelemetry aligned with existing aggregation patterns.
    Thread-safe: uses threading.Lock for dict access.
    """

    def __init__(
        self, max_sessions: int = 1000, max_age_seconds: int = 3600
    ) -> None:
        self.sessions: dict[str, SessionTelemetryTrace] = {}
        self._max_sessions = max_sessions
        self._max_age_seconds = max_age_seconds
        self._lock = threading.Lock()

    def create_session(self, session_id: str, eval_case_id: int) -> str:
        """Create a new session and return its ID."""
        with self._lock:
            self.sessions[session_id] = SessionTelemetryTrace(
                session_id=session_id, eval_case_id=eval_case_id
            )
            self._evict_if_needed()
            return session_id

    def _derive_role(self, phase: str) -> str:
        """Derive LLM call role from ExecutionTrace phase."""
        if phase in ("with_skill", "without_skill"):
            return "skill"
        elif phase == "grading":
            return "evaluator"
        elif phase == "judge":
            return "evaluator"
        elif phase == "simulator":
            return "simulator"
        return "skill"

    def record_trace(self, trace: ExecutionTrace) -> None:
        """Record an ExecutionTrace — session_id derived from run_id."""
        role = self._derive_role(trace.phase)
        record = LLMCallRecord(
            role=role,  # type: ignore[arg-type]
            input_tokens=trace.token_usage.input_tokens,
            output_tokens=trace.token_usage.output_tokens,
            total_tokens=trace.token_usage.total_tokens,
        )
        with self._lock:
            if trace.run_id not in self.sessions:
                eid: int | str | Any = trace.eval_id
                if isinstance(eid, (int, str)) and str(eid).lstrip("-").isdigit():
                    eid = int(eid)
                self.sessions[trace.run_id] = SessionTelemetryTrace(
                    session_id=trace.run_id,
                    eval_case_id=eid,
                )
            self.sessions[trace.run_id].llm_calls.append(record)
            self._evict_if_needed()

    def get_session_summary(
        self, session_id: str
    ) -> TelemetrySummary | None:
        """Get aggregated token summary for a session."""
        with self._lock:
            trace_data = self.sessions.get(session_id)
            if not trace_data:
                return None
            return self._build_summary(trace_data)

    def get_all_summaries(self) -> list[TelemetrySummary]:
        """Get aggregated summaries for all sessions."""
        with self._lock:
            return [self._build_summary(t) for t in self.sessions.values()]

    def _build_summary(self, trace_data: SessionTelemetryTrace) -> TelemetrySummary:
        total_input = 0
        total_output = 0
        total_cached = 0
        by_role: dict[str, dict[str, int]] = {}
        for call in trace_data.llm_calls:
            total_input += call.input_tokens
            total_output += call.output_tokens
            total_cached += call.cached_tokens
            if call.role not in by_role:
                by_role[call.role] = {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                }
            by_role[call.role]["input_tokens"] += call.input_tokens
            by_role[call.role]["output_tokens"] += call.output_tokens
            by_role[call.role]["total_tokens"] += call.total_tokens
        return TelemetrySummary(
            total_input=total_input,
            total_output=total_output,
            total_cached=total_cached,
            total=total_input + total_output,
            by_role=by_role,
            session_id=trace_data.session_id,
            eval_case_id=trace_data.eval_case_id,
        )

    def cleanup(self, max_sessions: int | None = None, max_age_seconds: float | None = None) -> int:
        """Evict sessions beyond limits. Returns number of evicted sessions."""
        max_s = max_sessions if max_sessions is not None else self._max_sessions
        max_age = max_age_seconds if max_age_seconds is not None else self._max_age_seconds
        now = time.time()
        evicted = 0
        with self._lock:
            stale = [
                sid
                for sid, t in self.sessions.items()
                if (now - t.created_at) > max_age
            ]
            for sid in stale:
                del self.sessions[sid]
                evicted += 1
            while len(self.sessions) > max_s:
                oldest = min(self.sessions.items(), key=lambda x: x[1].created_at)
                del self.sessions[oldest[0]]
                evicted += 1
        return evicted

    def flush(self) -> None:
        """Flush telemetry data — alias for cleanup() for runner compatibility."""
        self.cleanup()

    def _evict_if_needed(self) -> None:
        """Evict if over max_sessions (called with lock held)."""
        while len(self.sessions) > self._max_sessions:
            oldest = min(self.sessions.items(), key=lambda x: x[1].created_at)
            del self.sessions[oldest[0]]


# ── CompositeLedger ────────────────────────────────────────────


class CompositeLedger:
    """Composite ledger that fans out record_trace() to both TokenLedger and SessionTelemetry.

    Satisfies the same interface as TokenLedger for EvalRunner compatibility:
    - record_trace(trace) → calls both ledger.record_trace and telemetry.record_trace
    - flush() → calls both ledger.flush() and telemetry.cleanup()
    - Delegates aggregate(), get_summary(), etc. to the underlying TokenLedger
    - Exposes session_telemetry for report-level summary extraction
    """

    def __init__(self, ledger: Any, telemetry: SessionTelemetry | None = None) -> None:
        self._ledger = ledger
        self._telemetry = telemetry or SessionTelemetry()

    def record_trace(self, trace: ExecutionTrace) -> None:
        """Record a trace to both ledger and telemetry."""
        self._ledger.record_trace(trace)
        if self._telemetry:
            self._telemetry.record_trace(trace)

    def flush(self) -> None:
        """Flush both ledger and telemetry."""
        if hasattr(self._ledger, "flush"):
            self._ledger.flush()
        if self._telemetry:
            self._telemetry.cleanup()

    def __getattr__(self, name: str) -> Any:
        """Fall through to the underlying ledger for any unknown attributes."""
        return getattr(self._ledger, name)

    @property
    def session_telemetry(self) -> SessionTelemetry:
        return self._telemetry  # type: ignore[return-value]
