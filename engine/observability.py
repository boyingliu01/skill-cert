"""Observability layer: EventBus + TraceExporter for skill-cert.

Design decisions (Delphi Review consensus):
- EventBus is a lightweight pub/sub for trace events
- TraceExporter supports JSONL (default) and optional OTLP
- Exceptions in EventBus are LOGGED (not silently swallowed)
- OTLP export failure raises ClickException when explicitly configured
"""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any

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

    output_path: str | Path = ""  # LSP compatibility: satisfies access in SessionTelemetry.get_summary()

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
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter  # type: ignore[import-untyped,import-not-found]
            from opentelemetry.sdk.resources import Resource  # type: ignore[import-untyped,import-not-found]
            from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import-untyped,import-not-found]
            from opentelemetry.sdk.trace.export import BatchSpanProcessor  # type: ignore[import-untyped,import-not-found]

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


class SessionTelemetry:
    """Session-level telemetry aggregator for skill-cert evaluations.
    
    Wraps EventBus and TraceExporter to provide:
    - Real-time trace aggregation across multiple evals
    - Token/cost metrics computation
    - Event publishing to registered handlers
    - Trace export to configured destinations
    
    Usage:
        telemetry = SessionTelemetry(
            event_bus=EventBus(),
            exporter=create_trace_exporter("jsonl", "traces.jsonl")
        )
        telemetry.record_trace(trace)
        telemetry.flush()  # Export all traces
    """
    
    def __init__(self, event_bus: EventBus | None = None, exporter: BaseTraceExporter | None = None):
        """Initialize SessionTelemetry.
        
        Args:
            event_bus: EventBus instance for publishing trace events
            exporter: TraceExporter instance for persisting traces
        """
        self.event_bus = event_bus or EventBus()
        self.exporter = exporter or NoOpTraceExporter()
        self._traces: list[ExecutionTrace] = []
        self._lock = threading.Lock()
        self._trace_count = 0
        self._event_count = 0
        self._total_duration_ms = 0.0
        self._total_tool_calls = 0
        self._start_time = time.time()
    
    def record_trace(self, trace: ExecutionTrace) -> None:
        """Record an execution trace.
        
        Args:
            trace: ExecutionTrace instance to record
        """
        with self._lock:
            self._traces.append(trace)
            self._trace_count += 1
            self._event_count += len(trace.events)
            self._total_duration_ms += trace.duration_ms
            self._total_tool_calls += trace.tool_call_count
            
            # Publish trace event via EventBus
            self.event_bus.publish_trace_event(trace)
    
    def get_traces(self) -> list[ExecutionTrace]:
        """Return all recorded traces (copy)."""
        with self._lock:
            return list(self._traces)
    
    def get_summary(self) -> dict[str, Any]:
        """Get telemetry summary for reporter integration.
        
        Returns:
            Dictionary with aggregated metrics for ObservabilitySection
        """
        with self._lock:
            return {
                "trace_count": self._trace_count,
                "total_events": self._event_count,
                "total_duration_ms": self._total_duration_ms,
                "total_tool_calls": self._total_tool_calls,
                "session_duration_s": time.time() - self._start_time,
                "export_path": str(self.exporter.output_path) if hasattr(self.exporter, 'output_path') else "",
                "export_format": "jsonl" if isinstance(self.exporter, JSONLTraceExporter) else "none",
            }
    
    def flush(self) -> None:
        """Export all traces and close exporter."""
        with self._lock:
            if self._traces:
                self.exporter.export(self._traces)
                self._traces.clear()
        self.exporter.close()
    
    def __enter__(self) -> "SessionTelemetry":
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - ensure flush."""
        self.flush()
