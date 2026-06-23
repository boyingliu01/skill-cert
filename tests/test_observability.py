"""Tests for engine/observability.py — EventBus, TraceExporter, SessionTelemetry."""

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from engine.observability import (
    CompositeLedger,
    EventBus,
    JSONLTraceExporter,
    NoOpTraceExporter,
    OTLPTraceExporter,
    SessionTelemetry,
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

    def test_create_session(self):
        telemetry = SessionTelemetry()
        sid = telemetry.create_session("sess-1", eval_case_id=42)
        assert sid == "sess-1"
        assert "sess-1" in telemetry.sessions
        assert telemetry.sessions["sess-1"].eval_case_id == 42

    def test_record_trace_creates_session_implicitly(self):
        telemetry = SessionTelemetry()
        trace = ExecutionTrace(run_id="run-abc", eval_id=7, phase="with_skill")
        trace.token_usage = TokenAccounting(input_tokens=100, output_tokens=50, total_tokens=150)
        telemetry.record_trace(trace)
        assert "run-abc" in telemetry.sessions
        assert len(telemetry.sessions["run-abc"].llm_calls) == 1
        assert telemetry.sessions["run-abc"].llm_calls[0].role == "skill"

    def test_record_trace_appends_to_existing_session(self):
        telemetry = SessionTelemetry()
        telemetry.create_session("sess-2", eval_case_id=1)
        trace1 = ExecutionTrace(run_id="sess-2", eval_id=1, phase="with_skill")
        trace1.token_usage = TokenAccounting(input_tokens=10, output_tokens=20, total_tokens=30)
        trace2 = ExecutionTrace(run_id="sess-2", eval_id=1, phase="grading")
        trace2.token_usage = TokenAccounting(input_tokens=5, output_tokens=15, total_tokens=20)
        telemetry.record_trace(trace1)
        telemetry.record_trace(trace2)
        assert len(telemetry.sessions["sess-2"].llm_calls) == 2

    def test_get_session_summary(self):
        telemetry = SessionTelemetry()
        trace = ExecutionTrace(run_id="sess-3", eval_id=10, phase="with_skill")
        trace.token_usage = TokenAccounting(input_tokens=200, output_tokens=100, total_tokens=300)
        telemetry.record_trace(trace)
        summary = telemetry.get_session_summary("sess-3")
        assert summary is not None
        assert summary.total_input == 200
        assert summary.total_output == 100
        assert summary.total == 300
        assert summary.session_id == "sess-3"
        assert summary.eval_case_id == 10
        assert "skill" in summary.by_role

    def test_get_session_summary_not_found(self):
        telemetry = SessionTelemetry()
        assert telemetry.get_session_summary("nonexistent") is None

    def test_get_all_summaries(self):
        telemetry = SessionTelemetry()
        telemetry.create_session("a", 1)
        telemetry.create_session("b", 2)
        summaries = telemetry.get_all_summaries()
        assert len(summaries) == 2
        ids = {s.session_id for s in summaries}
        assert ids == {"a", "b"}

    def test_cleanup_by_age(self):
        telemetry = SessionTelemetry(max_age_seconds=10)
        telemetry.create_session("old", 1)
        telemetry.sessions["old"].created_at = time.time() - 100
        telemetry.create_session("new", 2)
        evicted = telemetry.cleanup()
        assert evicted == 1
        assert "old" not in telemetry.sessions
        assert "new" in telemetry.sessions

    def test_cleanup_by_max_sessions(self):
        telemetry = SessionTelemetry(max_sessions=2)
        telemetry.create_session("s1", 1)
        time.sleep(0.01)
        telemetry.create_session("s2", 2)
        time.sleep(0.01)
        telemetry.create_session("s3", 3)
        assert len(telemetry.sessions) <= 2

    def test_cleanup_explicit_max_sessions(self):
        telemetry = SessionTelemetry(max_sessions=100)
        for i in range(5):
            telemetry.create_session(f"s{i}", i)
        evicted = telemetry.cleanup(max_sessions=2)
        assert evicted == 3
        assert len(telemetry.sessions) == 2

    def test_derive_role_with_skill(self):
        telemetry = SessionTelemetry()
        assert telemetry._derive_role("with_skill") == "skill"

    def test_derive_role_without_skill(self):
        telemetry = SessionTelemetry()
        assert telemetry._derive_role("without_skill") == "skill"

    def test_derive_role_grading(self):
        telemetry = SessionTelemetry()
        assert telemetry._derive_role("grading") == "evaluator"

    def test_derive_role_judge(self):
        telemetry = SessionTelemetry()
        assert telemetry._derive_role("judge") == "evaluator"

    def test_derive_role_simulator(self):
        telemetry = SessionTelemetry()
        assert telemetry._derive_role("simulator") == "simulator"

    def test_derive_role_unknown_defaults_to_skill(self):
        telemetry = SessionTelemetry()
        assert telemetry._derive_role("unknown_phase") == "skill"

    def test_build_summary_multiple_roles(self):
        telemetry = SessionTelemetry()
        t1 = ExecutionTrace(run_id="multi", eval_id=1, phase="with_skill")
        t1.token_usage = TokenAccounting(input_tokens=100, output_tokens=50, total_tokens=150)
        t2 = ExecutionTrace(run_id="multi", eval_id=1, phase="grading")
        t2.token_usage = TokenAccounting(input_tokens=30, output_tokens=20, total_tokens=50)
        telemetry.record_trace(t1)
        telemetry.record_trace(t2)
        summary = telemetry.get_session_summary("multi")
        assert summary.total_input == 130
        assert summary.total_output == 70
        assert summary.total == 200
        assert "skill" in summary.by_role
        assert "evaluator" in summary.by_role
        assert summary.by_role["skill"]["input_tokens"] == 100
        assert summary.by_role["evaluator"]["input_tokens"] == 30

    def test_record_trace_eval_id_string(self):
        telemetry = SessionTelemetry()
        trace = ExecutionTrace(run_id="run-str", eval_id="eval-99", phase="with_skill")
        trace.token_usage = TokenAccounting(input_tokens=10, output_tokens=5, total_tokens=15)
        telemetry.record_trace(trace)
        assert telemetry.sessions["run-str"].eval_case_id == "eval-99"

    def test_record_trace_eval_id_numeric_string(self):
        telemetry = SessionTelemetry()
        trace = ExecutionTrace(run_id="run-numstr", eval_id="42", phase="with_skill")
        trace.token_usage = TokenAccounting(input_tokens=10, output_tokens=5, total_tokens=15)
        telemetry.record_trace(trace)
        assert telemetry.sessions["run-numstr"].eval_case_id == 42


class TestCompositeLedger:
    """Tests for CompositeLedger class."""

    def test_record_trace_fanout(self):
        mock_ledger = MagicMock()
        telemetry = SessionTelemetry()
        composite = CompositeLedger(mock_ledger, telemetry)
        trace = ExecutionTrace(run_id="comp-1", eval_id=1, phase="with_skill")
        trace.token_usage = TokenAccounting(input_tokens=50, output_tokens=25, total_tokens=75)
        composite.record_trace(trace)
        mock_ledger.record_trace.assert_called_once_with(trace)
        assert "comp-1" in telemetry.sessions

    def test_flush(self):
        mock_ledger = MagicMock()
        telemetry = SessionTelemetry()
        composite = CompositeLedger(mock_ledger, telemetry)
        composite.flush()
        mock_ledger.flush.assert_called_once()

    def test_flush_ledger_without_flush_method(self):
        mock_ledger = MagicMock(spec=[])
        telemetry = SessionTelemetry()
        composite = CompositeLedger(mock_ledger, telemetry)
        composite.flush()

    def test_getattr_delegation(self):
        mock_ledger = MagicMock()
        mock_ledger.some_custom_attr = "custom_value"
        composite = CompositeLedger(mock_ledger)
        assert composite.some_custom_attr == "custom_value"

    def test_getattr_delegation_method(self):
        mock_ledger = MagicMock()
        mock_ledger.aggregate.return_value = {"total": 100}
        composite = CompositeLedger(mock_ledger)
        result = composite.aggregate()
        mock_ledger.aggregate.assert_called_once()
        assert result == {"total": 100}

    def test_session_telemetry_property(self):
        mock_ledger = MagicMock()
        telemetry = SessionTelemetry()
        composite = CompositeLedger(mock_ledger, telemetry)
        assert composite.session_telemetry is telemetry

    def test_session_telemetry_default_created(self):
        mock_ledger = MagicMock()
        composite = CompositeLedger(mock_ledger)
        assert isinstance(composite.session_telemetry, SessionTelemetry)

    def test_record_trace_without_telemetry(self):
        mock_ledger = MagicMock()
        composite = CompositeLedger(mock_ledger, telemetry=None)
        trace = ExecutionTrace(run_id="no-telem", eval_id=1, phase="with_skill")
        trace.token_usage = TokenAccounting(input_tokens=10, output_tokens=5, total_tokens=15)
        composite.record_trace(trace)
        mock_ledger.record_trace.assert_called_once_with(trace)


class TestOTLPTraceExporter:
    """Tests for OTLPTraceExporter class."""

    def test_init_raises_import_error(self):
        with patch.dict("sys.modules", {
            "opentelemetry": None,
            "opentelemetry.exporter.otlp.proto.grpc.trace_exporter": None,
            "opentelemetry.sdk.resources": None,
            "opentelemetry.sdk.trace": None,
            "opentelemetry.sdk.trace.export": None,
        }):
            with pytest.raises(ImportError, match="OTLP export requires"):
                OTLPTraceExporter("http://localhost:4317")

    def test_export_when_not_initialized(self):
        exporter = OTLPTraceExporter.__new__(OTLPTraceExporter)
        exporter.endpoint = "http://localhost:4317"
        exporter.service_name = "skill-cert"
        exporter._initialized = False
        exporter._tracer = None
        trace = ExecutionTrace(eval_id=1)
        exporter.export([trace])

    def test_close(self):
        exporter = OTLPTraceExporter.__new__(OTLPTraceExporter)
        exporter.endpoint = "http://localhost:4317"
        exporter.service_name = "skill-cert"
        exporter._initialized = False
        exporter._tracer = None
        exporter.close()


class TestJSONLTraceExporterExtra:
    """Additional tests for JSONLTraceExporter edge cases."""

    def test_close_noop(self):
        """JSONLTraceExporter.close() is a no-op (covers line 131)."""
        exporter = JSONLTraceExporter.__new__(JSONLTraceExporter)
        exporter.output_path = "/tmp/nonexistent/traces.jsonl"
        exporter._file = None
        exporter._lock = __import__("threading").Lock()
        exporter.close()  # Should not raise


class TestCreateTraceExporterExtra:
    """Additional tests for create_trace_exporter factory."""

    def test_create_otlp_with_endpoint_raises_import_error(self):
        """create_trace_exporter('otlp') raises ImportError (covers line 235)."""
        with patch.dict("sys.modules", {
            "opentelemetry": None,
            "opentelemetry.exporter.otlp.proto.grpc.trace_exporter": None,
            "opentelemetry.sdk.resources": None,
            "opentelemetry.sdk.trace": None,
            "opentelemetry.sdk.trace.export": None,
        }):
            with pytest.raises(ImportError, match="OTLP export requires"):
                create_trace_exporter("otlp", otlp_endpoint="http://localhost:4317")


class TestOTLPTraceExporterExtra:
    """Additional tests for OTLPTraceExporter — success path and export loop."""

    def test_init_success_with_mocked_otlp(self):
        mock_otel_trace = MagicMock()

        mock_exporter_cls = MagicMock()
        mock_resource_cls = MagicMock(return_value="resource-obj")
        mock_tracer_provider_cls = MagicMock()
        mock_batch_span_processor_cls = MagicMock()
        mock_tracer = MagicMock()
        mock_otel_trace.get_tracer.return_value = mock_tracer

        modules = {
            "opentelemetry": mock_otel_trace,
            "opentelemetry.exporter.otlp.proto.grpc.trace_exporter": MagicMock(
                OTLPSpanExporter=mock_exporter_cls
            ),
            "opentelemetry.sdk.resources": MagicMock(Resource=mock_resource_cls),
            "opentelemetry.sdk.trace": MagicMock(TracerProvider=mock_tracer_provider_cls),
            "opentelemetry.sdk.trace.export": MagicMock(
                BatchSpanProcessor=mock_batch_span_processor_cls
            ),
        }

        with patch.dict("sys.modules", modules):
            exporter = OTLPTraceExporter("http://localhost:4317", "test-service")
            assert exporter._initialized is True
            mock_exporter_cls.assert_called_once()

    def test_export_with_tracer(self):
        from engine.trace_models import LLMCallEvent

        ctx = MagicMock()
        mock_span = MagicMock()
        ctx.__enter__ = MagicMock(return_value=mock_span)
        ctx.__exit__ = MagicMock(return_value=None)
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value = ctx

        exporter = OTLPTraceExporter.__new__(OTLPTraceExporter)
        exporter.endpoint = "http://localhost:4317"
        exporter.service_name = "test-service"
        exporter._initialized = True
        exporter._tracer = mock_tracer

        trace = ExecutionTrace(eval_id=42, phase="with_skill")
        trace.add_event(LLMCallEvent(model="gpt-4", latency_ms=150, total_tokens=100))
        trace.token_usage = TokenAccounting(total_tokens=100, cost=0.01)
        exporter.export([trace])

        mock_tracer.start_as_current_span.assert_called_once()
        args, kwargs = mock_tracer.start_as_current_span.call_args
        assert "eval:42" in args[0]
        assert kwargs["attributes"]["eval.id"] == "42"
        assert kwargs["attributes"]["eval.tokens"] == 100

    def test_export_multiple_traces(self):
        ctx = MagicMock()
        mock_span = MagicMock()
        ctx.__enter__ = MagicMock(return_value=mock_span)
        ctx.__exit__ = MagicMock(return_value=None)
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value = ctx

        exporter = OTLPTraceExporter.__new__(OTLPTraceExporter)
        exporter.endpoint = "http://localhost:4317"
        exporter.service_name = "test-service"
        exporter._initialized = True
        exporter._tracer = mock_tracer

        traces = [
            ExecutionTrace(eval_id=i, phase="with_skill")
            for i in range(3)
        ]
        exporter.export(traces)
        assert mock_tracer.start_as_current_span.call_count == 3
