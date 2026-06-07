"""Shared utilities for skill-cert CLI modes."""

import math

from adapters.factory import create_adapter as _create_adapter_factory
from engine.config import ModelConfig
from engine.constants import TimingLimits

EXIT_PASS = 0
EXIT_ERROR = 1
EXIT_FAIL_WITH_CAVEATS = 2


def _create_adapter(model_config: ModelConfig, rpm_limit: int = TimingLimits.RATE_LIMIT_RPM):
    """Create an adapter using factory auto-detection (backward-compatible wrapper)."""
    return _create_adapter_factory(model_config, rpm_limit)


def _print_phase(phase: int, name: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  Phase {phase}: {name}")
    print(f"{'=' * 60}")


def _print_phase_with_deadline(phase: int, name: str, deadline=None) -> None:
    """Print a phase header with optional deadline countdown.

    When deadline is provided, prints::

        Phase N: Name — Elapsed: Xs / Ys (Zs remaining)

    When deadline is None, prints the standard phase header.
    """
    if deadline is None:
        _print_phase(phase, name)
        return
    elapsed = deadline.elapsed
    total = deadline.max_total_time
    remaining = deadline.remaining
    if math.isfinite(total):
        remaining_str = f"{remaining:.0f}s remaining"
        elapsed_str = f"{elapsed:.0f}s"
        total_str = f"{total:.0f}s"
        print(f"\n{'=' * 60}")
        print(f"  Phase {phase}: {name} — Elapsed: {elapsed_str} / {total_str} ({remaining_str})")
        print(f"{'=' * 60}")
    else:
        _print_phase(phase, name)


def _print_metric(label: str, value: float, threshold: float | None = None) -> None:
    pct = f"{value * 100:.1f}%"
    if threshold is not None:
        status = "✓" if value >= threshold else "✗"
        print(f"  {label}: {pct} (threshold: {threshold * 100:.0f}%) {status}")
    else:
        print(f"  {label}: {pct}")
