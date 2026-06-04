"""Tests for engine/trace_models.py — ExecutionTrace, TokenAccounting, TraceEvent."""

import time

import pytest

from engine.trace_models import (
    BudgetAlert,
    EnvelopeTraceDTO,
    ErrorEvent,
    ExecutionTrace,
    LLMCallEvent,
    StepCompleteEvent,
    TokenAccounting,
    ToolCallEvent,
    ToolResultEvent,
    TurnStartEvent,
)


class TestTokenAccounting:
    """Tests for TokenAccounting model."""

    def test_default_values(self):
        ta = TokenAccounting()
        assert ta.input_tokens == 0
        assert ta.output_tokens == 0
        assert ta.total_tokens == 0
        assert ta.cost == 0.0
        assert ta.model == ""

    def test_merge(self):
        ta1 = TokenAccounting(input_tokens=100, output_tokens=50, total_tokens=150, cost=0.01, model="gpt-4")
        ta2 = TokenAccounting(input_tokens=200, output_tokens=100, total_tokens=300, cost=0.02, model="gpt-4")
        merged = ta1.merge(ta2)
        assert merged.input_tokens == 300
        assert merged.output_tokens == 150
        assert merged.total_tokens == 450
        assert merged.cost == 0.03
        assert merged.model == "gpt-4"

    def test_merge_preserves_model(self):
        ta1 = TokenAccounting(model="gpt-4")
        ta2 = TokenAccounting(model="")
        merged = ta1.merge(ta2)
        assert merged.model == "gpt-4"

    def test_from_dict_prompt_completion(self):
        data = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        ta = TokenAccounting.from_dict(data, model="claude-3")
        assert ta.input_tokens == 100
        assert ta.output_tokens == 50
        assert ta.total_tokens == 150
        assert ta.model == "claude-3"

    def test_from_dict_input_output(self):
        data = {"input_tokens": 200, "output_tokens": 100, "cost": 0.05}
        ta = TokenAccounting.from_dict(data, model="qwen")
        assert ta.input_tokens == 200
        assert ta.output_tokens == 100
        assert ta.cost == 0.05


class TestBudgetAlert:
    """Tests for BudgetAlert model."""

    def test_default_values(self):
        alert = BudgetAlert(message="Test alert")
        assert alert.level == "warning"
        assert alert.used == 0.0
        assert alert.budget == 0.0

    def test_critical_level(self):
        alert = BudgetAlert(level="critical", message="Budget exceeded", used=150, budget=100)
        assert alert.level == "critical"
        assert alert.used == 150


class TestTraceEvents:
    """Tests for trace event types."""

    def test_llm_call_event(self):
        event = LLMCallEvent(
            model="gpt-4",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            latency_ms=250.0,
        )
        assert event.event_type == "LLMCall"
        assert event.model == "gpt-4"
        assert event.total_tokens == 150
        assert event.success is True

    def test_tool_call_event(self):
        event = ToolCallEvent(tool_name="search", arguments={"query": "test"})
        assert event.event_type == "ToolCall"
        assert event.tool_name == "search"

    def test_tool_result_event(self):
        event = ToolResultEvent(tool_name="search", result_summary="Found 5 results")
        assert event.event_type == "ToolResult"
        assert event.success is True

    def test_step_complete_event(self):
        event = StepCompleteEvent(step_name="parse_input", step_index=0)
        assert event.event_type == "StepComplete"
        assert event.step_index == 0

    def test_turn_start_event(self):
        event = TurnStartEvent(turn_index=3)
        assert event.event_type == "TurnStart"
        assert event.turn_index == 3

    def test_error_event(self):
        event = ErrorEvent(error_type="TimeoutError", error_message="Request timed out", recoverable=True)
        assert event.event_type == "Error"
        assert event.recoverable is True


class TestEnvelopeTraceDTO:
    """Tests for EnvelopeTraceDTO frozen dataclass."""

    def test_creation(self):
        dto = EnvelopeTraceDTO(steps=5, tool_call_count=3, tokens=1000, time_ms=500.0, cost=0.05)
        assert dto.steps == 5
        assert dto.tool_call_count == 3
        assert dto.tokens == 1000
        assert dto.time_ms == 500.0
        assert dto.cost == 0.05

    def test_frozen(self):
        dto = EnvelopeTraceDTO(steps=5, tool_call_count=3, tokens=1000, time_ms=500.0, cost=0.05)
        with pytest.raises(AttributeError):
            dto.steps = 10  # type: ignore


class TestExecutionTrace:
    """Tests for ExecutionTrace model."""

    def test_default_values(self):
        trace = ExecutionTrace()
        assert trace.schema_version == "1.0"
        assert trace.run_id  # UUID generated
        assert trace.eval_id == 0
        assert trace.phase == "with_skill"
        assert trace.events == []
        assert trace.error is None

    def test_duration_ms(self):
        trace = ExecutionTrace(start_time=1000.0, end_time=1001.5)
        assert trace.duration_ms == 1500.0

    def test_duration_ms_no_end(self):
        trace = ExecutionTrace(start_time=1000.0)
        assert trace.duration_ms == 0.0

    def test_step_count(self):
        trace = ExecutionTrace()
        trace.events.append(StepCompleteEvent(step_name="step1"))
        trace.events.append(StepCompleteEvent(step_name="step2"))
        trace.events.append(LLMCallEvent(model="gpt-4", input_tokens=10, output_tokens=5, total_tokens=15))
        assert trace.step_count == 2

    def test_tool_call_count(self):
        trace = ExecutionTrace()
        trace.events.append(ToolCallEvent(tool_name="search"))
        trace.events.append(ToolCallEvent(tool_name="calculate"))
        trace.events.append(LLMCallEvent(model="gpt-4", input_tokens=10, output_tokens=5, total_tokens=15))
        assert trace.tool_call_count == 2

    def test_add_event(self):
        trace = ExecutionTrace()
        event = LLMCallEvent(model="gpt-4", input_tokens=100, output_tokens=50, total_tokens=150)
        trace.add_event(event)
        assert len(trace.events) == 1
        assert trace.events[0].event_type == "LLMCall"

    def test_record_llm_call(self):
        trace = ExecutionTrace()
        event = trace.record_llm_call(
            model="gpt-4",
            input_tokens=100,
            output_tokens=50,
            latency_ms=250.0,
        )
        assert event.event_type == "LLMCall"
        assert trace.token_usage.input_tokens == 100
        assert trace.token_usage.output_tokens == 50
        assert trace.token_usage.total_tokens == 150
        assert trace.token_usage.model == "gpt-4"

    def test_record_multiple_llm_calls(self):
        trace = ExecutionTrace()
        trace.record_llm_call(model="gpt-4", input_tokens=100, output_tokens=50, latency_ms=100)
        trace.record_llm_call(model="gpt-4", input_tokens=200, output_tokens=100, latency_ms=200)
        assert trace.token_usage.input_tokens == 300
        assert trace.token_usage.output_tokens == 150
        assert trace.token_usage.total_tokens == 450

    def test_to_envelope_dto(self):
        trace = ExecutionTrace(start_time=1000.0, end_time=1001.0)
        trace.events.append(StepCompleteEvent(step_name="step1"))
        trace.events.append(StepCompleteEvent(step_name="step2"))
        trace.events.append(ToolCallEvent(tool_name="search"))
        trace.token_usage = TokenAccounting(total_tokens=500, cost=0.025)
        dto = trace.to_envelope_dto()
        assert dto.steps == 2
        assert dto.tool_call_count == 1
        assert dto.tokens == 500
        assert dto.time_ms == 1000.0
        assert dto.cost == 0.025

    def test_to_envelope_trace_alias(self):
        trace = ExecutionTrace()
        dto1 = trace.to_envelope_dto()
        dto2 = trace.to_envelope_trace()
        assert dto1.steps == dto2.steps

    def test_model_dump(self):
        trace = ExecutionTrace(eval_id=1, phase="without_skill")
        trace.record_llm_call(model="gpt-4", input_tokens=100, output_tokens=50, latency_ms=100)
        data = trace.model_dump(mode="json")
        assert data["eval_id"] == 1
        assert data["phase"] == "without_skill"
        assert "events" in data
        assert "token_usage" in data

    def test_model_dump_json(self):
        trace = ExecutionTrace(eval_id=2)
        json_str = trace.model_dump_json()
        assert '"eval_id":2' in json_str
