import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any

from adapters.pricing import get_pricing
from engine.constants import ConcurrencyLimits, SecurityLimits, TimingLimits
from engine.deadline import Deadline
from engine.envelope import EnvelopeChecker
from engine.observability import SessionTelemetry
from engine.security_probes import SecurityScanner
from engine.trace_models import ExecutionTrace, TokenAccounting

logger = logging.getLogger(__name__)


class EvalRunner:
    SECURITY_MAX_OUTPUT_LENGTH = SecurityLimits.MAX_OUTPUT_LENGTH

    def __init__(
        self,
        max_concurrency: int = ConcurrencyLimits.MAX_CONCURRENCY,
        rate_limit_rpm: int = TimingLimits.RATE_LIMIT_RPM,
        request_timeout: int = TimingLimits.REQUEST_TIMEOUT,
        enable_security_scan: bool = True,
        enable_envelope: bool = True,
        model_name: str | None = None,
        cost_budget: float = 0.0,
        token_ledger: Any | None = None,
        telemetry: SessionTelemetry | None = None,
    ):
        self.max_concurrency = max_concurrency
        self.rate_limit_rpm = rate_limit_rpm
        self.request_timeout = request_timeout
        self.model_name = model_name
        self.cost_budget = cost_budget
        self._semaphore = threading.Semaphore(max_concurrency)
        self._rate_lock = threading.Lock()
        self._last_request_time = 0.0
        self._min_interval = 60.0 / rate_limit_rpm if rate_limit_rpm > 0 else 0.0
        self.executor = ThreadPoolExecutor(max_workers=max_concurrency)
        self.total_tokens = 0
        self.total_cost = 0.0
        self.token_budget = None
        self.scanner = SecurityScanner() if enable_security_scan else None
        self.envelope = (
            EnvelopeChecker(timeout_s=request_timeout, cost_budget=cost_budget)
            if enable_envelope
            else None
        )
        self._pricing = get_pricing()
        self.token_ledger = token_ledger
        self.telemetry = telemetry
        self._traces: list[ExecutionTrace] = []
        self._traces_lock = threading.Lock()

    def _wait_rate_limit(self):
        with self._rate_lock:
            elapsed = time.time() - self._last_request_time
            wait_time = self._min_interval - elapsed
            if wait_time > 0:
                time.sleep(wait_time)
            self._last_request_time = time.time()

    def _prepare_input(self, eval_case: dict, skill_path: str | None, with_skill: bool) -> str:
        """Prepare input text with or without skill context."""
        input_text = eval_case.get("input", "") or eval_case.get("prompt", "")
        if isinstance(input_text, dict):
            input_text = str(input_text)

        if not with_skill or skill_path is None:
            return input_text

        try:
            with open(skill_path, encoding="utf-8") as f:
                lines = f.readlines()
                skill_header = "".join(lines[:20])[:1000]
        except (OSError, FileNotFoundError):
            skill_header = skill_path

        skill_context = f"Skill file: {skill_path}\n{skill_header}\n\n---\nTask: {input_text}"
        return skill_context

    def _execute_llm_call(self, model_adapter, messages: list) -> tuple[str, dict]:
        """Execute LLM call and return response with token usage."""
        cls = type(model_adapter)
        usage_method = getattr(cls, "chat_with_usage", None)
        is_mock = hasattr(model_adapter, "_mock_name")
        has_usage = usage_method is not None and not is_mock

        if has_usage:
            response, token_usage = model_adapter.chat_with_usage(messages)
        else:
            response = model_adapter.chat(messages)
            token_usage = {
                "prompt_tokens": 0,
                "completion_tokens": len(response.split()) if response else 0,
                "total_tokens": len(response.split()) if response else 0,
            }

        return response, token_usage

    def _build_success_result(
        self,
        eval_case: dict,
        trace: ExecutionTrace,
        response: str,
        token_usage: dict,
        perf_elapsed: float,
        cost: float,
    ) -> dict:
        """Build success result dictionary."""
        end_time = time.time()
        trace.end_time = end_time

        return {
            "eval_id": eval_case.get("id"),
            "eval_name": eval_case.get("name"),
            "eval_category": eval_case.get("category"),
            "model": trace.token_usage.model,
            "run": trace.phase.replace("_", "-"),
            "skill_used": trace.phase == "with_skill",
            "input": eval_case.get("input") or eval_case.get("prompt"),
            "output": response,
            "execution_time": end_time - trace.start_time,
            "error": None,
            "tokens_used": token_usage.get("total_tokens", 0),
            "token_breakdown": token_usage,
            "security": self._check_security(response),
            "output_length_ok": self._check_output_length(response),
            "cost": cost,
            "trace": trace.model_dump(mode="json"),
        }

    def _build_error_result(
        self,
        eval_case: dict,
        trace: ExecutionTrace,
        error: str,
    ) -> dict:
        """Build error result dictionary."""
        end_time = time.time()
        trace.end_time = end_time
        trace.error = error

        return {
            "eval_id": eval_case.get("id"),
            "eval_name": eval_case.get("name"),
            "eval_category": eval_case.get("category"),
            "model": trace.token_usage.model,
            "run": trace.phase.replace("_", "-"),
            "skill_used": trace.phase == "with_skill",
            "input": eval_case.get("input") or eval_case.get("prompt"),
            "output": None,
            "execution_time": 0,
            "error": error,
            "tokens_used": 0,
            "cost": 0.0,
            "trace": trace.model_dump(mode="json"),
        }

    def _run_single(
        self,
        eval_case,
        skill_path: str | None,
        model_adapter,
        with_skill: bool,
        deadline: Deadline | None = None,
    ):
        """Run a single eval case with execution phases extracted."""
        with self._semaphore:
            self._wait_rate_limit()

            model_name = getattr(model_adapter, "model_name", "unknown")
            trace = ExecutionTrace(
                eval_id=eval_case.get("id", 0),
                phase="with_skill" if with_skill else "without_skill",
                token_usage=TokenAccounting(model=model_name),
            )

            try:
                if deadline is not None and deadline.must_stop():
                    return self._build_error_result(eval_case, trace, "Deadline reached")

                input_text = self._prepare_input(eval_case, skill_path, with_skill)

                trace.start_time = time.time()
                perf_start = time.perf_counter()
                messages = [{"role": "user", "content": input_text}]

                response, token_usage = self._execute_llm_call(model_adapter, messages)
                perf_elapsed = (time.perf_counter() - perf_start) * 1000
                cost = self._calc_cost(token_usage) if self.model_name else 0.0

                trace.record_llm_call(
                    model=model_name,
                    input_tokens=token_usage.get("prompt_tokens", 0),
                    output_tokens=token_usage.get("completion_tokens", 0),
                    latency_ms=perf_elapsed,
                )
                trace.token_usage.cost = cost

                with self._traces_lock:
                    self._traces.append(trace)
                if self.token_ledger:
                    self.token_ledger.record_trace(trace)
                if self.telemetry:
                    self.telemetry.record_trace(trace)

                self.total_tokens += token_usage.get("total_tokens", 0)
                self.total_cost += cost

                return self._build_success_result(
                    eval_case, trace, response, token_usage, perf_elapsed, cost
                )
            except Exception as e:
                logger.error(
                    f"Error running eval {eval_case.get('id')}: {type(e).__name__}: {str(e)}"
                )
                return self._build_error_result(eval_case, trace, str(e))

    def run_with_skill(
        self,
        evals: list[dict[str, Any]],
        skill_path: str,
        model_adapter,
        deadline: Deadline | None = None,
    ) -> list[dict[str, Any]]:
        results: list[tuple[int, dict[str, Any]]] = []
        partial = False
        total = len(evals)
        completed = 0
        next_log_pct = 20
        with ThreadPoolExecutor(max_workers=self.max_concurrency) as executor:
            futures = {
                executor.submit(self._run_single, ec, skill_path, model_adapter, True, deadline): i
                for i, ec in enumerate(evals)
            }
            initial_timeout = deadline.remaining if deadline is not None else None
            try:
                for future in as_completed(futures, timeout=initial_timeout):
                    # Re-check deadline on each iteration — don't wait for next future if expired
                    if deadline is not None and deadline.expired:
                        partial = True
                        executor.shutdown(wait=False, cancel_futures=True)
                        for f in futures:
                            if f.done():
                                i = futures[f]
                                try:
                                    results.append((i, f.result()))
                                except Exception as e:
                                    results.append(
                                        (i, {"eval_id": evals[i].get("id"), "error": str(e)})
                                    )
                        break
                    idx = futures[future]
                    completed += 1
                    pct = 100.0 * completed / total
                    if completed == total or pct >= next_log_pct:
                        logger.info("Eval progress: %d/%d (%.0f%%)", completed, total, pct)
                        next_log_pct += 20
                    try:
                        results.append((idx, future.result()))
                    except Exception as e:
                        results.append((idx, {"eval_id": evals[idx].get("id"), "error": str(e)}))
            except FuturesTimeoutError:
                partial = True
                executor.shutdown(wait=False, cancel_futures=True)
                # Collect already-completed futures
                for future in futures:
                    if future.done():
                        idx = futures[future]
                        try:
                            results.append((idx, future.result()))
                        except Exception as e:
                            results.append(
                                (idx, {"eval_id": evals[idx].get("id"), "error": str(e)})
                            )
        results.sort(key=lambda x: x[0])
        result_list = [r for _, r in results]
        if partial:
            result_list.append(
                {"_partial": True, "message": "Deadline reached, partial results only"}
            )
        return result_list

    def run_without_skill(
        self,
        evals: list[dict[str, Any]],
        model_adapter,
        deadline: Deadline | None = None,
    ) -> list[dict[str, Any]]:
        results: list[tuple[int, dict[str, Any]]] = []
        partial = False
        total = len(evals)
        completed = 0
        next_log_pct = 20
        with ThreadPoolExecutor(max_workers=self.max_concurrency) as executor:
            futures = {
                executor.submit(self._run_single, ec, None, model_adapter, False, deadline): i
                for i, ec in enumerate(evals)
            }
            initial_timeout = deadline.remaining if deadline is not None else None
            try:
                for future in as_completed(futures, timeout=initial_timeout):
                    if deadline is not None and deadline.expired:
                        partial = True
                        executor.shutdown(wait=False, cancel_futures=True)
                        for f in futures:
                            if f.done():
                                i = futures[f]
                                try:
                                    results.append((i, f.result()))
                                except Exception as e:
                                    results.append(
                                        (i, {"eval_id": evals[i].get("id"), "error": str(e)})
                                    )
                        break
                    idx = futures[future]
                    completed += 1
                    pct = 100.0 * completed / total
                    if completed == total or pct >= next_log_pct:
                        logger.info("Eval progress: %d/%d (%.0f%%)", completed, total, pct)
                        next_log_pct += 20
                    try:
                        results.append((idx, future.result()))
                    except Exception as e:
                        results.append((idx, {"eval_id": evals[idx].get("id"), "error": str(e)}))
            except FuturesTimeoutError:
                partial = True
                executor.shutdown(wait=False, cancel_futures=True)
                for future in futures:
                    if future.done():
                        idx = futures[future]
                        try:
                            results.append((idx, future.result()))
                        except Exception as e:
                            results.append(
                                (idx, {"eval_id": evals[idx].get("id"), "error": str(e)})
                            )
        results.sort(key=lambda x: x[0])
        result_list = [r for _, r in results]
        if partial:
            result_list.append(
                {"_partial": True, "message": "Deadline reached, partial results only"}
            )
        return result_list

    def _calc_cost(self, token_usage: dict) -> float:
        if not self.model_name or not token_usage:
            return 0.0
        return self._pricing.calculate_cost(
            token_usage.get("prompt_tokens", 0),
            token_usage.get("completion_tokens", 0),
            self.model_name,
        )

    def _check_security(self, output: str) -> dict:
        if not self.scanner:
            return {"scanned": False}
        report = self.scanner.scan(output)
        return {
            "scanned": True,
            "verdict": report.verdict,
            "score": report.score,
            "findings_count": report.summary.get("total", 0),
            "critical": report.summary.get("critical", 0),
            "high": report.summary.get("high", 0),
        }

    def _check_output_length(self, output: str) -> bool:
        return len(output) <= self.SECURITY_MAX_OUTPUT_LENGTH if output else True

    def get_traces(self) -> list[ExecutionTrace]:
        """Return all collected ExecutionTrace instances."""
        with self._traces_lock:
            return list(self._traces)

    def close(self):
        """Flush token ledger and telemetry if present."""
        if self.token_ledger:
            self.token_ledger.flush()
        if self.telemetry:
            self.telemetry.flush()
        pass
