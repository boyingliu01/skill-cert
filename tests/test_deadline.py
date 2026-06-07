"""Tests for engine/deadline.py — Deadline dataclass."""

import math
import time

from engine.deadline import Deadline


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
