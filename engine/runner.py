import asyncio
import logging
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor
from aiolimiter import AsyncLimiter
import time

from engine.security_probes import SecurityScanner
from engine.envelope import EnvelopeChecker
from adapters.pricing import get_pricing

logger = logging.getLogger(__name__)


class EvalRunner:
    SECURITY_MAX_OUTPUT_LENGTH = 100000

    def __init__(self, max_concurrency: int = 5, rate_limit_rpm: int = 60, request_timeout: int = 120,
                 enable_security_scan: bool = True, enable_envelope: bool = True,
                 model_name: Optional[str] = None, cost_budget: float = 0.0):
        self.max_concurrency = max_concurrency
        self.rate_limit_rpm = rate_limit_rpm
        self.request_timeout = request_timeout
        self.model_name = model_name
        self.cost_budget = cost_budget
        self.limiter = AsyncLimiter(max_rate=rate_limit_rpm / 60, time_period=1)
        self.executor = ThreadPoolExecutor(max_workers=max_concurrency)
        self.total_tokens = 0
        self.total_cost = 0.0
        self.token_budget = None
        self.scanner = SecurityScanner() if enable_security_scan else None
        self.envelope = EnvelopeChecker(timeout_s=request_timeout, cost_budget=cost_budget) if enable_envelope else None
        self._pricing = get_pricing()

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

    @staticmethod
    async def _call_adapter(model_adapter, messages):
        cls = type(model_adapter)
        usage_method = getattr(cls, 'chat_with_usage', None)
        is_mock = hasattr(model_adapter, '_mock_name')
        has_usage = usage_method is not None and not is_mock
        if has_usage:
            result = model_adapter.chat_with_usage(messages)
            if asyncio.iscoroutine(result):
                result = await result
            return result
        content = model_adapter.chat(messages)
        if asyncio.iscoroutine(content):
            content = await content
        return content, {"prompt_tokens": 0, "completion_tokens": len(content.split()) if content else 0, "total_tokens": len(content.split()) if content else 0}

    def _calc_cost(self, token_usage: dict) -> float:
        if not self.model_name or not token_usage:
            return 0.0
        return self._pricing.calculate_cost(
            token_usage.get("prompt_tokens", 0),
            token_usage.get("completion_tokens", 0),
            self.model_name,
        )

    async def run_with_skill(self, evals: List[Dict[str, Any]], skill_path: str, model_adapter) -> List[Dict[str, Any]]:
        results = []

        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def run_single_eval(eval_case):
            async with semaphore:
                async with self.limiter:
                    try:
                        skill_context = f"Using skill from {skill_path}. "
                        input_with_context = skill_context + eval_case.get("input", "")

                        start_time = time.time()
                        response, token_usage = await self._run_with_timeout(
                            self._call_adapter(model_adapter, [{"role": "user", "content": input_with_context}]),
                            self.request_timeout
                        )
                        end_time = time.time()

                        result = {
                            "eval_id": eval_case.get("id"),
                            "eval_name": eval_case.get("name"),
                            "eval_category": eval_case.get("category"),
                            "model": getattr(model_adapter, 'model_name', 'unknown'),
                            "run": "with-skill",
                            "skill_used": True,
                            "input": input_with_context,
                            "output": response,
                            "execution_time": end_time - start_time,
                            "error": None,
                            "tokens_used": token_usage.get("total_tokens", len(response.split()) if response else 0),
                            "token_breakdown": token_usage,
                            "security": self._check_security(response),
                            "output_length_ok": self._check_output_length(response),
                            "cost": self._calc_cost(token_usage),
                        }

                        self.total_tokens += token_usage.get("total_tokens", 0)
                        self.total_cost += result["cost"]

                        return result
                    except asyncio.TimeoutError:
                        logger.warning(f"Eval {eval_case.get('id')} timed out")
                        return {
                            "eval_id": eval_case.get("id"),
                            "eval_name": eval_case.get("name"),
                            "eval_category": eval_case.get("category"),
                            "model": getattr(model_adapter, 'model_name', 'unknown'),
                            "run": "with-skill",
                            "skill_used": True,
                            "input": eval_case.get("input", ""),
                            "output": None,
                            "execution_time": self.request_timeout,
                            "error": "timeout",
                            "tokens_used": 0,
                            "cost": 0.0,
                        }
                    except Exception as e:
                        logger.error(f"Error running eval {eval_case.get('id')}: {str(e)}")
                        return {
                            "eval_id": eval_case.get("id"),
                            "eval_name": eval_case.get("name"),
                            "eval_category": eval_case.get("category"),
                            "model": getattr(model_adapter, 'model_name', 'unknown'),
                            "run": "with-skill",
                            "skill_used": True,
                            "input": eval_case.get("input", ""),
                            "output": None,
                            "execution_time": 0,
                            "error": str(e),
                            "tokens_used": 0,
                            "cost": 0.0,
                        }

        tasks = [run_single_eval(eval_case) for eval_case in evals]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed_results: list[dict[str, Any]] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Exception in eval {i}: {result}")
                processed_results.append({
                    "eval_id": evals[i].get("id"),
                    "eval_name": evals[i].get("name"),
                    "eval_category": evals[i].get("category"),
                    "model": getattr(model_adapter, 'model_name', 'unknown'),
                    "run": "with-skill",
                    "skill_used": True,
                    "input": evals[i].get("input", ""),
                    "output": None,
                    "execution_time": 0,
                    "error": str(result),
                    "tokens_used": 0,
                    "cost": 0.0,
                })
            else:
                processed_results.append(result)

        return processed_results

    async def run_without_skill(self, evals: List[Dict[str, Any]], model_adapter) -> List[Dict[str, Any]]:
        results = []

        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def run_single_eval(eval_case):
            async with semaphore:
                async with self.limiter:
                    try:
                        start_time = time.time()
                        response, token_usage = await self._run_with_timeout(
                            self._call_adapter(model_adapter, [{"role": "user", "content": eval_case.get("input", "")}]),
                            self.request_timeout
                        )
                        end_time = time.time()

                        result = {
                            "eval_id": eval_case.get("id"),
                            "eval_name": eval_case.get("name"),
                            "eval_category": eval_case.get("category"),
                            "model": getattr(model_adapter, 'model_name', 'unknown'),
                            "run": "without-skill",
                            "skill_used": False,
                            "input": eval_case.get("input", ""),
                            "output": response,
                            "execution_time": end_time - start_time,
                            "error": None,
                            "tokens_used": token_usage.get("total_tokens", len(response.split()) if response else 0),
                            "token_breakdown": token_usage,
                            "security": self._check_security(response),
                            "output_length_ok": self._check_output_length(response),
                            "cost": self._calc_cost(token_usage),
                        }

                        self.total_tokens += token_usage.get("total_tokens", 0)
                        self.total_cost += result["cost"]

                        return result
                    except asyncio.TimeoutError:
                        logger.warning(f"Eval {eval_case.get('id')} timed out")
                        return {
                            "eval_id": eval_case.get("id"),
                            "eval_name": eval_case.get("name"),
                            "eval_category": eval_case.get("category"),
                            "model": getattr(model_adapter, 'model_name', 'unknown'),
                            "run": "without-skill",
                            "skill_used": False,
                            "input": eval_case.get("input", ""),
                            "output": None,
                            "execution_time": self.request_timeout,
                            "error": "timeout",
                            "tokens_used": 0,
                            "cost": 0.0,
                        }
                    except Exception as e:
                        logger.error(f"Error running eval {eval_case.get('id')}: {str(e)}")
                        return {
                            "eval_id": eval_case.get("id"),
                            "eval_name": eval_case.get("name"),
                            "eval_category": eval_case.get("category"),
                            "model": getattr(model_adapter, 'model_name', 'unknown'),
                            "run": "without-skill",
                            "skill_used": False,
                            "input": eval_case.get("input", ""),
                            "output": None,
                            "execution_time": 0,
                            "error": str(e),
                            "tokens_used": 0,
                            "cost": 0.0,
                        }

        tasks = [run_single_eval(eval_case) for eval_case in evals]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed_results: list[dict[str, Any]] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Exception in eval {i}: {result}")
                processed_results.append({
                    "eval_id": evals[i].get("id"),
                    "eval_name": evals[i].get("name"),
                    "eval_category": evals[i].get("category"),
                    "model": getattr(model_adapter, 'model_name', 'unknown'),
                    "run": "without-skill",
                    "skill_used": False,
                    "input": evals[i].get("input", ""),
                    "output": None,
                    "execution_time": 0,
                    "error": str(result),
                    "tokens_used": 0,
                    "cost": 0.0,
                })
            else:
                processed_results.append(result)

        return processed_results

    async def _run_with_timeout(self, coro, timeout: int):
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            raise asyncio.TimeoutError(f"Operation timed out after {timeout} seconds")

    def close(self):
        self.executor.shutdown(wait=True)
