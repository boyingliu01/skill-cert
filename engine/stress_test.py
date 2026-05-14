"""Scalability testing — concurrent stress tests and fairness validation."""

from __future__ import annotations

import asyncio
import statistics
import time
import tracemalloc
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class StressTestResult:
    eval_id: str
    model: str
    status: str = "success"
    latency: float = 0.0
    error: Optional[str] = None


@dataclass
class StressTestReport:
    total_evals: int = 0
    completed: int = 0
    failed: int = 0
    timed_out: int = 0
    errored: int = 0
    completion_rate: float = 0.0
    avg_latency: float = 0.0
    min_latency: float = 0.0
    max_latency: float = 0.0
    median_latency: float = 0.0
    p95_latency: float = 0.0
    p99_latency: float = 0.0
    memory_mb_peak: float = 0.0
    model_exec_counts: Dict[str, int] = field(default_factory=dict)
    fairness_ratio: float = 1.0
    concurrency_actual: int = 0
    errors: list = field(default_factory=list)
    scalability_score: float = 100.0
    verdict: str = "PASS"


class RateLimiter:

    def __init__(self, rpm: int = 60, models: Optional[list] = None):
        self.rpm = rpm
        self._lock = asyncio.Lock()
        self._model_counts: Dict[str, int] = {}
        self._per_model_rpm: Optional[Dict[str, int]] = None
        if models and rpm > 0:
            per_model = max(1, rpm // len(models))
            self._per_model_rpm = {m: per_model for m in models}

    async def acquire(self, model: Optional[str] = None) -> None:
        async with self._lock:
            if model and self._per_model_rpm and model in self._per_model_rpm:
                self._model_counts[model] = self._model_counts.get(model, 0) + 1

    def get_model_counts(self) -> Dict[str, int]:
        return dict(self._model_counts)


class StressTester:

    def __init__(
        self,
        concurrency: int = 5,
        rate_limit_rpm: int = 60,
        timeout_per_eval: float = 60.0,
        models: Optional[list] = None,
    ) -> None:
        self.concurrency = concurrency
        self.timeout_per_eval = timeout_per_eval
        self._models = models or []
        self._rate_limiter = RateLimiter(rpm=rate_limit_rpm, models=self._models)

    async def _execute_single(
        self,
        eval_case: Dict[str, Any],
        model_adapter: Any,
        semaphore: asyncio.Semaphore,
        results: list,
    ) -> None:
        eval_id = eval_case.get("id", "unknown")
        model = eval_case.get("model", "unknown")
        start = time.monotonic()
        try:
            async with semaphore:
                await self._rate_limiter.acquire(model=model)
                try:
                    await asyncio.wait_for(
                        model_adapter.generate(eval_case),
                        timeout=self.timeout_per_eval,
                    )
                    latency = time.monotonic() - start
                    results.append(
                        StressTestResult(
                            eval_id=eval_id,
                            model=model,
                            status="success",
                            latency=latency,
                        )
                    )
                except asyncio.TimeoutError:
                    latency = time.monotonic() - start
                    results.append(
                        StressTestResult(
                            eval_id=eval_id,
                            model=model,
                            status="timeout",
                            latency=latency,
                        )
                    )
                except Exception as exc:
                    latency = time.monotonic() - start
                    results.append(
                        StressTestResult(
                            eval_id=eval_id,
                            model=model,
                            status="error",
                            latency=latency,
                            error=str(exc),
                        )
                    )
        except Exception as exc:
            latency = time.monotonic() - start
            results.append(
                StressTestResult(
                    eval_id=eval_id,
                    model=model,
                    status="error",
                    latency=latency,
                    error=str(exc),
                )
            )

    async def run_stress_test(
        self,
        eval_cases: list,
        model_adapter: Any,
        concurrency: Optional[int] = None,
    ) -> StressTestReport:
        conc = concurrency or self.concurrency
        if not tracemalloc.is_tracing():
            tracemalloc.start()

        semaphore = asyncio.Semaphore(conc)
        results: list[StressTestResult] = []
        tasks = [
            asyncio.create_task(
                self._execute_single(case, model_adapter, semaphore, results)
            )
            for case in eval_cases
        ]

        await asyncio.gather(*tasks, return_exceptions=True)

        total = len(eval_cases)
        completed = sum(1 for r in results if r.status == "success")
        failed = sum(1 for r in results if r.status == "failed")
        timed_out = sum(1 for r in results if r.status == "timeout")
        errored = sum(1 for r in results if r.status == "error")

        latencies = [r.latency for r in results if r.latency > 0]
        avg_lat = statistics.mean(latencies) if latencies else 0.0
        min_lat = min(latencies) if latencies else 0.0
        max_lat = max(latencies) if latencies else 0.0
        median_lat = statistics.median(latencies) if latencies else 0.0
        p95_lat = self._percentile(latencies, 95)
        p99_lat = self._percentile(latencies, 99)

        current, peak = tracemalloc.get_traced_memory()
        memory_mb_peak = peak / (1024 * 1024)

        model_exec_counts: Dict[str, int] = {}
        for r in results:
            model_exec_counts[r.model] = model_exec_counts.get(r.model, 0) + 1

        fairness_ratio = 1.0
        if model_exec_counts:
            max_count = max(model_exec_counts.values())
            min_count = min(model_exec_counts.values())
            if max_count > 0:
                fairness_ratio = min_count / max_count

        completion_rate = completed / total if total > 0 else 0.0

        scalability_score = self._calculate_scalability_score(
            completion_rate, fairness_ratio, avg_lat, concurrency=conc
        )
        verdict = "PASS" if scalability_score >= 70 else "FAIL"

        return StressTestReport(
            total_evals=total,
            completed=completed,
            failed=failed,
            timed_out=timed_out,
            errored=errored,
            completion_rate=completion_rate,
            avg_latency=avg_lat,
            min_latency=min_lat,
            max_latency=max_lat,
            median_latency=median_lat,
            p95_latency=p95_lat,
            p99_latency=p99_lat,
            memory_mb_peak=memory_mb_peak,
            model_exec_counts=model_exec_counts,
            fairness_ratio=fairness_ratio,
            concurrency_actual=conc,
            scalability_score=scalability_score,
            verdict=verdict,
        )

    @staticmethod
    def _percentile(data: list[float], percentile: float) -> float:
        if not data:
            return 0.0
        sorted_data = sorted(data)
        k = (len(sorted_data) - 1) * (percentile / 100.0)
        f = int(k)
        c = f + 1 if f + 1 < len(sorted_data) else f
        d = k - f
        return sorted_data[f] + d * (sorted_data[c] - sorted_data[f])

    @staticmethod
    def _calculate_scalability_score(
        completion_rate: float,
        fairness_ratio: float,
        avg_latency: float,
        concurrency: int = 5,
    ) -> float:
        score = 100.0
        score -= (1 - completion_rate) * 50
        score -= (1 - fairness_ratio) * 25
        if avg_latency > 10:
            score -= 10
        elif avg_latency > 5:
            score -= 5
        return max(0.0, min(100.0, score))

    def report(self, stress_result: StressTestReport) -> str:
        return format_scalability_report(stress_result)


def format_scalability_report(result: StressTestReport) -> str:
    sections = [
        "",
        "## Scalability",
        "",
        f"**Verdict:** {result.verdict} | **Score:** {result.scalability_score:.1f}/100",
        "",
        f"- **Total evals:** {result.total_evals}",
        f"- **Completed:** {result.completed}",
        f"- **Failed:** {result.failed}",
        f"- **Timed out:** {result.timed_out}",
        f"- **Errored:** {result.errored}",
        f"- **Completion rate:** {result.completion_rate:.1%}",
        f"- **Fairness ratio:** {result.fairness_ratio:.2f}",
        "",
        "**Latency**",
        "",
        f"- **Avg:** {result.avg_latency:.2f}s",
        f"- **Min:** {result.min_latency:.2f}s | **Max:** {result.max_latency:.2f}s",
        f"- **Median:** {result.median_latency:.2f}s",
        f"- **P95:** {result.p95_latency:.2f}s | **P99:** {result.p99_latency:.2f}s",
        "",
        f"**Peak memory:** {result.memory_mb_peak:.2f} MB",
        "",
        "**Model execution counts**",
        "",
    ]
    for model, count in result.model_exec_counts.items():
        sections.append(f"- {model}: {count}")
    sections.append("")
    return "\n".join(sections)
