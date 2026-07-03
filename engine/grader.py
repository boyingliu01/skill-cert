"""Grading module for skill-cert engine — evaluates model outputs against eval assertions."""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, ValidationError, model_validator


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


ASSERTION_STRATEGY_VALUES = frozenset({"deterministic", "llm_judge", "mixed"})


class EvalCase(BaseModel):
    """Single evaluation test case."""

    id: int
    name: str
    category: str  # normal, boundary, failure, trigger
    prompt: str
    expected_output: str | None = None
    files: list[str] = Field(default_factory=list)
    assertions: list[EvalAssertion]
    without_skill_assertions: list[EvalAssertion] = Field(default_factory=list)
    workflow_step: str | None = None  # Name of the workflow step this case targets
    negative_case: bool = False  # If True, expect NOT to trigger (v0.4.0, Issue #44)
    confusion_prompt: str | None = None  # Near-miss prompt for boundary testing (Issue #44)
    # REQ-1: assertion evaluation strategy — per-eval-case routing
    assertion_strategy: str = "deterministic"  # deterministic | llm_judge | mixed
    judge_dimensions: list[str] | None = None  # trigger_accuracy | workflow_quality

    @model_validator(mode="after")
    def _validate_assertions_not_all_empty(self):
        if not self.assertions and not self.without_skill_assertions:
            raise ValueError(
                "At least one of 'assertions' or 'without_skill_assertions' must be non-empty"
            )
        return self

    @model_validator(mode="after")
    def _validate_assertion_strategy(self):
        if self.assertion_strategy not in ASSERTION_STRATEGY_VALUES:
            raise ValueError(
                f"assertion_strategy must be one of {sorted(ASSERTION_STRATEGY_VALUES)}, "
                f"got '{self.assertion_strategy}'"
            )
        return self


@dataclass
class AssertionResult:
    """Result of a single assertion evaluation."""

    assertion: EvalAssertion
    passed: bool
    confidence: float
    reason: str


class Grader:
    """Evaluates model outputs against eval assertions."""

    def __init__(self, llm_client: Any = None, debias_position: bool = True):
        """Initialize grader with optional LLM client for judge mode."""
        self.llm_client = llm_client
        self.debias_position = debias_position

    def grade_output(
        self, eval_case: EvalCase, model_output: str, *, mode: str = "with_skill"
    ) -> dict[str, Any]:
        if mode == "without_skill" and eval_case.without_skill_assertions:
            assertions = eval_case.without_skill_assertions
        else:
            assertions = eval_case.assertions

        strategy = getattr(eval_case, "assertion_strategy", None) or "deterministic"

        if strategy == "deterministic":
            return self._grade_deterministic(eval_case, model_output, assertions)
        elif strategy == "llm_judge":
            return self._grade_llm_judge(eval_case, model_output, assertions)
        elif strategy == "mixed":
            det_result = self._grade_deterministic(eval_case, model_output, assertions)
            if det_result["pass_rate"] >= 0.5 and self.llm_client:
                det_results = [
                    AssertionResult(
                        assertion=a, passed=True, confidence=1.0, reason="pass"
                    )
                    for a in assertions
                ]
                judge = self._llm_judge(eval_case, model_output, det_results)
                det_result["judge_result"] = judge.model_dump() if judge else None
            return det_result
        else:
            return self._grade_deterministic(eval_case, model_output, assertions)

    def _grade_deterministic(
        self, eval_case: EvalCase, model_output: str, assertions: list[EvalAssertion]
    ) -> dict[str, Any]:
        results, total_weighted_score, total_possible_score = self._evaluate_assertions(
            assertions, model_output
        )
        pass_rate = total_weighted_score / total_possible_score if total_possible_score > 0 else 0.0
        judge_result = None
        if eval_case.negative_case and pass_rate < 0.5 and self.llm_client:
            judge_result = self._llm_judge(eval_case, model_output, results)
        return self._build_grade_result(
            eval_case, model_output, results,
            total_weighted_score, total_possible_score, pass_rate, judge_result,
        )

    def _grade_llm_judge(
        self, eval_case: EvalCase, model_output: str, assertions: list[EvalAssertion]
    ) -> dict[str, Any]:
        results, total_weighted_score, total_possible_score = self._evaluate_assertions(
            assertions, model_output
        )
        pass_rate = total_weighted_score / total_possible_score if total_possible_score > 0 else 0.0
        judge_result = None
        if self.llm_client:
            judge_result = self._llm_judge(eval_case, model_output, results)
        return self._build_grade_result(
            eval_case, model_output, results,
            total_weighted_score, total_possible_score, pass_rate, judge_result,
        )

    def _evaluate_assertions(
        self,
        assertions: list[EvalAssertion],
        model_output: str,
    ) -> tuple[list[AssertionResult], int, int]:
        """Evaluate a list of assertions against model output."""
        results = []
        total_weighted_score = 0
        total_possible_score = 0

        for assertion in assertions:
            result = self._evaluate_assertion(assertion, model_output)
            results.append(result)

            weight_multiplier = self._get_weight_multiplier(assertion.weight)
            if result.passed:
                total_weighted_score += weight_multiplier
            total_possible_score += weight_multiplier

        return results, total_weighted_score, total_possible_score

    def _evaluate_all_assertions(
        self,
        eval_case: EvalCase,
        model_output: str,
    ) -> tuple[list[AssertionResult], int, int]:
        """Backward-compatible wrapper — delegates to _evaluate_assertions."""
        return self._evaluate_assertions(eval_case.assertions, model_output)

    def _build_grade_result(
        self,
        eval_case: EvalCase,
        model_output: str,
        results: list[AssertionResult],
        total_weighted_score: int,
        total_possible_score: int,
        pass_rate: float,
        judge_result: JudgeResult | None,
    ) -> dict[str, Any]:
        """Build the final grade result dictionary."""
        # For negative cases, final_passed means the model correctly did NOT trigger.
        # The logic depends on assertion types:
        # - With positive assertions (contains, regex, starts_with, json_valid):
        #   low pass_rate = correct (skill didn't produce expected patterns)
        # - With negative assertions (not_contains):
        #   high pass_rate = correct (skill avoided the patterns it should)
        if eval_case.negative_case:
            if judge_result and judge_result.confidence >= 0.8:
                final_passed = not judge_result.passed
            else:
                # Check if assertions are predominantly not_contains vs positive
                neg_assertion_types = {"not_contains"}
                has_any_pos = any(r.assertion.type not in neg_assertion_types for r in results)
                has_any_neg = any(r.assertion.type in neg_assertion_types for r in results)

                if has_any_neg and not has_any_pos:
                    # Pure not_contains assertions: high pass_rate = good (avoided patterns)
                    final_passed = pass_rate >= 0.5
                else:
                    # Positive assertions (or mixed): low pass_rate = correct (didn't trigger)
                    final_passed = pass_rate < 0.5
        else:
            final_passed = (
                judge_result.passed
                if judge_result and judge_result.confidence >= 0.8
                else pass_rate >= 0.5
            )
        return {
            "eval_id": eval_case.id,
            "eval_name": eval_case.name,
            "category": eval_case.category,
            "workflow_step": eval_case.workflow_step,
            "negative_case": eval_case.negative_case,
            "model_output": model_output,
            "assertion_results": [
                {
                    "assertion": result.assertion.model_dump(),
                    "passed": result.passed,
                    "confidence": result.confidence,
                    "reason": result.reason,
                }
                for result in results
            ],
            "total_weighted_score": total_weighted_score,
            "total_possible_score": total_possible_score,
            "pass_rate": pass_rate,
            "judge_result": judge_result.model_dump() if judge_result else None,
            "final_passed": final_passed,
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
                reason = (
                    f"Regex '{assertion.value}' {'matched' if passed else 'did not match'} output"
                )
            except re.error:
                passed = False
                confidence = 0.0
                reason = f"Invalid regex pattern: {assertion.value}"
        elif assertion.type == "starts_with":
            passed = model_output.startswith(assertion.value)
            confidence = 1.0
            reason = (
                f"Output {'starts with' if passed else 'does not start with'} '{assertion.value}'"
            )
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
            assertion=assertion, passed=passed, confidence=confidence, reason=reason
        )

    def _get_weight_multiplier(self, weight: int) -> int:
        """Convert weight to multiplier: 1=Normal=1, 2=Important=2, 3=Critical=3."""
        return max(1, min(3, weight))  # Clamp between 1 and 3

    @staticmethod
    def _clamp_confidence(value: Any) -> float:
        """Clamp confidence to [0.0, 1.0]."""
        return max(0.0, min(1.0, float(value)))

    def _llm_judge(
        self, eval_case: EvalCase, model_output: str, assertion_results: list[AssertionResult]
    ) -> JudgeResult | None:
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
        llm_judge_enabled = (
            os.environ.get("SKILL_CERT_LLM_JUDGE_ENABLED", "true").lower() != "false"
        )

        # Fallback to simplified logic if LLM client is None or LLM judge is disabled
        if self.llm_client is None or not llm_judge_enabled:
            return self._llm_judge_fallback(assertion_results)

        return self._llm_judge_with_call(eval_case, model_output, assertion_results)

    def _llm_judge_fallback(self, assertion_results: list[AssertionResult]) -> JudgeResult:
        """Fallback logic when LLM judge is disabled or unavailable."""
        passed_assertions = sum(1 for r in assertion_results if r.passed)
        total_assertions = len(assertion_results)
        passed_ratio = passed_assertions / total_assertions
        return JudgeResult(
            passed=passed_ratio >= 0.5,
            confidence=passed_ratio,
            reasoning=(
                f"LLM evaluation: "
                f"{passed_assertions}/{total_assertions} "
                f"assertions passed ({passed_ratio:.2f})"
            ),
            judge_version="1.0",
            judge_model="",
        )

    def _llm_judge_with_call(
        self,
        eval_case: EvalCase,
        model_output: str,
        assertion_results: list[AssertionResult],
    ) -> JudgeResult:
        """Execute LLM judge with API call.

        Main judge and debias swap calls are issued in parallel via ThreadPoolExecutor,
        reducing latency from 2x serial to ~1x for the pair.
        """
        expected_behavior = eval_case.expected_output or eval_case.prompt

        with ThreadPoolExecutor(max_workers=2) as executor:
            main_future = executor.submit(
                self._execute_judge_main, eval_case, model_output, assertion_results
            )
            swap_future = None
            if self.debias_position and self.llm_client:
                swap_future = executor.submit(
                    self._execute_debias_swap, expected_behavior, model_output
                )

            try:
                result = main_future.result()
            except ValidationError as e:
                return self._handle_validation_error(e, assertion_results)
            except Exception as e:
                return self._llm_judge_error_fallback(assertion_results, e)

            if swap_future is not None:
                swap_result = swap_future.result()
                result = self._merge_debias_result(result, swap_result)

            return result

    def _retry_llm_judge_strict(
        self,
        eval_case: EvalCase,
        model_output: str,
        assertion_results: list[AssertionResult],
    ) -> JudgeResult:
        """Retry LLM judge with stricter JSON-only prompt."""
        expected_behavior = eval_case.expected_output or eval_case.prompt
        prompt = self._build_judge_prompt(
            eval_case, model_output, assertion_results, expected_behavior
        )
        prompt += "\n\nIMPORTANT: Respond ONLY with valid JSON. No markdown, no explanation."
        response_text = self.llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            timeout=30,
        )
        response_text = self._parse_judge_response(response_text)
        judge_data = json.loads(response_text)
        if isinstance(judge_data, str):
            judge_data = json.loads(judge_data)
        if not isinstance(judge_data, dict):
            raise ValueError(f"Expected dict from judge response, got {type(judge_data).__name__}")
        failure_reasons = judge_data.get("failure_reasons", [])
        if not isinstance(failure_reasons, list):
            failure_reasons = []
        return JudgeResult(
            passed=bool(judge_data.get("passed", False)),
            confidence=self._clamp_confidence(judge_data.get("confidence", 0.5)),
            reasoning=str(judge_data.get("reasoning", "")),
            failure_reasons=failure_reasons,
            judge_version="2.0",
            judge_model="llm",
        )

    def _handle_validation_error(
        self,
        error: ValidationError,
        assertion_results: list[AssertionResult],
    ) -> JudgeResult:
        """Handle Pydantic ValidationError — clamp confidence and reconstruct."""
        raw_confidence = 0.5
        for err in error.errors():
            if err.get("loc") == ("confidence",):
                raw_input = err.get("input")
                if raw_input is not None:
                    try:
                        raw_confidence = float(raw_input)
                    except (TypeError, ValueError):
                        raw_confidence = 0.5
        return JudgeResult(
            passed=False,
            confidence=self._clamp_confidence(raw_confidence),
            reasoning=f"Validation error recovered: {error}",
            judge_version="2.0",
            judge_model="llm",
        )

    def _execute_llm_judge(
        self,
        eval_case: EvalCase,
        model_output: str,
        assertion_results: list[AssertionResult],
    ) -> JudgeResult:
        """Execute the main LLM judge call."""
        expected_behavior = eval_case.expected_output or eval_case.prompt
        prompt = self._build_judge_prompt(
            eval_case,
            model_output,
            assertion_results,
            expected_behavior,
        )

        # Call LLM with judge prompt — temperature=0 for deterministic results
        response_text = self.llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            timeout=30,
        )

        # Parse JSON response — handle possible Markdown code block wrapping
        response_text = self._parse_judge_response(response_text)
        judge_data = json.loads(response_text)

        # Handle double-encoded JSON (LLM returns string instead of dict)
        if isinstance(judge_data, str):
            judge_data = json.loads(judge_data)
        if not isinstance(judge_data, dict):
            raise ValueError(f"Expected dict from judge response, got {type(judge_data).__name__}")

        failure_reasons = judge_data.get("failure_reasons", [])
        if not isinstance(failure_reasons, list):
            failure_reasons = []

        return JudgeResult(
            passed=bool(judge_data.get("passed", False)),
            confidence=self._clamp_confidence(judge_data.get("confidence", 0.5)),
            reasoning=str(judge_data.get("reasoning", "")),
            failure_reasons=failure_reasons,
            judge_version="2.0",
            judge_model="llm",
        )

    @staticmethod
    def _load_judge_template(dimension: str) -> str:
        try:
            from pathlib import Path

            prompts_dir = Path(__file__).parent.parent / "prompts"
            template_map = {
                "trigger_accuracy": "judge-trigger.md",
                "workflow_quality": "judge-workflow.md",
                "output_quality": "judge-output.md",
            }
            filename = template_map.get(dimension, "judge.md")
            template_path = prompts_dir / filename
            if template_path.exists():
                return template_path.read_text(encoding="utf-8")
        except Exception:
            pass
        return ""

    def _build_judge_prompt(
        self,
        eval_case: EvalCase,
        model_output: str,
        assertion_results: list[AssertionResult],
        expected_behavior: str,
    ) -> str:
        sanitized_output = model_output.replace("```", "'''")
        dimensions = getattr(eval_case, "judge_dimensions", None) or []
        primary_dim = dimensions[0] if dimensions else ""
        template = self._load_judge_template(primary_dim) if primary_dim else ""

        if template:
            workflow_steps = getattr(eval_case, "workflow_step", "") or ""
            prompt_text = (
                template
                .replace("{input}", str(expected_behavior))
                .replace("{output}", sanitized_output)
                .replace("{workflow_steps}", workflow_steps)
            )
        else:
            prompt_text = f"""# LLM-as-Judge Prompt

你是一个严格的评测裁判。评估以下模型输出是否满足指定的行为要求。

## 断言列表

{self._format_assertions_for_judge(assertion_results)}

## 评测任务

**Skill 输出**:
```
{sanitized_output}
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
        return prompt_text

    def _parse_judge_response(self, response_text: str) -> str:
        """Parse JSON response — handle possible Markdown code block wrapping."""
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

        if self._is_valid_json(response_text):
            return response_text

        extracted = self._extract_json_by_braces(response_text)
        if extracted is not None:
            return extracted

        cleaned = self._repair_json_trailing_commas(response_text)
        if cleaned is not None:
            return cleaned

        try:
            parsed = json.loads(response_text, strict=False)
            return json.dumps(parsed)
        except (json.JSONDecodeError, ValueError):
            pass

        cleaned = self._repair_json_trailing_commas(response_text)
        if cleaned is not None:
            return cleaned

        return response_text

    @staticmethod
    def _is_valid_json(text: str) -> bool:
        """Check if text is valid JSON."""
        try:
            json.loads(text)
            return True
        except (json.JSONDecodeError, ValueError):
            return False

    @staticmethod
    def _extract_json_by_braces(text: str) -> str | None:
        """Find outermost {..} via brace counting."""
        start = text.find("{")
        if start == -1:
            return None
        depth = 0
        in_string = False
        escape_next = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape_next:
                escape_next = False
                continue
            if ch == "\\" and in_string:
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        json.loads(candidate)
                        return candidate
                    except (json.JSONDecodeError, ValueError):
                        repaired = Grader._repair_json_trailing_commas(candidate)
                        if repaired is not None:
                            return repaired
                        return None
        return None

    @staticmethod
    def _repair_json_trailing_commas(text: str) -> str | None:
        """Remove trailing commas before closing braces/brackets (common LLM mistake)."""
        try:
            repaired = re.sub(r",(\s*[}\]])", r"\1", text)
            json.loads(repaired)
            return repaired
        except (json.JSONDecodeError, ValueError):
            return None

    def _llm_judge_error_fallback(
        self,
        assertion_results: list[AssertionResult],
        error: Exception,
    ) -> JudgeResult:
        """Fallback logic when LLM judge call fails."""
        passed_assertions = sum(1 for r in assertion_results if r.passed)
        total_assertions = len(assertion_results)
        passed_ratio = passed_assertions / total_assertions if total_assertions > 0 else 0.0
        return JudgeResult(
            passed=passed_ratio >= 0.5,
            confidence=passed_ratio,
            reasoning=(
                f"LLM judge call failed ({error}), "
                f"fallback to assertion-based: "
                f"{passed_assertions}/{total_assertions} "
                f"passed ({passed_ratio:.2f})"
            ),
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
            swap_text = self._parse_judge_response(swap_text)
            swap_data = json.loads(swap_text)
            # Handle double-encoded JSON
            if isinstance(swap_data, str):
                swap_data = json.loads(swap_data)
            if not isinstance(swap_data, dict):
                raise ValueError(
                    f"Expected dict from swap response, got {type(swap_data).__name__}"
                )
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

    def _execute_judge_main(
        self,
        eval_case: EvalCase,
        model_output: str,
        assertion_results: list[AssertionResult],
    ) -> JudgeResult:
        try:
            return self._execute_llm_judge(eval_case, model_output, assertion_results)
        except ValidationError:
            raise
        except json.JSONDecodeError:
            try:
                return self._retry_llm_judge_strict(eval_case, model_output, assertion_results)
            except Exception as retry_err:
                return self._llm_judge_error_fallback(assertion_results, retry_err)

    def _execute_debias_swap(
        self, expected_behavior: str, model_output: str
    ) -> dict[str, Any]:
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
        swap_text = self.llm_client.chat(
            messages=[{"role": "user", "content": swap_prompt}], timeout=30
        )
        swap_text = self._parse_judge_response(swap_text)
        swap_data = json.loads(swap_text)
        if isinstance(swap_data, str):
            swap_data = json.loads(swap_data)
        if not isinstance(swap_data, dict):
            raise ValueError(
                f"Expected dict from swap response, got {type(swap_data).__name__}"
            )
        return {
            "passed": bool(swap_data.get("passed", False)),
            "confidence": self._clamp_confidence(float(swap_data.get("confidence", 0.5))),
        }

    def _merge_debias_result(
        self, first_result: JudgeResult, swap_result: dict[str, Any]
    ) -> JudgeResult:
        swap_passed = swap_result["passed"]
        swap_confidence = float(swap_result["confidence"])

        if swap_passed != first_result.passed:
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

    def _format_assertions_for_judge(self, assertion_results: list[AssertionResult]) -> str:
        """Format assertion results for the judge prompt."""
        lines = []
        for r in assertion_results:
            status = "PASS" if r.passed else "FAIL"
            lines.append(
                f"- [{status}] {r.assertion.name} "
                f"(type={r.assertion.type}, weight={r.assertion.weight}): {r.reason}"
            )
        return "\n".join(lines) if lines else "(no assertions)"
