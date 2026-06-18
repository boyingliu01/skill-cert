"""Tests for engine/observability.py — EventBus, TraceExporter, SessionTelemetry."""

import json

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
    """Tests for SessionTelemetry aggregation."""

    def test_create_session(self):
        telemetry = SessionTelemetry()
        sid = telemetry.create_session("session-1", 42)
        assert sid == "session-1"
        assert telemetry.sessions["session-1"].eval_case_id == 42

    def test_record_trace_creates_session(self):
        telemetry = SessionTelemetry()
        trace = ExecutionTrace(run_id="run-1", eval_id=1, phase="with_skill")
        trace.token_usage = TokenAccounting(input_tokens=50, output_tokens=30, total_tokens=80)
        telemetry.record_trace(trace)
        assert "run-1" in telemetry.sessions
        assert len(telemetry.sessions["run-1"].llm_calls) == 1

    def test_record_trace_derives_role(self):
        telemetry = SessionTelemetry()
        trace = ExecutionTrace(run_id="r1", eval_id=1, phase="grading")
        trace.token_usage = TokenAccounting(input_tokens=10, output_tokens=5, total_tokens=15)
        telemetry.record_trace(trace)
        assert telemetry.sessions["r1"].llm_calls[0].role == "evaluator"

    def test_record_trace_simulator_role(self):
        telemetry = SessionTelemetry()
        trace = ExecutionTrace(run_id="r1", eval_id=1, phase="simulator")
        trace.token_usage = TokenAccounting(input_tokens=5, output_tokens=10, total_tokens=15)
        telemetry.record_trace(trace)
        assert telemetry.sessions["r1"].llm_calls[0].role == "simulator"

    def test_multiple_traces_same_session(self):
        telemetry = SessionTelemetry()
        for i in range(3):
            trace = ExecutionTrace(run_id="sess-1", eval_id=i, phase="with_skill")
            trace.token_usage = TokenAccounting(
                input_tokens=10, output_tokens=5, total_tokens=15
            )
            telemetry.record_trace(trace)
        assert len(telemetry.sessions["sess-1"].llm_calls) == 3

    def test_multiple_sessions(self):
        telemetry = SessionTelemetry()
        for sid in ("a", "b"):
            trace = ExecutionTrace(run_id=sid, eval_id=1, phase="with_skill")
            trace.token_usage = TokenAccounting(input_tokens=10, output_tokens=5, total_tokens=15)
            telemetry.record_trace(trace)
        assert set(telemetry.sessions.keys()) == {"a", "b"}

    def test_get_session_summary(self):
        telemetry = SessionTelemetry()
        telemetry.create_session("sess-1", 1)
        for _ in range(2):
            trace = ExecutionTrace(run_id="sess-1", eval_id=1, phase="with_skill")
            trace.token_usage = TokenAccounting(
                input_tokens=50, output_tokens=30, total_tokens=80
            )
            telemetry.record_trace(trace)
        summary = telemetry.get_session_summary("sess-1")
        assert summary is not None
        assert summary.total_input == 100
        assert summary.total_output == 60
        assert summary.total == 160
        assert "skill" in summary.by_role

    def test_get_session_summary_nonexistent(self):
        telemetry = SessionTelemetry()
        assert telemetry.get_session_summary("no-such") is None

    def test_get_all_summaries(self):
        telemetry = SessionTelemetry()
        for sid in ("s1", "s2"):
            telemetry.create_session(sid, 1)
            trace = ExecutionTrace(run_id=sid, eval_id=1, phase="with_skill")
            trace.token_usage = TokenAccounting(input_tokens=10, output_tokens=5, total_tokens=15)
            telemetry.record_trace(trace)
        summaries = telemetry.get_all_summaries()
        assert len(summaries) == 2

    def test_cleanup_by_age(self):
        import time as _time
        telemetry = SessionTelemetry(max_age_seconds=0)
        telemetry.create_session("old", 1)
        _time.sleep(0.01)
        evicted = telemetry.cleanup(max_age_seconds=0.005)
        assert evicted >= 1
        assert "old" not in telemetry.sessions

    def test_cleanup_by_count(self):
        telemetry = SessionTelemetry(max_sessions=100)
        for i in range(5):
            telemetry.create_session(f"s{i}", i)
        evicted = telemetry.cleanup(max_sessions=2)
        assert evicted >= 3
        assert len(telemetry.sessions) <= 2

    def test_eviction_on_create(self):
        telemetry = SessionTelemetry(max_sessions=2)
        for i in range(5):
            telemetry.create_session(f"s{i}", i)
        assert len(telemetry.sessions) <= 2

    def test_summary_by_role(self):
        telemetry = SessionTelemetry()
        sid = "sess-1"
        telemetry.create_session(sid, 1)

        skill_trace = ExecutionTrace(run_id=sid, eval_id=1, phase="with_skill")
        skill_trace.token_usage = TokenAccounting(
            input_tokens=50, output_tokens=30, total_tokens=80
        )
        telemetry.record_trace(skill_trace)

        eval_trace = ExecutionTrace(run_id=sid, eval_id=1, phase="grading")
        eval_trace.token_usage = TokenAccounting(input_tokens=10, output_tokens=5, total_tokens=15)
        telemetry.record_trace(eval_trace)

        summary = telemetry.get_session_summary(sid)
        assert summary is not None
        assert summary.by_role["skill"]["input_tokens"] == 50
        assert summary.by_role["skill"]["output_tokens"] == 30
        assert summary.by_role["evaluator"]["input_tokens"] == 10
        assert summary.by_role["evaluator"]["output_tokens"] == 5


class TestCompositeLedger:
    """Tests for CompositeLedger — fans out record_trace() to TokenLedger + SessionTelemetry."""

    def test_record_trace_fans_to_both(self):
        ledger = TokenLedger()
        telemetry = SessionTelemetry()
        composite = CompositeLedger(ledger, telemetry)

        trace = ExecutionTrace(run_id="run-1", eval_id=1, phase="with_skill")
        trace.token_usage = TokenAccounting(input_tokens=50, output_tokens=30, total_tokens=80)
        composite.record_trace(trace)

        # TokenLedger has the trace
        assert ledger.trace_count == 1
        # SessionTelemetry has the trace
        assert "run-1" in telemetry.sessions
        assert len(telemetry.sessions["run-1"].llm_calls) == 1

    def test_multiple_traces_fan_to_both(self):
        ledger = TokenLedger()
        telemetry = SessionTelemetry()
        composite = CompositeLedger(ledger, telemetry)

        for i in range(3):
            trace = ExecutionTrace(run_id=f"run-{i}", eval_id=i, phase="with_skill")
            trace.token_usage = TokenAccounting(input_tokens=10, output_tokens=5, total_tokens=15)
            composite.record_trace(trace)

        assert ledger.trace_count == 3
        assert len(telemetry.get_all_summaries()) == 3

    def test_flush_calls_both(self):
        ledger = TokenLedger()
        telemetry = SessionTelemetry()
        composite = CompositeLedger(ledger, telemetry)

        for i in range(3):
            trace = ExecutionTrace(run_id=f"r-{i}", eval_id=i, phase="with_skill")
            trace.token_usage = TokenAccounting(input_tokens=5, output_tokens=3, total_tokens=8)
            composite.record_trace(trace)

        composite.flush()

        # After flush, TokenLedger should recompute
        assert ledger.trace_count == 3
        # SessionTelemetry cleanup should not evict (under limits)
        assert len(telemetry.sessions) == 3

    def test_delegates_ledger_methods(self):
        ledger = TokenLedger()
        composite = CompositeLedger(ledger, SessionTelemetry())

        trace = ExecutionTrace(run_id="r1", eval_id=1, phase="with_skill")
        trace.token_usage = TokenAccounting(input_tokens=10, output_tokens=5, total_tokens=15)
        # Use aggregate() directly; record_trace already appended under the hood
        composite.aggregate([trace])
        summary = composite.get_summary()
        assert summary["total_tokens"] == 15
        assert summary["trace_count"] == 1

    def test_session_telemetry_property(self):
        telemetry = SessionTelemetry()
        composite = CompositeLedger(TokenLedger(), telemetry)
        assert composite.session_telemetry is telemetry

    def test_session_telemetry_summary_via_composite(self):
        """Session telemetry summaries are accessible after record_trace through composite."""
        composite = CompositeLedger(TokenLedger(), SessionTelemetry())

        for i in range(2):
            trace = ExecutionTrace(run_id=f"sess-{i}", eval_id=i, phase="with_skill")
            trace.token_usage = TokenAccounting(input_tokens=10, output_tokens=5, total_tokens=15)
            composite.record_trace(trace)

        summaries = composite.session_telemetry.get_all_summaries()
        assert len(summaries) == 2
        assert all(s.total == 15 for s in summaries)
