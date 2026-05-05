"""Reliability module — error classification, retry statistics, graceful degradation tracking."""

import re
from typing import Dict, Any, List, Optional


_ERROR_PATTERNS = [
    (r"(?i)timeout", "timeout"),
    (r"(?i)\b504\b", "timeout"),
    (r"(?i)\b429\b", "rate_limit"),
    (r"(?i)\b50[0-9]\b", "server_error"),
    (r"(?i)connection", "connection_error"),
    (r"(?i)protocol", "protocol_error"),
    (r"(?i)parse|json|decode", "parse_error"),
]


def classify_error(error_message: Optional[str]) -> str:
    """Categorize an error string into one of the known error categories."""
    if not error_message:
        return "none"
    for pattern, category in _ERROR_PATTERNS:
        if re.search(pattern, error_message):
            return category
    return "unknown"


class ReliabilityTracker:
    """Tracks eval reliability metrics across all runs."""
    
    def __init__(self):
        self.results: List[Dict[str, Any]] = []
    
    def record_eval(self, eval_id: str, success: bool, error: Optional[str], retry_count: int = 0):
        """Record the result of a single eval run."""
        self.results.append({
            "eval_id": eval_id,
            "success": success,
            "error": error,
            "error_category": classify_error(error) if error else "none",
            "retry_count": retry_count,
        })
    
    def generate_report(self) -> Dict[str, Any]:
        """Generate a reliability report from all recorded eval results."""
        total = len(self.results)
        if total == 0:
            return {
                "total_evals": 0,
                "success_count": 0,
                "error_count": 0,
                "success_rate": 0.0,
                "error_rate": 0.0,
                "errors_by_category": {},
                "retry_stats": {
                    "total_retries": 0,
                    "avg_retries": 0.0,
                    "max_retries": 0,
                },
            }
        
        success_count = sum(1 for r in self.results if r["success"])
        error_count = total - success_count
        
        errors_by_category: Dict[str, int] = {}
        for r in self.results:
            if r["error_category"] and r["error_category"] != "none":
                errors_by_category[r["error_category"]] = errors_by_category.get(r["error_category"], 0) + 1
        
        retries = [r["retry_count"] for r in self.results]
        
        return {
            "total_evals": total,
            "success_count": success_count,
            "error_count": error_count,
            "success_rate": success_count / total,
            "error_rate": error_count / total,
            "errors_by_category": errors_by_category,
            "retry_stats": {
                "total_retries": sum(retries),
                "avg_retries": sum(retries) / len(retries),
                "max_retries": max(retries),
            },
        }
