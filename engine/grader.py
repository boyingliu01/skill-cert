"""Grading module for skill-cert engine — evaluates model outputs against eval assertions."""

import json
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field


class JudgeResult(BaseModel):
    """Structure for LLM-as-judge evaluation results."""
    passed: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""
    failure_reasons: list[dict[str, str]] = Field(default_factory=list)
    position_sensitive: bool = False
    debias_runs: int = 1
    judge_version: str = "2.0"
    judge_model: str = ""


class EvalAssertion(BaseModel):
    """Single assertion in an evaluation case."""
    name: str
    type: str  # contains, not_contains, regex, starts_with, json_valid
    value: str
    weight: int = 1  # 1=Normal, 2=Important, 3=Critical


class EvalCase(BaseModel):
    """Single evaluation test case."""
    id: int
    name: str
    category: str  # normal, boundary, failure, trigger
    prompt: str
    expected_output: str | None = None
    files: list[str] = Field(default_factory=list)
    assertions: list[EvalAssertion]
    workflow_step: str | None = None  # Name of the workflow step this case targets


@dataclass
class AssertionResult:
    """Result of a single assertion evaluation."""
    assertion: EvalAssertion
    passed: bool
    confidence: float
    reason: str


class Grader:
    """Evaluates model outputs against eval assertions."""

    def __init__(self, llm_client=None):
        """Initialize grader with optional LLM client for judge mode."""
        self.llm_client = llm_client

    def grade_output(self, eval_case: EvalCase, model_output: str) -> dict[str, Any]:
        """Evaluate a single model output against eval case assertions."""
        results = []
        total_weighted_score = 0
        total_possible_score = 0

        for assertion in eval_case.assertions:
            result = self._evaluate_assertion(assertion, model_output)
            results.append(result)

            # Calculate weighted score
            weight_multiplier = self._get_weight_multiplier(assertion.weight)
            if result.passed:
                total_weighted_score += weight_multiplier
            total_possible_score += weight_multiplier

        # Calculate pass rate
        pass_rate = total_weighted_score / total_possible_score if total_possible_score > 0 else 0.0

        # Determine if we need LLM-as-judge for complex behavior
        deterministic_passed_count = sum(1 for r in results if r.confidence == 1.0 and r.passed)
        deterministic_total_count = sum(1 for r in results if r.confidence == 1.0)

        # If not all deterministic assertions passed, or if we have complex cases, use LLM judge
        use_llm_judge = (
            deterministic_total_count < len(results) or  # Some assertions are non-deterministic
            deterministic_passed_count < deterministic_total_count  # Some deterministic failed
        )

        judge_result = None
        if use_llm_judge and self.llm_client:
            judge_result = self._llm_judge(eval_case, model_output, results)

        return {
            "eval_id": eval_case.id,
            "eval_name": eval_case.name,
            "category": eval_case.category,
            "workflow_step": eval_case.workflow_step,
            "model_output": model_output,
            "assertion_results": [
                {
                    "assertion": result.assertion.model_dump(),
                    "passed": result.passed,
                    "confidence": result.confidence,
                    "reason": result.reason
                }
                for result in results
            ],
            "total_weighted_score": total_weighted_score,
            "total_possible_score": total_possible_score,
            "pass_rate": pass_rate,
            "judge_result": judge_result.model_dump() if judge_result else None,
            "final_passed": judge_result.passed if judge_result and judge_result.confidence >= 0.8 else pass_rate >= 0.5
        }

    def _evaluate_assertion(self, assertion: EvalAssertion, model_output: str) -> AssertionResult:
        """Evaluate a single assertion against model output."""
        if assertion.type == "contains":
            passed = assertion.value.lower() in model_output.lower()
            confidence = 1.0
            reason = f"'{assertion.value}' {'found' if passed else 'not found'} in output"
        elif assertion.type == "not_contains":
            passed = assertion.value.lower() not in model_output.lower()
            confidence = 1.0
            reason = f"'{assertion.value}' {'not found' if passed else 'found'} in output"
        elif assertion.type == "regex":
            try:
                pattern = re.compile(assertion.value)
                match = pattern.search(model_output)
                passed = bool(match)
                confidence = 1.0
                reason = f"Regex '{assertion.value}' {'matched' if passed else 'did not match'} output"
            except re.error:
                passed = False
                confidence = 0.0
                reason = f"Invalid regex pattern: {assertion.value}"
        elif assertion.type == "starts_with":
            passed = model_output.startswith(assertion.value)
            confidence = 1.0
            reason = f"Output {'starts with' if passed else 'does not start with'} '{assertion.value}'"
        elif assertion.type == "json_valid":
            try:
                json.loads(model_output)
                passed = True
                confidence = 1.0
                reason = "Output is valid JSON"
            except json.JSONDecodeError:
                passed = False
                confidence = 1.0
                reason = "Output is not valid JSON"
        else:
            # Unknown assertion type - treat as failed with low confidence
            passed = False
            confidence = 0.0
            reason = f"Unknown assertion type: {assertion.type}"

        return AssertionResult(
            assertion=assertion,
            passed=passed,
            confidence=confidence,
            reason=reason
        )

    def _get_weight_multiplier(self, weight: int) -> int:
        """Convert weight to multiplier: 1=Normal=1, 2=Important=2, 3=Critical=3."""
        return max(1, min(3, weight))  # Clamp between 1 and 3

    def _llm_judge(self, eval_case: EvalCase, model_output: str, assertion_results: list[AssertionResult]) -> JudgeResult | None:
        """Use LLM as judge for complex behavior evaluation."""
        import os

        if not assertion_results:
            return JudgeResult(
                passed=False,
                confidence=0.0,
                reasoning="No assertions to evaluate",
                judge_version="1.0",
                judge_model="",
            )

        # Check if LLM judge is disabled via environment variable
        llm_judge_enabled = os.environ.get("SKILL_CERT_LLM_JUDGE_ENABLED", "true").lower() != "false"

        # Fallback to simplified logic if LLM client is None or LLM judge is disabled
        if self.llm_client is None or not llm_judge_enabled:
            passed_assertions = sum(1 for r in assertion_results if r.passed)
            total_assertions = len(assertion_results)
            passed_ratio = passed_assertions / total_assertions
            return JudgeResult(
                passed=passed_ratio >= 0.5,
                confidence=passed_ratio,
                reasoning=f"LLM evaluation: {passed_assertions}/{total_assertions} assertions passed ({passed_ratio:.2f})",
                judge_version="1.0",
                judge_model="",
            )

        expected_behavior = eval_case.expected_output or eval_case.prompt

        prompt = f"""# LLM-as-Judge Prompt

你是一个严格的评测裁判。评估以下模型输出是否满足指定的行为要求。

## 评测要求

1. 回答 `passed`: true 或 false
2. 给出 `confidence`（0.0 - 1.0）
3. 用 `reasoning` 简要说明理由
4. 对于每个未通过的断言，在 `failure_reasons` 中给出具体失败原因
5. temperature=0，确保确定性

## 断言列表

{self._format_assertions_for_judge(assertion_results)}

## 评测任务

**Skill 输出**:
```
{model_output}
```

**行为要求**:
```
{expected_behavior}
```

## 输出格式（严格 JSON）

```json
{{
  "passed": true,
  "confidence": 0.95,
  "reasoning": "输出包含了所有要求的步骤",
  "failure_reasons": []
}}
```"""

        try:
            # Call LLM with judge prompt — temperature=0 for deterministic results
            response_text = self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                timeout=30,
            )

            # Parse JSON response — handle possible Markdown code block wrapping
            response_text = response_text.strip()
            if "```json" in response_text:
                start = response_text.find("```json") + 7
                end = response_text.find("```", start)
                if end > start:
                    response_text = response_text[start:end].strip()
            elif response_text.startswith("```") and "```" in response_text[3:]:
                start = 3
                end = response_text.find("```", start)
                if end > start:
                    response_text = response_text[start:end].strip()

            judge_data = json.loads(response_text)

            failure_reasons = judge_data.get("failure_reasons", [])
            if not isinstance(failure_reasons, list):
                failure_reasons = []

            result = JudgeResult(
                passed=bool(judge_data.get("passed", False)),
                confidence=float(judge_data.get("confidence", 0.5)),
                reasoning=str(judge_data.get("reasoning", "")),
                failure_reasons=failure_reasons,
                judge_version="2.0",
                judge_model="llm",
            )

            # Position debias: for borderline cases (confidence < 0.8), run swap
            if result.confidence < 0.8 and self.llm_client:
                result = self._debias_position(
                    eval_case, model_output, assertion_results, result
                )

            return result
        except Exception as e:
            # Fallback to simplified logic on any error (network, parse, etc.)
            passed_assertions = sum(1 for r in assertion_results if r.passed)
            total_assertions = len(assertion_results)
            passed_ratio = passed_assertions / total_assertions if total_assertions > 0 else 0.0
            return JudgeResult(
                passed=passed_ratio >= 0.5,
                confidence=passed_ratio,
                reasoning=f"LLM judge call failed ({e}), fallback to assertion-based: {passed_assertions}/{total_assertions} passed ({passed_ratio:.2f})",
                judge_version="2.0",
                judge_model="",
            )

    def _debias_position(
        self,
        eval_case: EvalCase,
        model_output: str,
        assertion_results: list[AssertionResult],
        first_result: JudgeResult,
    ) -> JudgeResult:
        """Run a second judge call with swapped positions to detect position bias.

        If the two calls disagree, reduce confidence and mark position_sensitive.
        """
        expected_behavior = eval_case.expected_output or eval_case.prompt

        # Swap: put expected_behavior as "output" and model_output as "requirement"
        swap_prompt = f"""# LLM-as-Judge (Swap Run)

你是一个严格的评测裁判。评估以下输出是否满足行为要求。

## 评测要求
1. 回答 passed: true/false, confidence: 0.0-1.0, reasoning: 简要理由
2. 对于未通过的断言在 failure_reasons 中列出

## 输出（原始行为要求）:
```
{expected_behavior}
```

## 行为要求（原始模型输出）:
```
{model_output}
```

## 输出 JSON:
```json
{{"passed": true, "confidence": 0.9, "reasoning": "...", "failure_reasons": []}}
```"""
        try:
            swap_text = self.llm_client.chat(
                messages=[{"role": "user", "content": swap_prompt}], timeout=30
            )
            swap_text = swap_text.strip()
            if "```json" in swap_text:
                start = swap_text.find("```json") + 7
                end = swap_text.find("```", start)
                if end > start:
                    swap_text = swap_text[start:end].strip()
            swap_data = json.loads(swap_text)
            swap_passed = bool(swap_data.get("passed", False))
            swap_confidence = float(swap_data.get("confidence", 0.5))

            if swap_passed != first_result.passed:
                # Disagreement → reduce confidence, mark sensitive
                return JudgeResult(
                    passed=first_result.passed,
                    confidence=min(first_result.confidence, swap_confidence) * 0.7,
                    reasoning=f"{first_result.reasoning} [Position debias: disagreement detected]",
                    failure_reasons=first_result.failure_reasons,
                    position_sensitive=True,
                    debias_runs=2,
                    judge_version="2.0",
                    judge_model=first_result.judge_model,
                )
            else:
                # Agreement → keep first result, mark as verified
                return JudgeResult(
                    passed=first_result.passed,
                    confidence=max(first_result.confidence, swap_confidence),
                    reasoning=first_result.reasoning,
                    failure_reasons=first_result.failure_reasons,
                    position_sensitive=False,
                    debias_runs=2,
                    judge_version="2.0",
                    judge_model=first_result.judge_model,
                )
        except Exception:
            # Swap call failed → return first result unchanged
            return JudgeResult(
                passed=first_result.passed,
                confidence=first_result.confidence,
                reasoning=first_result.reasoning,
                failure_reasons=first_result.failure_reasons,
                position_sensitive=False,
                debias_runs=1,
                judge_version="2.0",
                judge_model=first_result.judge_model,
            )

    def _format_assertions_for_judge(self, assertion_results: list[AssertionResult]) -> str:
        """Format assertion results for the judge prompt."""
        lines = []
        for r in assertion_results:
            status = "PASS" if r.passed else "FAIL"
            lines.append(f"- [{status}] {r.assertion.name} (type={r.assertion.type}, weight={r.assertion.weight}): {r.reason}")
        return "\n".join(lines) if lines else "(no assertions)"
