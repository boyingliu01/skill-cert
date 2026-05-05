"""Tests for L8 latency metrics."""

import pytest
from engine.metrics import MetricsCalculator


def make_result(skill_used=True, exec_time=5.0):
    return {
        "category": "normal",
        "skill_used": skill_used,
        "final_passed": True,
        "pass_rate": 0.8,
        "assertion_results": [],
        "execution_time": exec_time,
    }


def test_no_latency_data_returns_none():
    calc = MetricsCalculator()
    results = [{"category": "normal", "assertion_results": []}]
    l8 = calc._calculate_l8_latency_metrics(results)
    assert l8 is None


def test_latency_with_both_modes():
    calc = MetricsCalculator()
    results = [
        make_result(skill_used=True, exec_time=3.0),
        make_result(skill_used=True, exec_time=5.0),
        make_result(skill_used=True, exec_time=7.0),
        make_result(skill_used=False, exec_time=2.0),
        make_result(skill_used=False, exec_time=4.0),
    ]
    l8 = calc._calculate_l8_latency_metrics(results)
    assert l8 is not None
    assert "with_skill" in l8
    assert "without_skill" in l8
    assert "overhead_pct" in l8


def test_p50_calculation_odd_count():
    calc = MetricsCalculator()
    times = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]
    stats = calc._compute_latency_stats(times)
    assert stats["p50"] == 5.0


def test_p50_calculation_even_count():
    calc = MetricsCalculator()
    times = [1.0, 2.0, 3.0, 4.0]
    stats = calc._compute_latency_stats(times)
    assert stats["p50"] == 3.0


def test_p95_calculation():
    calc = MetricsCalculator()
    times = list(range(1, 21))
    stats = calc._compute_latency_stats(times)
    assert stats["p95"] == 20


def test_p99_calculation():
    calc = MetricsCalculator()
    times = list(range(1, 101))
    stats = calc._compute_latency_stats(times)
    assert stats["p99"] == 100


def test_slow_request_detection():
    calc = MetricsCalculator()
    results = [
        make_result(skill_used=True, exec_time=10.0),
        make_result(skill_used=True, exec_time=35.0),
        make_result(skill_used=True, exec_time=40.0),
        make_result(skill_used=False, exec_time=5.0),
    ]
    l8 = calc._calculate_l8_latency_metrics(results)
    assert l8["slow_with_skill"] == 2
    assert l8["slow_without_skill"] == 0


def test_overhead_calculation():
    calc = MetricsCalculator()
    results = [
        make_result(skill_used=True, exec_time=6.0),
        make_result(skill_used=True, exec_time=6.0),
        make_result(skill_used=False, exec_time=4.0),
        make_result(skill_used=False, exec_time=4.0),
    ]
    l8 = calc._calculate_l8_latency_metrics(results)
    with_avg = 6.0
    without_avg = 4.0
    expected_overhead = ((with_avg - without_avg) / without_avg) * 100
    assert l8["overhead_pct"] == pytest.approx(expected_overhead, rel=0.01)
