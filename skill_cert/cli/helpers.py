"""Shared utilities for skill-cert CLI modes."""

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


def _print_metric(label: str, value: float, threshold: float | None = None) -> None:
    pct = f"{value * 100:.1f}%"
    if threshold is not None:
        status = "✓" if value >= threshold else "✗"
        print(f"  {label}: {pct} (threshold: {threshold * 100:.0f}%) {status}")
    else:
        print(f"  {label}: {pct}")
