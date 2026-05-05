import logging
import threading
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
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
            try:
                input_text = eval_case.get("input", "") or eval_case.get("prompt", "")
                if isinstance(input_text, dict):
                    input_text = str(input_text)
                
                if with_skill:
                    try:
                        with open(skill_path, 'r', encoding='utf-8') as f:
                            lines = f.readlines()
                            skill_header = ''.join(lines[:20])[:1000]
                    except (FileNotFoundError, IOError):
                        skill_header = skill_path
                    skill_context = f"Skill file: {skill_path}\n{skill_header}\n\n---\nTask: {input_text}"
                    input_text = skill_context
                
                start_time = time.time()
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
                
                end_time = time.time()
                
                cost = self._calc_cost(token_usage) if self.model_name else 0.0
                
                result = {
                    "eval_id": eval_case.get("id"),
                    "eval_name": eval_case.get("name"),
                    "eval_category": eval_case.get("category"),
                    "model": getattr(model_adapter, 'model_name', 'unknown'),
                    "run": "with-skill" if with_skill else "without-skill",
                    "skill_used": with_skill,
                    "input": input_text,
                    "output": response,
                    "execution_time": end_time - start_time,
                    "error": None,
                    "tokens_used": token_usage.get("total_tokens", 0),
                    "token_breakdown": token_usage,
                    "security": self._check_security(response),
                    "output_length_ok": self._check_output_length(response),
                    "cost": cost,
                }
                
                self.total_tokens += token_usage.get("total_tokens", 0)
                self.total_cost += cost
                
                return result
            except Exception as e:
                logger.error(f"Error running eval {eval_case.get('id')}: {type(e).__name__}: {str(e)}")
                return {
                    "eval_id": eval_case.get("id"),
                    "eval_name": eval_case.get("name"),
                    "eval_category": eval_case.get("category"),
                    "model": getattr(model_adapter, 'model_name', 'unknown'),
                    "run": "with-skill" if with_skill else "without-skill",
                    "skill_used": with_skill,
                    "input": eval_case.get("input") or eval_case.get("prompt"),
                    "output": None,
                    "execution_time": 0,
                    "error": str(e),
                    "tokens_used": 0,
                    "cost": 0.0,
                }

    def run_with_skill(self, evals: List[Dict[str, Any]], skill_path: str, model_adapter) -> List[Dict[str, Any]]:
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

    def run_without_skill(self, evals: List[Dict[str, Any]], model_adapter) -> List[Dict[str, Any]]:
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

    def close(self):
        pass
