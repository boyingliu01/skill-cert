"""Token ledger — read-only aggregator for per-eval token accounting.

Design decisions (Delphi Review consensus):
- ExecutionTrace is the SINGLE source of truth for token data
- TokenLedger is a READ-ONLY aggregator that consumes ExecutionTrace list
- Thread-safe via per-thread local buffer + phase-end merge
- Runner uses ThreadPoolExecutor, so we use threading.local()
"""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any

from engine.trace_models import BudgetAlert, ExecutionTrace, TokenAccounting


class TokenLedger:
    """Per-evaluation token accounting aggregator.

    Usage:
        ledger = TokenLedger()
        # ... runner executes evals, producing ExecutionTrace instances ...
        ledger.aggregate(all_traces)
        summary = ledger.get_summary()
    """

    def __init__(self) -> None:
        self._traces: list[ExecutionTrace] = []
        self._lock = threading.Lock()
        self._local = threading.local()
        self._phase_totals: dict[str, TokenAccounting] = {}
        self._model_totals: dict[str, TokenAccounting] = {}
        self._eval_totals: dict[str, TokenAccounting] = {}
        self._aggregated = False

    def aggregate(self, traces: list[ExecutionTrace]) -> None:
        """Aggregate token data from a list of ExecutionTrace instances.

        This is the PRIMARY API. TokenLedger consumes ExecutionTrace objects
        and computes per-phase, per-model, and per-eval totals.

        Thread-safe: can be called from any thread after traces are collected.
        """
        with self._lock:
            self._traces.extend(traces)
            self._aggregated = False

        self._recompute()

    def record_trace(self, trace: ExecutionTrace) -> None:
        """Record a single trace (thread-safe).

        This is the primary API during concurrent execution.
        Thread-safe via internal lock.
        """
        with self._lock:
            self._traces.append(trace)
            self._aggregated = False

    def flush(self) -> None:
        """Recompute aggregations after all traces are recorded.

        Call this after all traces have been recorded via record_trace().
        """
        self._recompute()

    def _recompute(self) -> None:
        """Recompute all aggregations from self._traces."""
        if self._aggregated:
            return

        phase_totals: dict[str, TokenAccounting] = defaultdict(TokenAccounting)
        model_totals: dict[str, TokenAccounting] = defaultdict(TokenAccounting)
        eval_totals: dict[str, TokenAccounting] = {}

        for trace in self._traces:
            tu = trace.token_usage
            eval_key = str(trace.eval_id)

            # Phase totals
            phase_totals[trace.phase] = phase_totals[trace.phase].merge(tu)

            # Model totals
            if tu.model:
                model_totals[tu.model] = model_totals[tu.model].merge(tu)

            # Eval totals
            if eval_key in eval_totals:
                eval_totals[eval_key] = eval_totals[eval_key].merge(tu)
            else:
                eval_totals[eval_key] = tu.model_copy()

        with self._lock:
            self._phase_totals = dict(phase_totals)
            self._model_totals = dict(model_totals)
            self._eval_totals = eval_totals
            self._aggregated = True

    @property
    def phase_totals(self) -> dict[str, TokenAccounting]:
        """Token totals grouped by phase (with_skill, without_skill, etc.)."""
        return dict(self._phase_totals)

    @property
    def model_totals(self) -> dict[str, TokenAccounting]:
        """Token totals grouped by model name."""
        return dict(self._model_totals)

    @property
    def eval_totals(self) -> dict[str, TokenAccounting]:
        """Token totals grouped by eval_id."""
        return dict(self._eval_totals)

    @property
    def total_tokens(self) -> int:
        """Total tokens across all traces."""
        return sum(t.token_usage.total_tokens for t in self._traces)

    @property
    def total_cost(self) -> float:
        """Total cost across all traces."""
        return sum(t.token_usage.cost for t in self._traces)

    @property
    def trace_count(self) -> int:
        """Number of aggregated traces."""
        return len(self._traces)

    def get_summary(self) -> dict[str, Any]:
        """Generate complete summary dict for reporter consumption.

        Returns a JSON-serializable dict with:
        - total_tokens, total_cost, trace_count
        - by_phase, by_model, by_eval (TokenAccounting dicts)
        """
        return {
            "total_tokens": self.total_tokens,
            "total_cost": round(self.total_cost, 4),
            "trace_count": self.trace_count,
            "by_phase": {k: v.model_dump() for k, v in self._phase_totals.items()},
            "by_model": {k: v.model_dump() for k, v in self._model_totals.items()},
            "by_eval": [
                {"eval_id": k, **v.model_dump()}
                for k, v in self._eval_totals.items()
            ],
        }

    def check_budget(self, token_budget: int = 0, cost_budget: float = 0.0) -> list[BudgetAlert]:
        """Check if any budget thresholds are exceeded.

        Args:
            token_budget: Maximum allowed tokens (0 = no limit)
            cost_budget: Maximum allowed cost (0 = no limit)

        Returns:
            List of BudgetAlert instances for any exceeded thresholds.
        """
        alerts: list[BudgetAlert] = []

        if token_budget > 0:
            used = self.total_tokens
            utilization = used / token_budget
            if utilization >= 1.0:
                alerts.append(BudgetAlert(
                    level="critical",
                    message=f"Token budget exceeded: {used:,} / {token_budget:,} ({utilization:.0%})",
                    used=used,
                    budget=token_budget,
                ))
            elif utilization >= 0.8:
                alerts.append(BudgetAlert(
                    level="warning",
                    message=f"Token budget at {utilization:.0%}: {used:,} / {token_budget:,}",
                    used=used,
                    budget=token_budget,
                ))

        if cost_budget > 0:
            used = self.total_cost
            utilization = used / cost_budget
            if utilization >= 1.0:
                alerts.append(BudgetAlert(
                    level="critical",
                    message=f"Cost budget exceeded: ${used:.4f} / ${cost_budget:.4f} ({utilization:.0%})",
                    used=used,
                    budget=cost_budget,
                ))
            elif utilization >= 0.8:
                alerts.append(BudgetAlert(
                    level="warning",
                    message=f"Cost budget at {utilization:.0%}: ${used:.4f} / ${cost_budget:.4f}",
                    used=used,
                    budget=cost_budget,
                ))

        return alerts

    def clear(self) -> None:
        """Reset the ledger (useful between phases)."""
        with self._lock:
            self._traces.clear()
            self._phase_totals.clear()
            self._model_totals.clear()
            self._eval_totals.clear()
            self._aggregated = False
