"""Tests for engine/observability.py — EventBus, TraceExporter, SessionTelemetry."""

import json
import time

import pytest

from engine.observability import (
    CompositeLedger,
    EventBus,
    JSONLTraceExporter,
    NoOpTraceExporter,
    SessionTelemetry,
    create_trace_exporter,
)
from engine.token_ledger import TokenLedger
from engine.trace_models import ExecutionTrace, TokenAccounting


class TestEventBus:
    """Tests for EventBus pub/sub."""

    def test_subscribe_and_publish(self):
        bus = EventBus()
        received = []
        bus.subscribe("test_event", lambda et, p: received.append((et, p)))
        bus.publish("test_event", {"key": "value"})
        assert len(received) == 1
        assert received[0][0] == "test_event"
        assert received[0][1]["key"] == "value"

    def test_wildcard_subscriber(self):
        bus = EventBus()
        received = []
        bus.subscribe("*", lambda et, p: received.append(et))
        bus.publish("event1", {})
        bus.publish("event2", {})
        assert len(received) == 2

    def test_multiple_subscribers(self):
        bus = EventBus()
        received1 = []
        received2 = []
        bus.subscribe("test", lambda et, p: received1.append(1))
        bus.subscribe("test", lambda et, p: received2.append(2))
        bus.publish("test", {})
        assert len(received1) == 1
        assert len(received2) == 1

    def test_handler_exception_logged(self):
        bus = EventBus()
        bus.subscribe("test", lambda et, p: 1 / 0)  # Will raise ZeroDivisionError
        # Should not raise, just log
        bus.publish("test", {})

    def test_publish_trace_event(self):
        bus = EventBus()
        received = []
        bus.subscribe("TraceComplete", lambda et, p: received.append(p))
        trace = ExecutionTrace(eval_id=1, phase="with_skill")
        trace.token_usage = TokenAccounting(total_tokens=100, cost=0.01)
        bus.publish_trace_event(trace)
        assert len(received) == 1
        assert received[0]["eval_id"] == 1
        assert received[0]["tokens"] == 100

    def test_clear(self):
        bus = EventBus()
        bus.subscribe("test", lambda et, p: None)
        bus.clear()
        # After clear, no subscribers
        received = []
        bus.subscribe("test2", lambda et, p: received.append(1))
        bus.publish("test", {})  # Should not trigger
        assert len(received) == 0


class TestJSONLTraceExporter:
    """Tests for JSONLTraceExporter."""

    def test_export_creates_file(self, tmp_path):
        output_path = tmp_path / "traces.jsonl"
        exporter = JSONLTraceExporter(output_path)
        trace = ExecutionTrace(eval_id=1)
        trace.record_llm_call(model="gpt-4", input_tokens=100, output_tokens=50, latency_ms=100)
        exporter.export([trace])
        assert output_path.exists()
        lines = output_path.read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["eval_id"] == 1

    def test_export_appends(self, tmp_path):
        output_path = tmp_path / "traces.jsonl"
        exporter = JSONLTraceExporter(output_path)
        trace1 = ExecutionTrace(eval_id=1)
        trace2 = ExecutionTrace(eval_id=2)
        exporter.export([trace1])
        exporter.export([trace2])
        lines = output_path.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_export_multiple_traces(self, tmp_path):
        output_path = tmp_path / "traces.jsonl"
        exporter = JSONLTraceExporter(output_path)
        traces = [ExecutionTrace(eval_id=i) for i in range(5)]
        exporter.export(traces)
        lines = output_path.read_text().strip().split("\n")
        assert len(lines) == 5


class TestNoOpTraceExporter:
    """Tests for NoOpTraceExporter."""

    def test_export_noop(self):
        exporter = NoOpTraceExporter()
        trace = ExecutionTrace(eval_id=1)
        exporter.export([trace])  # Should not raise

    def test_close_noop(self):
        exporter = NoOpTraceExporter()
        exporter.close()  # Should not raise


class TestCreateTraceExporter:
    """Tests for create_trace_exporter factory."""

    def test_create_jsonl(self, tmp_path):
        exporter = create_trace_exporter("jsonl", output_path=tmp_path / "traces.jsonl")
        assert isinstance(exporter, JSONLTraceExporter)

    def test_create_none(self):
        exporter = create_trace_exporter("none")
        assert isinstance(exporter, NoOpTraceExporter)

    def test_create_otlp_without_endpoint(self):
        with pytest.raises(ValueError, match="OTLP"):
            create_trace_exporter("otlp")

    def test_create_default(self):
        exporter = create_trace_exporter()
        assert isinstance(exporter, NoOpTraceExporter)


class TestSessionTelemetry:
    """Tests for SessionTelemetry class."""


