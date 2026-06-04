import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from adapters.pricing import get_pricing
from engine.constants import ConcurrencyLimits, SecurityLimits, TimingLimits
from engine.envelope import EnvelopeChecker
from engine.security_probes import SecurityScanner
from engine.trace_models import ExecutionTrace, TokenAccounting

logger = logging.getLogger(__name__)


class EvalRunner:
    SECURITY_MAX_OUTPUT_LENGTH = SecurityLimits.MAX_OUTPUT_LENGTH

    def __init__(self, max_concurrency: int = ConcurrencyLimits.MAX_CONCURRENCY, rate_limit_rpm: int = TimingLimits.RATE_LIMIT_RPM, request_timeout: int = TimingLimits.REQUEST_TIMEOUT,
                 enable_security_scan: bool = True, enable_envelope: bool = True,
                 model_name: str | None = None, cost_budget: float = 0.0,
                 token_ledger: Any | None = None):
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
        self.envelope = EnvelopeChecker(timeout_s=request_timeout, cost_budget=cost_budget) if enable_envelope else None
        self._pricing = get_pricing()
        self.token_ledger = token_ledger
        self._traces: list[ExecutionTrace] = []
        self._traces_lock = threading.Lock()

    def _wait_rate_limit(self):
        with self._rate_lock:
            elapsed = time.time() - self._last_request_time
            wait_time = self._min_interval - elapsed
            if wait_time > 0:
                time.sleep(wait_time)
            self._last_request_time = time.time()

    def _run_single(self, eval_case, skill_path: str, model_adapter, with_skill: bool):
        with self._semaphore:
            self._wait_rate_limit()
            # Create ExecutionTrace for observability
            model_name = getattr(model_adapter, 'model_name', 'unknown')
            trace = ExecutionTrace(
                eval_id=eval_case.get("id", 0),
                phase="with_skill" if with_skill else "without_skill",
                token_usage=TokenAccounting(model=model_name),
            )
            try:
                input_text = eval_case.get("input", "") or eval_case.get("prompt", "")
                if isinstance(input_text, dict):
                    input_text = str(input_text)

                if with_skill:
                    try:
                        with open(skill_path, encoding='utf-8') as f:
                            lines = f.readlines()
                            skill_header = ''.join(lines[:20])[:1000]
                    except (OSError, FileNotFoundError):
                        skill_header = skill_path
                    skill_context = f"Skill file: {skill_path}\n{skill_header}\n\n---\nTask: {input_text}"
                    input_text = skill_context

                trace.start_time = time.time()
                perf_start = time.perf_counter()
                messages = [{"role": "user", "content": input_text}]

                cls = type(model_adapter)
                usage_method = getattr(cls, 'chat_with_usage', None)
                is_mock = hasattr(model_adapter, '_mock_name')
                has_usage = usage_method is not None and not is_mock

                if has_usage:
                    response, token_usage = model_adapter.chat_with_usage(messages)
                else:
                    response = model_adapter.chat(messages)
                    token_usage = {
                        "prompt_tokens": 0,
                        "completion_tokens": len(response.split()) if response else 0,
                        "total_tokens": len(response.split()) if response else 0
                    }

                perf_elapsed = (time.perf_counter() - perf_start) * 1000
                end_time = time.time()
                trace.end_time = end_time

                # Record LLM call in trace (single source of truth for tokens)
                trace.record_llm_call(
                    model=model_name,
                    input_tokens=token_usage.get("prompt_tokens", 0),
                    output_tokens=token_usage.get("completion_tokens", 0),
                    latency_ms=perf_elapsed,
                )
                cost = self._calc_cost(token_usage) if self.model_name else 0.0
                trace.token_usage.cost = cost

                # Store trace for later aggregation
                with self._traces_lock:
                    self._traces.append(trace)
                if self.token_ledger:
                    self.token_ledger.record_trace(trace)

                result = {
                    "eval_id": eval_case.get("id"),
                    "eval_name": eval_case.get("name"),
                    "eval_category": eval_case.get("category"),
                    "model": model_name,
                    "run": "with-skill" if with_skill else "without-skill",
                    "skill_used": with_skill,
                    "input": input_text,
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

                self.total_tokens += token_usage.get("total_tokens", 0)
                self.total_cost += cost

                return result
            except Exception as e:
                logger.error(f"Error running eval {eval_case.get('id')}: {type(e).__name__}: {str(e)}")
                trace.end_time = time.time()
                trace.error = str(e)
                with self._traces_lock:
                    self._traces.append(trace)
                if self.token_ledger:
                    self.token_ledger.record_trace(trace)
                return {
                    "eval_id": eval_case.get("id"),
                    "eval_name": eval_case.get("name"),
                    "eval_category": eval_case.get("category"),
                    "model": model_name,
                    "run": "with-skill" if with_skill else "without-skill",
                    "skill_used": with_skill,
                    "input": eval_case.get("input") or eval_case.get("prompt"),
                    "output": None,
                    "execution_time": 0,
                    "error": str(e),
                    "tokens_used": 0,
                    "cost": 0.0,
                    "trace": trace.model_dump(mode="json"),
                }

    def run_with_skill(self, evals: list[dict[str, Any]], skill_path: str, model_adapter) -> list[dict[str, Any]]:
        results = []
        with ThreadPoolExecutor(max_workers=self.max_concurrency) as executor:
            futures = {executor.submit(self._run_single, ec, skill_path, model_adapter, True): i
                      for i, ec in enumerate(evals)}
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results.append((idx, future.result()))
                except Exception as e:
                    results.append((idx, {"eval_id": evals[idx].get("id"), "error": str(e)}))
        results.sort(key=lambda x: x[0])
        return [r for _, r in results]

    def run_without_skill(self, evals: list[dict[str, Any]], model_adapter) -> list[dict[str, Any]]:
        results = []
        with ThreadPoolExecutor(max_workers=self.max_concurrency) as executor:
            futures = {executor.submit(self._run_single, ec, None, model_adapter, False): i
                      for i, ec in enumerate(evals)}
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results.append((idx, future.result()))
                except Exception as e:
                    results.append((idx, {"eval_id": evals[idx].get("id"), "error": str(e)}))
        results.sort(key=lambda x: x[0])
        return [r for _, r in results]

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
        """Flush token ledger if present."""
        if self.token_ledger:
            self.token_ledger.flush()
        pass
