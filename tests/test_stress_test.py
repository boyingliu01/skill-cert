"""Tests for engine/stress_test.py — scalability testing."""

import asyncio

import pytest

from engine.stress_test import (
    RateLimiter,
    StressTestReport,
    StressTestResult,
    StressTester,
    format_scalability_report,
)


class MockAdapter:
    """Mock model adapter with configurable latency."""

    def __init__(self, latency=0.01, fail_pattern=None, fail_rate=0):
        self.latency = latency
        self.fail_pattern = fail_pattern
        self.fail_rate = fail_rate
        self.call_count = 0

    async def generate(self, eval_case):
        self.call_count += 1
        await asyncio.sleep(self.latency)
        model = eval_case.get("model", "")
        if self.fail_pattern == "model" and model == "bad-model":
            raise RuntimeError("model error")
        if self.fail_pattern == "random" and (self.call_count % 5 == 0):
            raise RuntimeError("random failure")
        return f"response for {eval_case.get('id', '')}"


class TestStressTestResult:
    def test_defaults(self):
        r = StressTestResult(eval_id="t1", model="m1")
        assert r.status == "success"
        assert r.latency == 0.0
        assert r.error is None

    def test_with_values(self):
        r = StressTestResult(eval_id="t2", model="m2", status="timeout", latency=5.0, error="too slow")
        assert r.status == "timeout"
        assert r.latency == 5.0
        assert r.error == "too slow"


class TestStressTestReport:
    def test_defaults(self):
        r = StressTestReport()
        assert r.total_evals == 0
        assert r.completion_rate == 0.0
        assert r.model_exec_counts == {}
        assert r.fairness_ratio == 1.0
        assert r.scalability_score == 100.0
        assert r.verdict == "PASS"


class TestRateLimiter:
    def test_init_default(self):
        limiter = RateLimiter()
        assert limiter.rpm == 60

    def test_init_custom_rpm(self):
        limiter = RateLimiter(rpm=120)
        assert limiter.rpm == 120

    def test_init_with_models(self):
        limiter = RateLimiter(rpm=60, models=["m1", "m2", "m3"])
        assert limiter._per_model_rpm == {"m1": 20, "m2": 20, "m3": 20}

    @pytest.mark.asyncio
    async def test_acquire_basic(self):
        limiter = RateLimiter(rpm=1000)
        await limiter.acquire()
        assert limiter.rpm == 1000

    @pytest.mark.asyncio
    async def test_acquire_tracks_model(self):
        limiter = RateLimiter(rpm=60, models=["m1", "m2"])
        await limiter.acquire("m1")
        assert limiter._model_counts["m1"] == 1

    @pytest.mark.asyncio
    async def test_get_model_counts(self):
        limiter = RateLimiter(rpm=60, models=["m1"])
        await limiter.acquire("m1")
        await limiter.acquire("m1")
        counts = limiter.get_model_counts()
        assert counts == {"m1": 2}


class TestStressTester:
    def test_default_concurrency(self):
        st = StressTester()
        assert st.concurrency == 5

    def test_custom_settings(self):
        st = StressTester(concurrency=10, rate_limit_rpm=100, timeout_per_eval=30)
        assert st.concurrency == 10

    @pytest.mark.asyncio
    async def test_run_basic_success(self):
        st = StressTester(concurrency=5)
        cases = [{"id": f"eval-{i}", "model": "model-a"} for i in range(10)]
        adapter = MockAdapter(latency=0.001)
        report = await st.run_stress_test(cases, adapter)
        assert report.total_evals == 10
        assert report.completed == 10
        assert report.completion_rate == 1.0

    @pytest.mark.asyncio
    async def test_run_with_50_concurrent(self):
        st = StressTester(concurrency=50)
        cases = [{"id": f"eval-{i}", "model": "model-a"} for i in range(50)]
        adapter = MockAdapter(latency=0.001)
        report = await st.run_stress_test(cases, adapter)
        assert report.total_evals == 50
        assert report.completed == 50

    @pytest.mark.asyncio
    async def test_run_with_timeouts(self):
        class SlowAdapter:
            async def generate(self, case):
                await asyncio.sleep(60)
                return "never"

        st = StressTester(concurrency=5, timeout_per_eval=0.01)
        cases = [{"id": f"slow-{i}", "model": "m1"} for i in range(5)]
        report = await st.run_stress_test(cases, SlowAdapter())
        assert report.timed_out == 5
        assert report.completed == 0

    @pytest.mark.asyncio
    async def test_run_with_errors(self):
        st = StressTester(concurrency=5)
        cases = [{"id": f"err-{i}", "model": "m1"} for i in range(5)]
        adapter = MockAdapter(fail_pattern="random")
        report = await st.run_stress_test(cases, adapter)
        assert report.errored > 0
        assert report.completed + report.errored == 5

    @pytest.mark.asyncio
    async def test_run_model_specific_failure(self):
        st = StressTester(concurrency=5)
        cases = [{"id": f"m-{i}", "model": "bad-model"} for i in range(5)]
        adapter = MockAdapter(fail_pattern="model")
        report = await st.run_stress_test(cases, adapter)
        assert report.errored == 5

    @pytest.mark.asyncio
    async def test_run_fairness_two_models(self):
        st = StressTester(concurrency=10, models=["m1", "m2"])
        cases = [
            {"id": f"a-{i}", "model": "m1"}
            if i % 2 == 0
            else {"id": f"b-{i}", "model": "m2"}
            for i in range(20)
        ]
        adapter = MockAdapter(latency=0.001)
        report = await st.run_stress_test(cases, adapter)
        m1_count = report.model_exec_counts.get("m1", 0)
        m2_count = report.model_exec_counts.get("m2", 0)
        if m1_count > 0 and m2_count > 0:
            assert report.fairness_ratio > 0.5

    @pytest.mark.asyncio
    async def test_run_latency_tracking(self):
        st = StressTester(concurrency=5)
        cases = [{"id": f"lat-{i}", "model": "m1"} for i in range(10)]
        adapter = MockAdapter(latency=0.01)
        report = await st.run_stress_test(cases, adapter)
        assert report.avg_latency > 0
        assert report.min_latency > 0
        assert report.max_latency > 0
        assert report.max_latency >= report.min_latency

    @pytest.mark.asyncio
    async def test_run_memory_tracking(self):
        st = StressTester(concurrency=5)
        cases = [{"id": f"mem-{i}", "model": "m1"} for i in range(5)]
        adapter = MockAdapter(latency=0.001)
        report = await st.run_stress_test(cases, adapter)
        assert report.memory_mb_peak >= 0

    @pytest.mark.asyncio
    async def test_run_scalability_score(self):
        st = StressTester(concurrency=5)
        cases = [{"id": f"score-{i}", "model": "m1"} for i in range(10)]
        adapter = MockAdapter(latency=0.001)
        report = await st.run_stress_test(cases, adapter)
        assert 0 <= report.scalability_score <= 100

    @pytest.mark.asyncio
    async def test_run_verdict_pass(self):
        st = StressTester(concurrency=5)
        cases = [{"id": f"pass-{i}", "model": "m1"} for i in range(10)]
        adapter = MockAdapter(latency=0.001)
        report = await st.run_stress_test(cases, adapter)
        assert report.verdict == "PASS"

    @pytest.mark.asyncio
    async def test_run_percentile_latencies(self):
        st = StressTester(concurrency=5)
        cases = [{"id": f"p-{i}", "model": "m1"} for i in range(100)]
        adapter = MockAdapter(latency=0.005)
        report = await st.run_stress_test(cases, adapter)
        assert report.p95_latency >= 0
        assert report.p99_latency >= 0
        assert report.median_latency >= 0

    @pytest.mark.asyncio
    async def test_run_override_concurrency(self):
        st = StressTester(concurrency=5)
        cases = [{"id": f"o-{i}", "model": "m1"} for i in range(10)]
        adapter = MockAdapter(latency=0.001)
        report = await st.run_stress_test(cases, adapter, concurrency=10)
        assert report.concurrency_actual == 10

    def test_format_report(self):
        report = StressTestReport(
            total_evals=10,
            completed=8,
            failed=1,
            timed_out=1,
            completion_rate=0.8,
            avg_latency=1.5,
            max_latency=3.0,
            fairness_ratio=0.9,
            scalability_score=85.0,
            verdict="PASS",
        )
        output = format_scalability_report(report)
        assert "Scalability" in output
        assert "PASS" in output
        assert "10" in output
        assert "85.0" in output

    def test_format_report_with_model_counts(self):
        report = StressTestReport(
            total_evals=10,
            completed=10,
            completion_rate=1.0,
            model_exec_counts={"m1": 5, "m2": 5},
        )
        output = format_scalability_report(report)
        assert "m1: 5" in output
        assert "m2: 5" in output

    def test_report_method(self):
        st = StressTester()
        report = StressTestReport(total_evals=5, completed=5, completion_rate=1.0)
        output = st.report(report)
        assert "Scalability" in output
