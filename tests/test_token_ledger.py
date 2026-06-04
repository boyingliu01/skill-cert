"""Tests for engine/token_ledger.py — TokenLedger aggregator."""

import threading

import pytest

from engine.token_ledger import TokenLedger
from engine.trace_models import ExecutionTrace, TokenAccounting


def _make_trace(eval_id: int, phase: str, model: str, tokens: int, cost: float = 0.0) -> ExecutionTrace:
    """Helper to create a trace with token usage."""
    trace = ExecutionTrace(
        eval_id=eval_id,
        phase=phase,
        token_usage=TokenAccounting(
            input_tokens=tokens // 2,
            output_tokens=tokens // 2,
            total_tokens=tokens,
            cost=cost,
            model=model,
        ),
    )
    return trace


class TestTokenLedger:
    """Tests for TokenLedger aggregator."""

    def test_empty_ledger(self):
        ledger = TokenLedger()
        assert ledger.total_tokens == 0
        assert ledger.total_cost == 0.0
        assert ledger.trace_count == 0

    def test_aggregate_single_trace(self):
        ledger = TokenLedger()
        trace = _make_trace(1, "with_skill", "gpt-4", 100, 0.01)
        ledger.aggregate([trace])
        assert ledger.total_tokens == 100
        assert ledger.total_cost == 0.01
        assert ledger.trace_count == 1

    def test_aggregate_multiple_traces(self):
        ledger = TokenLedger()
        traces = [
            _make_trace(1, "with_skill", "gpt-4", 100, 0.01),
            _make_trace(2, "without_skill", "gpt-4", 80, 0.008),
            _make_trace(1, "with_skill", "claude-3", 120, 0.015),
        ]
        ledger.aggregate(traces)
        assert ledger.total_tokens == 300
        assert ledger.total_cost == pytest.approx(0.033)
        assert ledger.trace_count == 3

    def test_phase_totals(self):
        ledger = TokenLedger()
        traces = [
            _make_trace(1, "with_skill", "gpt-4", 100),
            _make_trace(2, "with_skill", "gpt-4", 150),
            _make_trace(1, "without_skill", "gpt-4", 80),
        ]
        ledger.aggregate(traces)
        phase_totals = ledger.phase_totals
        assert "with_skill" in phase_totals
        assert phase_totals["with_skill"].total_tokens == 250
        assert phase_totals["without_skill"].total_tokens == 80

    def test_model_totals(self):
        ledger = TokenLedger()
        traces = [
            _make_trace(1, "with_skill", "gpt-4", 100),
            _make_trace(2, "with_skill", "claude-3", 150),
            _make_trace(1, "without_skill", "gpt-4", 80),
        ]
        ledger.aggregate(traces)
        model_totals = ledger.model_totals
        assert "gpt-4" in model_totals
        assert model_totals["gpt-4"].total_tokens == 180
        assert model_totals["claude-3"].total_tokens == 150

    def test_eval_totals(self):
        ledger = TokenLedger()
        traces = [
            _make_trace(1, "with_skill", "gpt-4", 100),
            _make_trace(1, "without_skill", "gpt-4", 80),
            _make_trace(2, "with_skill", "gpt-4", 120),
        ]
        ledger.aggregate(traces)
        eval_totals = ledger.eval_totals
        assert "1" in eval_totals
        assert eval_totals["1"].total_tokens == 180
        assert "2" in eval_totals
        assert eval_totals["2"].total_tokens == 120

    def test_get_summary(self):
        ledger = TokenLedger()
        traces = [
            _make_trace(1, "with_skill", "gpt-4", 100, 0.01),
            _make_trace(2, "without_skill", "gpt-4", 80, 0.008),
        ]
        ledger.aggregate(traces)
        summary = ledger.get_summary()
        assert summary["total_tokens"] == 180
        assert summary["total_cost"] == pytest.approx(0.018)
        assert summary["trace_count"] == 2
        assert "by_phase" in summary
        assert "by_model" in summary
        assert "by_eval" in summary

    def test_check_budget_no_limit(self):
        ledger = TokenLedger()
        traces = [_make_trace(1, "with_skill", "gpt-4", 100)]
        ledger.aggregate(traces)
        alerts = ledger.check_budget()
        assert len(alerts) == 0

    def test_check_budget_warning(self):
        ledger = TokenLedger()
        traces = [_make_trace(1, "with_skill", "gpt-4", 85000)]
        ledger.aggregate(traces)
        alerts = ledger.check_budget(token_budget=100000)
        assert len(alerts) == 1
        assert alerts[0].level == "warning"

    def test_check_budget_critical(self):
        ledger = TokenLedger()
        traces = [_make_trace(1, "with_skill", "gpt-4", 120000)]
        ledger.aggregate(traces)
        alerts = ledger.check_budget(token_budget=100000)
        assert len(alerts) == 1
        assert alerts[0].level == "critical"

    def test_check_cost_budget_warning(self):
        ledger = TokenLedger()
        traces = [_make_trace(1, "with_skill", "gpt-4", 100, cost=0.85)]
        ledger.aggregate(traces)
        alerts = ledger.check_budget(cost_budget=1.0)
        assert len(alerts) == 1
        assert alerts[0].level == "warning"

    def test_check_cost_budget_critical(self):
        ledger = TokenLedger()
        traces = [_make_trace(1, "with_skill", "gpt-4", 100, cost=1.5)]
        ledger.aggregate(traces)
        alerts = ledger.check_budget(cost_budget=1.0)
        assert len(alerts) == 1
        assert alerts[0].level == "critical"

    def test_record_trace_thread_local(self):
        ledger = TokenLedger()
        trace = _make_trace(1, "with_skill", "gpt-4", 100)
        ledger.record_trace(trace)
        # record_trace is thread-safe, immediately available
        assert ledger.trace_count == 1
        assert ledger.total_tokens == 100
        # flush() recomputes aggregations
        ledger.flush()
        assert ledger.trace_count == 1

    def test_clear(self):
        ledger = TokenLedger()
        traces = [_make_trace(1, "with_skill", "gpt-4", 100)]
        ledger.aggregate(traces)
        assert ledger.trace_count == 1
        ledger.clear()
        assert ledger.trace_count == 0
        assert ledger.total_tokens == 0

    def test_concurrent_record_trace(self):
        """Test thread-safe record_trace with multiple threads."""
        ledger = TokenLedger()
        num_threads = 5
        traces_per_thread = 10

        def record_traces(thread_id: int):
            for i in range(traces_per_thread):
                trace = _make_trace(thread_id * 100 + i, "with_skill", "gpt-4", 10)
                ledger.record_trace(trace)

        threads = [threading.Thread(target=record_traces, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        ledger.flush()
        assert ledger.trace_count == num_threads * traces_per_thread
        assert ledger.total_tokens == num_threads * traces_per_thread * 10
