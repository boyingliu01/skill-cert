"""Tests for engine/deadline.py — Deadline dataclass and PhaseTimer."""

import math
import time

import pytest

from engine.deadline import Deadline, PhaseTimer


def test_deadline_creation_defaults():
    """Deadline created with defaults has infinite max_total_time."""
    dl = Deadline()
    assert dl.max_total_time == float("inf")
    assert dl.elapsed >= 0.0
    assert math.isinf(dl.remaining)
    assert not dl.expired


def test_deadline_creation_with_time():
    """Deadline with a finite max_total_time tracks elapsed correctly."""
    dl = Deadline(max_total_time=60.0)
    assert dl.max_total_time == 60.0
    assert dl.elapsed >= 0.0
    assert 0.0 < dl.remaining <= 60.0
    assert not dl.expired


def test_deadline_elapsed_increases():
    """elapsed property increases over time."""
    dl = Deadline(max_total_time=60.0)
    e1 = dl.elapsed
    time.sleep(0.01)
    e2 = dl.elapsed
    assert e2 > e1


def test_deadline_remaining_decreases():
    """remaining property decreases over time."""
    dl = Deadline(max_total_time=60.0)
    r1 = dl.remaining
    time.sleep(0.01)
    r2 = dl.remaining
    assert r2 < r1


def test_deadline_expired():
    """expired is True when remaining <= 0."""
    dl = Deadline(max_total_time=0.0)
    assert dl.remaining <= 0.0
    assert dl.expired


def test_deadline_not_expired():
    """expired is False when remaining > 0."""
    dl = Deadline(max_total_time=60.0)
    assert not dl.expired


def test_must_stop_within_grace():
    """must_stop returns True when remaining <= grace_period."""
    dl = Deadline(max_total_time=2.0)
    # remaining ~2s, grace_period=5s => remaining <= grace_period
    assert dl.must_stop(grace_period=5.0)


def test_must_stop_outside_grace():
    """must_stop returns False when remaining > grace_period."""
    dl = Deadline(max_total_time=60.0)
    assert not dl.must_stop(grace_period=5.0)


def test_must_stop_custom_grace():
    """must_stop respects custom grace_period."""
    dl = Deadline(max_total_time=10.0)
    # remaining ~10s, grace_period=10s => remaining <= grace_period
    assert dl.must_stop(grace_period=10.0)


def test_adapter_timeout_less_than_default():
    """adapter_timeout returns remaining (capped at min 5) when less than default."""
    dl = Deadline(max_total_time=10.0)
    timeout = dl.adapter_timeout(default=120)
    # remaining ~10s, ceil(10)=10, max(5,10)=10, min(120,10)=10
    assert 5 <= timeout <= 120


def test_adapter_timeout_more_than_default():
    """adapter_timeout returns default when remaining exceeds default."""
    dl = Deadline(max_total_time=3600.0)
    timeout = dl.adapter_timeout(default=120)
    assert timeout == 120


def test_adapter_timeout_minimum_floor():
    """adapter_timeout returns at least 5s even when remaining is tiny."""
    dl = Deadline(max_total_time=2.0)
    timeout = dl.adapter_timeout(default=120)
    # min(120, max(5, ceil(~2))) = min(120, 5) = 5
    assert timeout == 5


def test_adapter_timeout_infinite_remaining():
    """adapter_timeout returns default when remaining is infinite."""
    dl = Deadline()
    timeout = dl.adapter_timeout(default=120)
    assert timeout == 120


def test_adapter_timeout_default_param():
    """adapter_timeout uses default=120 when not specified."""
    dl = Deadline(max_total_time=3600.0)
    timeout = dl.adapter_timeout()
    assert timeout == 120


def test_adapter_timeout_custom_default():
    """adapter_timeout accepts custom default."""
    dl = Deadline(max_total_time=3600.0)
    timeout = dl.adapter_timeout(default=60)
    assert timeout == 60


def test_deadline_repr():
    """__repr__ returns a meaningful debug string."""
    dl = Deadline(max_total_time=60.0)
    r = repr(dl)
    assert "Deadline(" in r
    assert "max_total_time=60" in r
    assert "elapsed=" in r
    assert "remaining=" in r
    assert "expired=" in r


# ── Mock time.monotonic tests (AC-019-02, AC-019-03) ──────────────────────
#
# NOTE: patch targets `engine.deadline.time.monotonic` (the module-level
# reference) rather than `time.monotonic` (the global) because the
# dataclass ``field(default_factory=time.monotonic)`` captures the function
# reference at class-definition time — patching the global later has no
# effect on ``start_time``.  By patching the module-level name we affect
# the ``elapsed`` / ``remaining`` / ``expired`` property reads.


def test_deadline_expired_mock_monotonic():
    """AC-019-02: Use mock time.monotonic to verify deadline.expired transitions."""
    from unittest.mock import patch

    dl = Deadline(max_total_time=10.0)
    real_start = dl.start_time

    with patch("engine.deadline.time.monotonic") as mock_time:
        mock_time.return_value = real_start + 5.0
        assert not dl.expired
        assert abs(dl.remaining - 5.0) < 0.01, f"Expected ~5.0 remaining, got {dl.remaining}"

        mock_time.return_value = real_start + 10.0
        assert dl.expired
        assert dl.remaining == 0.0

        mock_time.return_value = real_start + 15.0
        assert dl.expired
        assert dl.remaining == 0.0


def test_deadline_elapsed_mock_monotonic():
    """AC-019-02: Verify elapsed property reflects simulated time passage."""
    from unittest.mock import patch

    dl = Deadline(max_total_time=60.0)
    real_start = dl.start_time

    with patch("engine.deadline.time.monotonic") as mock_time:
        mock_time.return_value = real_start + 3.5
        assert abs(dl.elapsed - 3.5) < 0.01, f"Expected ~3.5s elapsed, got {dl.elapsed}"

        mock_time.return_value = real_start + 10.0
        assert abs(dl.elapsed - 10.0) < 0.01, f"Expected 10.0s elapsed, got {dl.elapsed}"


@pytest.mark.parametrize(
    "remaining_input,expected_timeout",
    [
        (3.0, 5),  # AC-019-03: ceil(3)=3, max(5,3)=5, min(120,5)=5
        (0.5, 5),  # ceil(0.5)=1, max(5,1)=5, min(120,5)=5
        (5.0, 5),  # ceil(5)=5, max(5,5)=5, min(120,5)=5
        (10.0, 10),  # ceil(10)=10, max(5,10)=10, min(120,10)=10
    ],
)
def test_adapter_timeout_floor_parametrized(remaining_input, expected_timeout):
    """AC-019-03: adapter_timeout respects 5s floor for various remaining values."""
    from unittest.mock import patch

    dl = Deadline(max_total_time=remaining_input + 5.0)
    real_start = dl.start_time

    with patch("engine.deadline.time.monotonic") as mock_time:
        # Simulate elapsed = max_total_time - remaining_input
        mock_time.return_value = real_start + (dl.max_total_time - remaining_input)

        result = dl.adapter_timeout(default=120)
        assert result == expected_timeout, (
            f"adapter_timeout(remaining_input={remaining_input}) = {result}, "
            f"expected {expected_timeout}"
        )


def test_adapter_timeout_floor_remaining_1():
    """AC-019-03: adapter_timeout returns 5 when remaining=1 (below 5s floor)."""
    from unittest.mock import patch

    dl = Deadline(max_total_time=10.0)
    real_start = dl.start_time

    with patch("engine.deadline.time.monotonic") as mock_time:
        mock_time.return_value = real_start + 9.0
        result = dl.adapter_timeout(default=120)
        assert result == 5, f"Expected 5 (floor), got {result}"


# ── PhaseTimer tests ────────────────────────────────────────────────────────


def test_phasetimer_creation():
    """PhaseTimer created with just a name."""
    pt = PhaseTimer(phase_name="testgen")
    assert pt.phase_name == "testgen"
    assert pt.start_time > 0
    assert pt.item_count == 0
    assert pt.items_completed == 0
    assert pt.deadline is None


def test_phasetimer_creation_with_count():
    """PhaseTimer with item_count and deadline."""
    dl = Deadline(max_total_time=60.0)
    pt = PhaseTimer(phase_name="evals", item_count=5, deadline=dl)
    assert pt.phase_name == "evals"
    assert pt.item_count == 5
    assert pt.deadline is dl


def test_phasetimer_log_progress_returns_string():
    """log_progress returns a non-empty string."""
    pt = PhaseTimer(phase_name="test")
    msg = pt.log_progress("doing work")
    assert isinstance(msg, str)
    assert len(msg) > 0


def test_phasetimer_log_progress_format():
    """log_progress output contains phase name and elapsed."""
    pt = PhaseTimer(phase_name="mytest")
    msg = pt.log_progress()
    assert "[mytest]" in msg
    assert "elapsed" in msg


def test_phasetimer_log_progress_with_label():
    """log_progress includes the label when provided."""
    pt = PhaseTimer(phase_name="testgen")
    msg = pt.log_progress("round 3")
    assert "[testgen]" in msg
    assert "round 3" in msg
    assert "elapsed" in msg


def test_phasetimer_log_progress_with_count():
    """log_progress includes item count when item_count > 0."""
    pt = PhaseTimer(phase_name="evals", item_count=10)
    msg = pt.log_progress()
    assert "[0/10]" in msg


def test_phasetimer_log_progress_with_deadline():
    """log_progress includes deadline remaining when deadline is set."""
    dl = Deadline(max_total_time=60.0)
    pt = PhaseTimer(phase_name="evals", item_count=5, deadline=dl)
    msg = pt.log_progress("model-a")
    assert "deadline:" in msg
    assert "remaining" in msg


def test_phasetimer_log_progress_infinite_deadline():
    """log_progress shows 'no limit' for infinite deadline."""
    dl = Deadline()
    pt = PhaseTimer(phase_name="testgen", deadline=dl)
    msg = pt.log_progress()
    assert "no limit" in msg


def test_phasetimer_log_progress_shows_item_count():
    """log_progress shows items_completed/item_count format."""
    pt = PhaseTimer(phase_name="stability", item_count=5)
    pt.items_completed = 2
    msg = pt.log_progress("run 3/5")
    assert "[2/5]" in msg
