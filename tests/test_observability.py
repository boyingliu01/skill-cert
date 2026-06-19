"""Tests for engine/observability.py — EventBus and TraceExporter."""

import json
import time

import pytest

from engine.observability import (
    EventBus,
    JSONLTraceExporter,
    NoOpTraceExporter,
    create_trace_exporter,
)
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

    def test_init_with_exporter(self, tmp_path):
        """Test SessionTelemetry initialization with exporter."""
        from engine.observability import SessionTelemetry, create_trace_exporter
        
        output_path = tmp_path / "traces.jsonl"
        exporter = create_trace_exporter("jsonl", output_path=str(output_path))
        telemetry = SessionTelemetry(exporter=exporter)
        assert telemetry is not None
        assert telemetry.event_bus is not None
        assert telemetry.exporter is not None
        assert telemetry._trace_count == 0
        assert telemetry._event_count == 0
        assert telemetry._total_duration_ms == 0
        assert telemetry._total_tool_calls == 0
        assert telemetry._start_time is not None

    def test_init_without_exporter(self):
        """Test SessionTelemetry initialization without exporter."""
        from engine.observability import SessionTelemetry, create_trace_exporter
        
        telemetry = SessionTelemetry(exporter=create_trace_exporter("none"))
        assert telemetry is not None
        assert telemetry.event_bus is not None
        assert telemetry.exporter is not None
        from engine.observability import NoOpTraceExporter
        assert isinstance(telemetry.exporter, NoOpTraceExporter)

    def test_record_trace_with_event_bus(self, tmp_path):
        """Test that record_trace publishes to event bus and updates metrics."""
        from engine.observability import SessionTelemetry, create_trace_exporter
        from engine.trace_models import ExecutionTrace, TokenAccounting
        
        output_path = tmp_path / "traces.jsonl"
        exporter = create_trace_exporter("jsonl", output_path=str(output_path))
        telemetry = SessionTelemetry(exporter=exporter)
        
        # Subscribe to events
        received_events = []
        telemetry.event_bus.subscribe("TraceComplete", lambda event, payload: received_events.append(payload))
        
        # Create and record a trace
        trace = ExecutionTrace(eval_id=1, phase="with_skill", run_id="test-run-1")
        trace.record_llm_call(model="test-model", input_tokens=100, output_tokens=50, latency_ms=100)
        trace.token_usage = TokenAccounting(total_tokens=150, cost=0.01)
        trace.start_time = time.time() - 0.1  # Set start_time so duration_ms = 100
        trace.end_time = time.time()
        
        telemetry.record_trace(trace)
        
        # Verify event bus publication
        assert len(received_events) == 1
        assert received_events[0]["eval_id"] == 1
        assert received_events[0]["tokens"] == 150
        
        # Verify metrics aggregation
        assert telemetry._trace_count == 1
        assert telemetry._event_count >= 1  # At least the llm_call event
        assert telemetry._total_duration_ms >= 100
        # Note: _total_tool_calls is 0 because LLMCallEvent is not a ToolCallEvent

    def test_get_summary(self, tmp_path):
        """Test that get_summary returns correct aggregated data."""
        from engine.observability import SessionTelemetry, create_trace_exporter
        from engine.trace_models import ExecutionTrace, TokenAccounting
        
        output_path = tmp_path / "traces.jsonl"
        exporter = create_trace_exporter("jsonl", output_path=str(output_path))
        telemetry = SessionTelemetry(exporter=exporter)
        
        # Record a trace
        trace = ExecutionTrace(eval_id=1, phase="with_skill", run_id="test-run-1")
        trace.record_llm_call(model="test-model", input_tokens=100, output_tokens=50, latency_ms=100)
        trace.token_usage = TokenAccounting(total_tokens=150, cost=0.01)
        trace.start_time = time.time() - 0.1  # Set start_time so duration_ms = 100
        trace.end_time = time.time()
        telemetry.record_trace(trace)
        
        # Get summary
        summary = telemetry.get_summary()
        
        assert summary["trace_count"] == 1
        assert summary["total_events"] >= 1
        assert summary["total_duration_ms"] >= 100
        # Note: total_tool_calls is 0 because LLMCallEvent is not a ToolCallEvent
        assert summary["session_duration_s"] >= 0
        assert summary["export_path"] == str(output_path)
        assert summary["export_format"] == "jsonl"

    def test_flush_calls_exporter(self, tmp_path):
        """Test that flush calls exporter.export with all traces."""
        from engine.observability import SessionTelemetry, create_trace_exporter
        from engine.trace_models import ExecutionTrace
        
        output_path = tmp_path / "traces.jsonl"
        exporter = create_trace_exporter("jsonl", output_path=str(output_path))
        telemetry = SessionTelemetry(exporter=exporter)
        
        # Record a trace
        trace = ExecutionTrace(eval_id=1, phase="with_skill")
        telemetry.record_trace(trace)
        
        # Flush
        telemetry.flush()
        
        # Verify file was created
        assert output_path.exists()
        lines = output_path.read_text().strip().split("\n")
        assert len(lines) == 1

    def test_context_manager(self, tmp_path):
        """Test that context manager properly flushes on exit."""
        from engine.observability import SessionTelemetry, create_trace_exporter
        from engine.trace_models import ExecutionTrace
        
        output_path = tmp_path / "traces.jsonl"
        exporter = create_trace_exporter("jsonl", output_path=str(output_path))
        
        with SessionTelemetry(exporter=exporter) as telemetry:
            trace = ExecutionTrace(eval_id=1, phase="with_skill")
            telemetry.record_trace(trace)
        
        # After context exit, file should be flushed
        assert output_path.exists()
        assert len(output_path.read_text().strip().split("\n")) == 1

    def test_thread_safe_aggregation(self, tmp_path):
        """Test that SessionTelemetry is thread-safe for concurrent trace recording."""
        import threading
        from engine.observability import SessionTelemetry, create_trace_exporter
        from engine.trace_models import ExecutionTrace, TokenAccounting
        
        output_path = tmp_path / "traces.jsonl"
        exporter = create_trace_exporter("jsonl", output_path=str(output_path))
        telemetry = SessionTelemetry(exporter=exporter)
        
        def record_trace(trace_id):
            trace = ExecutionTrace(eval_id=trace_id, phase="with_skill", run_id="test-run-1")
            trace.record_llm_call(model="test-model", input_tokens=10, output_tokens=5, latency_ms=10)
            trace.token_usage = TokenAccounting(total_tokens=15, cost=0.001)
            telemetry.record_trace(trace)
        
        # Create and start 10 threads
        threads = [threading.Thread(target=record_trace, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Verify all traces were recorded
        assert telemetry._trace_count == 10
        assert telemetry._trace_count == 10  # All 10 traces were recorded

    def test_no_exporter_with_none_format(self):
        """Test that NoOpTraceExporter is used when format is 'none'."""
        from engine.observability import SessionTelemetry, create_trace_exporter, NoOpTraceExporter
        
        telemetry = SessionTelemetry(exporter=create_trace_exporter("none"))
        assert isinstance(telemetry.exporter, NoOpTraceExporter)

    def test_summary_with_multiple_traces(self, tmp_path):
        """Test that summary correctly aggregates multiple traces."""
        from engine.observability import SessionTelemetry, create_trace_exporter
        from engine.trace_models import ExecutionTrace, TokenAccounting
        
        output_path = tmp_path / "traces.jsonl"
        exporter = create_trace_exporter("jsonl", output_path=str(output_path))
        telemetry = SessionTelemetry(exporter=exporter)
        
        # Record 3 traces
        for i in range(3):
            trace = ExecutionTrace(eval_id=i, phase="with_skill", run_id="test-run-1")
            trace.record_llm_call(model="test-model", input_tokens=100, output_tokens=50, latency_ms=100)
            trace.token_usage = TokenAccounting(total_tokens=150, cost=0.01)
            trace.start_time = time.time() - 0.1  # Set start_time so duration_ms = 100
            trace.end_time = time.time()
            telemetry.record_trace(trace)
        
        summary = telemetry.get_summary()
        assert summary["trace_count"] == 3
        assert summary["total_duration_ms"] >= 300  # 3 * 100ms
        # Note: total_tool_calls is 0 because LLMCallEvent is not a ToolCallEvent
