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
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

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
