import json
import logging
import re
from enum import Enum
from pathlib import Path
from typing import Any

from engine.classifier import classify_output_type
from engine.constants import CoverageThresholds, TestGenLimits
from engine.deadline import PhaseTimer

logger = logging.getLogger(__name__)


class CoverageResult(Enum):
    """Result of coverage check — used for fail-fast decisions."""

    PASS = "PASS"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class EvalGenerator:
    CoverageResult = CoverageResult

    def __init__(self):
        self.max_rounds = TestGenLimits.MAX_REVIEW_ROUNDS
        self.consecutive_no_improvement = TestGenLimits.MAX_NO_IMPROVEMENT
        self.coverage_threshold = CoverageThresholds.COVERAGE_TARGET
        self.degrade_threshold = CoverageThresholds.COVERAGE_DEGRADE
        self.block_threshold = CoverageThresholds.COVERAGE_BLOCK

        try:
            template_path = Path(__file__).parent.parent / "templates" / "minimum-evals.json"
            if template_path.exists():
                with open(template_path, encoding="utf-8") as f:
                    self.minimum_evals_template = json.load(f)
            else:
                self.minimum_evals_template = {
                    "eval_cases": [
                        {
                            "id": 1,
                            "name": "basic-trigger-test",
                            "category": "trigger",
                            "input": "Please review this skill",
                            "expected_triggers": True,
                            "assertions": [{"type": "contains", "value": "review", "weight": 1}],
                        },
                        {
                            "id": 2,
                            "name": "should-not-trigger-test",
                            "category": "trigger",
                            "input": "Hello world",
                            "expected_triggers": False,
                            "assertions": [
                                {"type": "not_contains", "value": "review", "weight": 1}
                            ],
                        },
                        {
                            "id": 3,
                            "name": "normal-operation-test",
                            "category": "normal",
                            "input": "Execute the skill with sample input",
                            "expected_triggers": True,
                            "assertions": [{"type": "contains", "value": "skill", "weight": 1}],
                        },
                    ]
                }
        except Exception as e:
            logger.warning(f"Failed to load minimum evals template: {e}")
            self.minimum_evals_template = {
                "eval_cases": [
                    {
                        "id": 1,
                        "name": "fallback-basic-test",
                        "category": "normal",
                        "input": "Execute the skill",
                        "expected_triggers": True,
                        "assertions": [{"type": "contains", "value": "skill", "weight": 1}],
                    }
                ]
            }

    @staticmethod
    def check_coverage_or_abort(coverage: float) -> Any:
        """Classify coverage into PASS / DEGRADED / BLOCKED / FAILED."""
        if coverage >= CoverageThresholds.COVERAGE_TARGET:
            return CoverageResult.PASS
        if coverage >= CoverageThresholds.COVERAGE_DEGRADE:
            return CoverageResult.DEGRADED
        if coverage >= CoverageThresholds.COVERAGE_BLOCK:
            return CoverageResult.BLOCKED
        return CoverageResult.FAILED

    def generate_initial_evals(self, skill_spec: dict[str, Any], model_adapter) -> dict[str, Any]:
        try:
            prompt = self._prepare_generation_prompt(skill_spec)
            response = model_adapter.chat([{"role": "user", "content": prompt}])

            parsed = self._extract_json(response)
            if parsed is not None:
                evals = self._parse_evals_response(response)
                if self._has_sufficient_evals(evals):
                    return evals

            # Retry up to 3 times with progressively stronger hints
            retry_hints = [
                "Respond ONLY with a JSON object. No prose.",
                (
                    "Your last response was not valid JSON. "
                    "Output ONLY valid JSON with correct syntax. No trailing commas."
                ),
                "Still invalid. Return the MINIMAL JSON object with only the eval_cases array.",
            ]
            for attempt in range(min(3, len(retry_hints))):
                logger.warning(
                    "Failed to parse JSON from model response, retrying (attempt %d/%d)",
                    attempt + 1,
                    3,
                )
                retry_messages = [
                    {"role": "system", "content": retry_hints[attempt]},
                    {"role": "user", "content": prompt},
                ]
                response = model_adapter.chat(retry_messages)
                parsed = self._extract_json(response)
                if parsed is not None:
                    evals = self._parse_evals_response(response)
                    if self._has_sufficient_evals(evals):
                        return evals

            # All retries exhausted — fall back to template
            evals = self._parse_evals_response(response)
            if self._has_sufficient_evals(evals):
                return evals

            logger.warning("Generated evals below minimum requirement, using template")
            return self.minimum_evals_template
        except Exception as e:
            logger.error(f"Failed to generate initial evals: {e}")
            return self.minimum_evals_template

    def review_evals(self, evals: dict[str, Any], review_adapter) -> dict[str, Any]:
        try:
            coverage = self._calculate_coverage(evals, review_adapter.skill_spec)
            prompt = self._prepare_review_prompt(evals, review_adapter.skill_spec, coverage)
            response = review_adapter.chat(
                [{"role": "user", "content": prompt}],
                timeout=TestGenLimits.GAP_FILL_TIMEOUT,
            )
            gaps = self._parse_review_response(response, coverage)
            return gaps
        except Exception as e:
            logger.error(f"Failed to review evals: {e}")
            return {"coverage": 0.0, "gaps": ["Failed to review evals"], "needs_improvement": True}

    def fill_gaps(
        self,
        gaps: dict[str, Any],
        skill_spec: dict[str, Any],
        model_adapter,
        timeout: int | None = None,
        max_retries: int = 1,
    ) -> dict[str, Any]:
        _timeout = timeout or TestGenLimits.GAP_FILL_TIMEOUT
        for attempt in range(max_retries + 1):
            try:
                prompt = self._prepare_gap_filling_prompt(gaps, skill_spec)
                kwargs = [{"role": "user", "content": prompt}]
                response = model_adapter.chat(kwargs, timeout=_timeout)
                supplementary_evals = self._parse_evals_response(response)
                return supplementary_evals
            except Exception as e:
                if attempt < max_retries:
                    logger.warning(
                        f"Gap-fill attempt {attempt + 1}/{max_retries + 1}"
                        f" failed ({e}), retrying..."
                    )
                else:
                    logger.error(f"Failed to fill gaps after {max_retries + 1} attempts: {e}")
        return {"eval_cases": []}

    def generate_evals_with_convergence(
        self,
        skill_spec: dict[str, Any],
        model_adapter,
        review_adapter,
        deadline: Any | None = None,
    ) -> dict[str, Any]:
        review_adapter.skill_spec = skill_spec

        timer = PhaseTimer(phase_name="testgen", item_count=self.max_rounds, deadline=deadline)

        current_evals = self.generate_initial_evals(skill_spec, model_adapter)

        prev_coverage = 0.0
        round_num = 0
        current_coverage: float = 0.0

        while round_num < self.max_rounds:
            if deadline is not None and deadline.expired:
                result = self._finalize_evals_result(current_evals, current_coverage)
                result["failed"] = True
                return result

            should_stop, current_evals, current_coverage = self._run_convergence_round(
                current_evals, review_adapter, prev_coverage, round_num, deadline=deadline
            )

            timer.items_completed = round_num + 1
            timer.log_progress(f"round {round_num + 1}, coverage: {current_coverage:.0%}")

            if should_stop:
                break
            prev_coverage = current_coverage
            round_num += 1

        return self._apply_classifier_routing(
            self._finalize_evals_result(current_evals, current_coverage),
            skill_spec,
        )

    def _apply_classifier_routing(
        self, evals: dict[str, Any], skill_spec: dict[str, Any]
    ) -> dict[str, Any]:
        """Apply classifier-based assertion strategy routing to evals.

        For natural_language skills: override assertion_strategy='llm_judge' on all evals.
        For structured skills: leave assertion_strategy unchanged.
        """
        classification = classify_output_type(skill_spec)

        if classification.strategy != "natural_language":
            logger.info(
                "Classifier: structured skill (confidence=%.2f), no routing override",
                classification.confidence,
            )
            return evals

        logger.info(
            "Classifier: natural_language skill (confidence=%.2f, signals=%s), "
            "setting assertion_strategy=llm_judge on all evals",
            classification.confidence,
            classification.signals,
        )

        eval_cases = self._get_eval_cases(evals)
        for case in eval_cases:
            case["assertion_strategy"] = "llm_judge"
            case["judge_dimensions"] = ["output_quality", "trigger_accuracy", "workflow_quality"]

        return evals

    def _run_convergence_round(
        self,
        current_evals: dict[str, Any],
        review_adapter,
        prev_coverage: float,
        round_num: int,
        deadline: Any | None = None,
    ) -> tuple[bool, dict[str, Any], float]:
        """Run one convergence round. Returns (should_stop, updated_evals, current_coverage)."""
        review_result = self.review_evals(current_evals, review_adapter)
        current_coverage = review_result.get("coverage", 0.0)

        logger.info(f"Round {round_num + 1}: Coverage = {current_coverage:.2f}")

        if current_coverage >= self.coverage_threshold:
            logger.info(
                f"Coverage target ({self.coverage_threshold}) reached at round {round_num + 1}"
            )
            return True, current_evals, current_coverage

        no_improvement_count = (
            self.consecutive_no_improvement if current_coverage <= prev_coverage else 0
        )

        if no_improvement_count >= self.consecutive_no_improvement:
            logger.info(
                f"No improvement for {self.consecutive_no_improvement} consecutive rounds, stopping"
            )
            return True, current_evals, current_coverage

        if review_result.get("needs_improvement", False):
            if deadline is not None and deadline.must_stop():
                logger.info("Deadline approaching, skipping gap fill")
                return True, current_evals, current_coverage

            skill_spec = self._get_skill_spec_from_adapter(review_adapter)
            timeout = (
                deadline.adapter_timeout(default=TestGenLimits.GAP_FILL_TIMEOUT)
                if deadline
                else TestGenLimits.GAP_FILL_TIMEOUT
            )
            supplementary_evals = self.fill_gaps(
                review_result,
                skill_spec,
                review_adapter,
                timeout=timeout,
            )
            if self._has_sufficient_evals(supplementary_evals):
                current_evals = self._merge_evals(current_evals, supplementary_evals)

        return False, current_evals, current_coverage

    def _get_skill_spec_from_adapter(self, review_adapter) -> dict[str, Any]:
        """Extract skill_spec from review_adapter."""
        return getattr(review_adapter, "skill_spec", {})

    def _finalize_evals_result(
        self, current_evals: dict[str, Any], current_coverage: float
    ) -> dict[str, Any]:
        """Finalize evals generation and return result based on coverage."""
        result = self.check_coverage_or_abort(current_coverage)
        degraded = result in (
            CoverageResult.DEGRADED,
            CoverageResult.BLOCKED,
            CoverageResult.FAILED,
        )
        failed = result == CoverageResult.FAILED

        if current_coverage >= self.coverage_threshold:
            logger.info("Eval generation completed with sufficient coverage")
        elif current_coverage >= self.degrade_threshold:
            logger.warning(
                f"Eval generation completed with degraded coverage "
                f"({current_coverage}), below target but above degrade threshold"
            )
        elif (
            isinstance(current_evals, dict) and current_evals.get("eval_cases")
        ) or self._get_eval_cases(current_evals):
            logger.warning(
                f"Eval generation with degraded coverage ({current_coverage}), "
                "using generated evals"
            )
        else:
            logger.error(
                f"Eval generation failed with insufficient coverage "
                f"({current_coverage}), below block threshold"
            )
            current_evals = self.minimum_evals_template

        if isinstance(current_evals, dict):
            current_evals["degraded"] = degraded
            current_evals["failed"] = failed
        return current_evals

    def _prepare_generation_prompt(self, skill_spec: dict[str, Any]) -> str:
        skill_type = skill_spec.get("skill_type", "agent_guide")

        if skill_type == "cli_tool":
            return self._prepare_cli_tool_prompt(skill_spec)
        elif skill_type == "library":
            return self._prepare_library_prompt(skill_spec)
        else:
            return self._prepare_agent_guide_prompt(skill_spec)

    def _prepare_agent_guide_prompt(self, skill_spec: dict[str, Any]) -> str:
        workflow_steps = skill_spec.get("workflow_steps", [])
        anti_patterns = skill_spec.get("anti_patterns", [])
        output_format = skill_spec.get("output_format", [])

        workflow_step_hint = ""
        if workflow_steps:
            steps_list = "\n".join(f"  - {s}" for s in workflow_steps)
            n_steps = len(workflow_steps)
            workflow_step_hint = f"""
WORKFLOW STEP EVAL CASES (MANDATORY) — Generate exactly {n_steps}
eval cases with category="workflow_step", one per step listed below.
Use regex patterns (NOT single exact contains) that match multiple
possible phrasings.
Workflow steps to cover:
{steps_list}
For each workflow_step case, generate multi-candidate assertions:
  regex "(Determine mode|Design review|code.walkthrough|mode)"
  contains "[common section heading from expected output]"
  regex "structural pattern" (not single keyword)
DO NOT use single contains like "Mode:" — models paraphrase. Use regex alternatives that cover
synonyms, capitalization variants, and positional phrasing.
"""

        anti_pattern_hint = ""
        if anti_patterns:
            ap_list = "\n".join(f"  - {ap}" for ap in anti_patterns)
            anti_pattern_hint = f"""
ANTI-PATTERN EVAL CASES — Generate at least 2 boundary/failure cases that check the skill
avoids these anti-patterns:
{ap_list}
Use not_contains or regex assertions to verify the anti-pattern is NOT present.
"""

        output_format_hint = ""
        if output_format:
            of_list = "\n".join(f"  - {of}" for of in output_format)
            fmt_text = " ".join(str(f).lower() for f in output_format)
            has_structured = any(
                kw in fmt_text for kw in ("json", "code", "schema", "yaml", "toml")
            )
            if has_structured:
                output_format_hint = (
                    "OUTPUT FORMAT — The skill produces structured output."
                    " Verify format correctness:\n"
                    f"{of_list}\n"
                    "Use json_valid or regex assertions to validate structure.\n"
                )
            else:
                output_format_hint = (
                    "OUTPUT FORMAT — The skill produces free-form/natural language output:\n"
                    f"{of_list}\n"
                    "Use contains, regex, starts_with assertions to verify structural"
                    " sections, headings, or domain-specific content.\n"
                    "DO NOT use json_valid for free-form output.\n"
                )

        return f"""
Generate evaluation test cases for the following skill specification:

Skill Name: {skill_spec.get("name", "Unknown")}
Description: {skill_spec.get("description", "No description")}
Triggers: {skill_spec.get("triggers", [])}
Workflow Steps: {workflow_steps}
Anti-Patterns: {anti_patterns}
Output Format: {output_format}
Examples: {skill_spec.get("examples", [])}
{workflow_step_hint}
{anti_pattern_hint}
{output_format_hint}

Generate a JSON object with an array of eval_cases containing:
- id: integer
- name: string
- category: "normal", "boundary", "failure", "trigger", or "workflow_step"
- input: string (the input to test the skill with)
- expected_triggers: boolean (whether the skill should trigger)
- negative_case: boolean (true if skill should NOT trigger; defaults to false)
- workflow_step: string (name of the workflow step this case targets, if applicable)
- assertions: array of objects with type
    ("contains", "not_contains", "regex", "starts_with", "json_valid"),
    value, and weight
- without_skill_assertions: array of objects (SAME FORMAT as assertions) for
    grading WITHOUT_SKILL mode. When empty defaults to assertions.

OUTPUT FORMAT ADAPTATION — Choose assertion types based on the skill's actual output:
- If the skill produces Markdown/prose: use contains, regex, starts_with for
  section headings, structural patterns (e.g. "## ", "---", "Round 1", "Expert").
  DO NOT use json_valid for free-form text output.
- If the skill produces JSON/structured data: use json_valid + contains for key names.
- If the skill produces both: use mixed assertions covering both formats.

DIVERSITY REQUIREMENT — Each eval case MUST use at least 2 DIFFERENT assertion types.
Mix from: contains, not_contains, regex, json_valid, starts_with. Never use
only one type in a single case. This is strictly enforced by the scoring system.

COVERAGE LINKING REQUIREMENT (CRITICAL) — Each eval case MUST have at least ONE
assertion whose value DIRECTLY references a keyword from the skill's specification items
listed above. The coverage system uses substring matching to verify that eval assertions
cover the skill's workflow_steps, anti_patterns, and output_format fields.

HOW THE COVERAGE SYSTEM WORKS:
- For contains, not_contains, starts_with: the literal VALUE is checked against spec items.
  "Determine mode" → checks if "determine mode" is a substring of any spec item.
  This COVERS spec items but may NOT match actual model output if phrasing differs.
- For regex: alternation patterns like "(Design review|Determine mode|code-walkthrough)"
  are EXPANDED into branches: ["Design review", "Determine mode", "code-walkthrough"].
  EACH branch is checked against spec items. Use regex to cover MULTIPLE spec items at once.

DUAL-PURPOSE ASSERTION STRATEGY — Each eval case MUST use BOTH:
1. Regex assertions for SPEC COVERAGE: Include spec keywords in alternation patterns so
   coverage matches. Example for workflow_step "Determine mode":
   regex "(Determine mode|Design review|code-walkthrough|mode)"
2. Contains assertions for GRADING: Use values that match the ACTUAL OUTPUT phrasing the
   skill produces, not abstract spec field names.
   Example: if the skill outputs "**Mode:** Design Review", use:
   contains "Mode:" or contains "Design Review" — DO NOT use contains "Determine mode"
   because the literal phrase "Determine mode" does not appear in real output.

KEYWORD BLACKLIST — DO NOT use these patterns as the sole assertion value:
- DO NOT use contains "skill", contains "SKILL.md", or similar single-word skill-name checks
- DO NOT use assertions that only check for the word "skill" without context
- Instead, check for structural output patterns, workflow step names, or domain-specific content

For TRIGGER evals (category="trigger") — check for skill-specific markers:
- regex for COVERAGE: Include keywords from workflow_steps, anti_patterns, or output_format
  so coverage calculation matches. Example: regex "(Round 1|Expert|Consensus|Delphi)"
- contains for GRADING: Use actual phrases the skill outputs when triggered.
  Look at the skill's examples section for real output patterns.
  Example: contains "Delphi Consensus Review" or contains "Round 1".
- For negative triggers (should_not_trigger): use not_contains for skill-specific markers
  Example: not_contains "Round 1", not_contains "Expert"

For WORKFLOW_STEP evals (category="workflow_step") — verify step execution:
- regex "(spec_keyword_1|spec_keyword_2|actual_output_pattern)" for COVERAGE
  Include keywords from the workflow step spec item so coverage matches.
- contains "ACTUAL PHRASE FROM OUTPUT" for GRADING
  What exact section heading, phase label, or marker does the skill emit for this step?
  Use THAT phrase. DO NOT use the abstract step name if the skill uses different wording.
  Example: if step is "Determine mode" but output shows "**Mode:** Design Review",
  use regex "(Determine mode|Design review|mode)" and contains "Mode:".
- These cases MUST have assertion_strategy derived as "llm_judge"

For NORMAL evals — verify overall skill behavior:
- regex for COVERAGE: Include keywords from output_format and workflow_steps
  Example: regex "(verdict|consensus_report|expert_id|consensus)"
- contains for GRADING: Match actual output patterns the skill commonly produces
  Example: if the skill outputs a consensus verdict, use contains "Final Verdict:"
  If it produces expert IDs, use contains "Expert 1" or contains "Expert ID"

For WITHOUT_SKILL assertions (without_skill_assertions array):
- Use the SAME assertion types (regex, contains, starts_with, etc.) as the
  with_skill assertions array above. Do NOT use not_contains unless the
  corresponding with_skill assertion also uses not_contains.
- The without_skill assertions measure the SAME expectations — the skill should
  improve how many of these assertions pass, not change what is tested.
- Only add without_skill_assertions when truly different assertions are needed
  (e.g., a skill that should suppress a harmful pattern in output).
- IMPORTANT: At runtime, an empty or omitted without_skill_assertions
  automatically falls back to the regular assertions array. This is built-in
  behavior — omitting it is safe and preserves symmetric evaluation.
- For negative_case=True evals, omit without_skill_assertions (falls back to assertions)

Each eval case MUST have at least 2 assertions with at least 2 different types.
Use weights >= 2 for critical assertions.

Minimum requirements:
- At least 4 eval cases total
- At least 5 trigger cases (mix of should_trigger and should_not_trigger)
- At least 2 workflow_step cases (if skill has workflow_steps)
- Cover workflow steps, anti-patterns, and output formats mentioned in the spec
"""

    def _prepare_cli_tool_prompt(self, skill_spec: dict[str, Any]) -> str:
        return f"""
Generate evaluation test cases for the following CLI tool skill:

Skill Name: {skill_spec.get("name", "Unknown")}
Description: {skill_spec.get("description", "No description")}
Triggers: {skill_spec.get("triggers", [])}
Anti-Patterns: {skill_spec.get("anti_patterns", [])}
Output Format: {skill_spec.get("output_format", [])}
Examples: {skill_spec.get("examples", [])}

This is a CLI tool skill. Generate eval cases that test:
- Command-line flag parsing and validation (--flag, -f, --option value)
- Exit codes (0 for success, non-zero for errors)
- Standard output and standard error behavior
- Subcommand dispatch and argument handling
- Invalid input handling and error messages

Generate a JSON object with an array of eval_cases containing:
- id: integer
- name: string
- category: "normal", "boundary", "failure", or "trigger"
- input: string (the CLI command to test, e.g. "tool --flag value")
- expected_triggers: boolean
- negative_case: boolean
- assertions: array of objects with type
    ("contains", "not_contains", "regex", "starts_with"),
    value, and weight

IMPORTANT: Focus on CLI-specific assertions:
- Check exit code behavior (e.g., exit code 0 for success, non-zero for failure)
- Verify command-line flags produce expected output
- Test error messages for invalid flags or missing arguments
- Example: {{"type": "regex", "value": "(exit code|return code|non-zero|returned 0)", "weight": 3}}
- Example: {{"type": "contains", "value": "--help", "weight": 2}}
- Example: {{"type": "regex", "value": "(usage|Usage|USAGE)", "weight": 2}}

Each eval case MUST have at least 2 assertions.
Use weights >= 2 for critical assertions.

Minimum requirements:
- At least 4 eval cases total
- At least 3 CLI flag/option test cases
- At least 2 exit code / error handling test cases
"""

    def _prepare_library_prompt(self, skill_spec: dict[str, Any]) -> str:
        return f"""
Generate evaluation test cases for the following library/API skill:

Skill Name: {skill_spec.get("name", "Unknown")}
Description: {skill_spec.get("description", "No description")}
Triggers: {skill_spec.get("triggers", [])}
Anti-Patterns: {skill_spec.get("anti_patterns", [])}
Output Format: {skill_spec.get("output_format", [])}
Examples: {skill_spec.get("examples", [])}

This is a library/API skill. Generate eval cases that test:
- Function/method import and invocation
- API parameter validation and type checking
- Return value correctness
- Error handling and exception behavior
- Edge cases in function arguments

Generate a JSON object with an array of eval_cases containing:
- id: integer
- name: string
- category: "normal", "boundary", "failure", or "trigger"
- input: string (the function call or import to test)
- expected_triggers: boolean
- negative_case: boolean
- assertions: array of objects with type
    ("contains", "not_contains", "regex", "starts_with", "json_valid"),
    value, and weight

IMPORTANT: Focus on API-specific assertions:
- Check that import statements are correct
- Verify function signatures and parameter types
- Test return values and error handling
- Example: {{"type": "regex", "value": "(import|from.*import)", "weight": 2}}
- Example: {{"type": "contains", "value": "def ", "weight": 2}}
- Example: {{"type": "regex", "value": "(TypeError|ValueError|raises|Exception)", "weight": 2}}

Each eval case MUST have at least 2 assertions.
Use weights >= 2 for critical assertions.

Minimum requirements:
- At least 4 eval cases total
- At least 3 function/API test cases
- At least 2 error handling test cases
"""

    def _parse_evals_response(self, response: str) -> dict[str, Any]:
        parsed = self._extract_json(response)

        if parsed is None:
            logger.warning("Could not parse JSON from model response, using template")
            return self.minimum_evals_template

        if "eval_cases" not in parsed:
            for key in ["evals", "cases", "test_cases", "evaluations", "eval"]:
                if key in parsed and isinstance(parsed[key], list):
                    parsed["eval_cases"] = parsed[key]
                    break
            else:
                parsed["eval_cases"] = [
                    {
                        "id": 1,
                        "name": "fallback-case",
                        "category": "normal",
                        "input": "Execute the skill",
                        "expected_triggers": True,
                        "assertions": [{"type": "contains", "value": "skill", "weight": 1}],
                    }
                ]

        parsed["eval_cases"] = [
            self._normalize_eval_case(c, idx) for idx, c in enumerate(parsed["eval_cases"])
        ]

        return parsed

    @staticmethod
    @staticmethod
    def _repair_json_trailing_commas(text: str) -> str | None:
        """Remove trailing commas before closing braces/brackets (common LLM mistake)."""
        try:
            repaired = re.sub(r",(\s*[}\]])", r"\1", text)
            json.loads(repaired)
            return repaired
        except (json.JSONDecodeError, ValueError):
            return None

    @staticmethod
    def _extract_json(response: str) -> dict[str, Any] | None:
        """Extract JSON object from LLM response using 4-level fallback.

        Strategy 1: Strip markdown fences + repair trailing commas + json.loads
        Strategy 2: Balanced brace counting to find outermost {..} (with repair)
        Strategy 3: Largest-first — try all {..} blocks largest to smallest (with repair)
        Strategy 4: json.loads with strict=False on full response (with repair)
        """
        if not response or not response.strip():
            return None

        # Strategy 1: Strip markdown fences + json.loads (with trailing comma repair)
        try:
            cleaned = EvalGenerator._strip_markdown_fences(response)
            start_idx = cleaned.find("{")
            end_idx = cleaned.rfind("}") + 1
            if start_idx != -1 and end_idx > start_idx:
                candidate = cleaned[start_idx:end_idx]
                repaired = EvalGenerator._repair_json_trailing_commas(candidate)
                if repaired is not None:
                    parsed = json.loads(repaired)
                    if isinstance(parsed, dict):
                        return parsed
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
        except (json.JSONDecodeError, ValueError):
            pass

        # Strategy 2: Balanced brace extraction — find first valid outermost {..}
        result = EvalGenerator._balanced_brace_extract(response)
        if result is not None:
            return result

        # Strategy 3: Largest-first — find all {..} blocks, try largest first
        result = EvalGenerator._largest_first_extract(response)
        if result is not None:
            return result

        # Strategy 4: json.loads with strict=False on full response (with repair)
        try:
            repaired = EvalGenerator._repair_json_trailing_commas(response)
            if repaired is not None:
                parsed = json.loads(repaired, strict=False)
                if isinstance(parsed, dict):
                    return parsed
            parsed = json.loads(response, strict=False)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass

        # Also try strict=False on the first{..}last slice (with repair)
        try:
            start_idx = response.find("{")
            end_idx = response.rfind("}") + 1
            if start_idx != -1 and end_idx > start_idx:
                candidate = response[start_idx:end_idx]
                repaired = EvalGenerator._repair_json_trailing_commas(candidate)
                if repaired is not None:
                    parsed = json.loads(repaired, strict=False)
                    if isinstance(parsed, dict):
                        return parsed
                parsed = json.loads(candidate, strict=False)
                if isinstance(parsed, dict):
                    return parsed
        except (json.JSONDecodeError, ValueError):
            pass

        return None

    @staticmethod
    def _balanced_brace_extract(response: str) -> dict[str, Any] | None:
        """Strategy 2: Find first valid outermost {..} via balanced brace counting."""
        start = response.find("{")
        while start != -1:
            depth = 0
            in_string = False
            escape_next = False
            for i in range(start, len(response)):
                ch = response[i]
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
                        candidate = response[start : i + 1]
                        try:
                            parsed = json.loads(candidate)
                            if isinstance(parsed, dict):
                                return parsed
                        except (json.JSONDecodeError, ValueError):
                            pass
                        break
            start = response.find("{", start + 1)
        return None

    @staticmethod
    def _largest_first_extract(response: str) -> dict[str, Any] | None:
        """Strategy 3: Find all top-level {..} blocks, try largest to smallest."""
        blocks: list[tuple[int, int]] = []
        start = response.find("{")
        while start != -1:
            depth = 0
            in_string = False
            escape_next = False
            for i in range(start, len(response)):
                ch = response[i]
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
                        blocks.append((start, i + 1))
                        break
            start = response.find("{", start + 1)

        blocks.sort(key=lambda b: b[1] - b[0], reverse=True)
        for s, e in blocks:
            try:
                parsed = json.loads(response[s:e])
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, ValueError):
                continue
        return None

    @staticmethod
    def _strip_markdown_fences(text: str) -> str:
        """Strip markdown JSON fences and return clean JSON text."""
        lines = text.split("\n")
        fences = []
        in_fence = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```"):
                if in_fence:
                    in_fence = False
                elif stripped.startswith("```json") or stripped == "```":
                    in_fence = True
                continue
            if not in_fence or stripped:
                fences.append(line)
        return "\n".join(fences)

    @staticmethod
    def _normalize_eval_case(case: dict, idx: int) -> dict:
        """Normalize an eval case to ensure correct structure."""
        normalized = dict(case)

        # Ensure 'input' field (fallback from 'prompt')
        if not normalized.get("input"):
            normalized["input"] = normalized.get("prompt", "")

        # Ensure input/prompt is always a string, not dict/list
        for key in ("input", "prompt"):
            if key in normalized and not isinstance(normalized[key], str):
                if isinstance(normalized[key], (dict, list)):
                    normalized[key] = json.dumps(normalized[key])
                else:
                    normalized[key] = str(normalized[key])

        # Normalize flat assertion_type/assertion_value → assertions array
        if "assertions" not in normalized or not isinstance(normalized.get("assertions"), list):
            flat_type = normalized.pop("assertion_type", None)
            flat_value = normalized.pop("assertion_value", "")
            flat_weight = normalized.pop("assertion_weight", 1)
            if flat_type:
                normalized["assertions"] = [
                    {"type": flat_type, "value": str(flat_value), "weight": int(float(flat_weight))}
                ]
            else:
                normalized["assertions"] = []

        # Ensure assertions have proper structure
        clean_asserts = []
        for i, a in enumerate(normalized["assertions"]):
            if isinstance(a, dict):
                clean_asserts.append(
                    {
                        "type": a.get("type", "contains"),
                        "value": str(a.get("value", "")),
                        "weight": int(float(a.get("weight", 1))),
                    }
                )
        normalized["assertions"] = clean_asserts

        # Normalize without_skill_assertions with same structure as assertions
        if "without_skill_assertions" in normalized and isinstance(
            normalized["without_skill_assertions"], list
        ):
            clean_ws_asserts = []
            for a in normalized["without_skill_assertions"]:
                if isinstance(a, dict):
                    clean_ws_asserts.append(
                        {
                            "type": a.get("type", "contains"),
                            "value": str(a.get("value", "")),
                            "weight": int(float(a.get("weight", 1))),
                        }
                    )
            normalized["without_skill_assertions"] = clean_ws_asserts

        # Ensure required fields
        normalized.setdefault("id", idx + 1)
        normalized.setdefault("name", f"eval-{idx + 1}")
        normalized.setdefault("category", "normal")

        # Fallback: if both assertions and without_skill_assertions are empty, add a
        # minimal assertion to satisfy the model_validator on EvalCase.
        ws_asserts = normalized.get("without_skill_assertions", [])
        if not normalized["assertions"] and not ws_asserts:
            normalized["assertions"] = [{"type": "contains", "value": "skill", "weight": 1}]

        # Normalize negative_case from ALL plausible LLM variants
        # String-to-bool coercion before isinstance check
        for key in ("negative_case", "is_negative", "negative", "should_not"):
            if key in normalized and isinstance(normalized[key], str):
                normalized[key] = normalized[key].lower() in ("true", "1", "yes")

        if "is_negative" in normalized:
            normalized["negative_case"] = bool(normalized.pop("is_negative"))
        elif "negative" in normalized:
            normalized["negative_case"] = bool(normalized.pop("negative"))
        elif "should_not" in normalized:
            normalized["negative_case"] = bool(normalized.pop("should_not"))
        elif "triggers_on" in normalized:
            normalized["negative_case"] = not bool(normalized.pop("triggers_on"))
        elif "expected_triggers" in normalized:
            normalized["negative_case"] = not bool(normalized.pop("expected_triggers"))
        else:
            normalized.setdefault("negative_case", False)

        if "assertion_strategy" not in normalized or normalized["assertion_strategy"] is None:
            category = normalized.get("category", "normal")
            output_fields = normalized.get("output_format_fields", [])
            normalized["assertion_strategy"] = EvalGenerator._assign_strategy(
                category, output_fields
            )

        return normalized

    @staticmethod
    def _assign_strategy(category: str, output_format_fields: list[str]) -> str:
        if category == "workflow_step":
            return "llm_judge"
        if category == "trigger":
            # Trigger output may be structured (JSON, verdict) or free-form Markdown.
            # Use deterministic only when the skill declares structured output formats.
            fmt_text = " ".join(str(f).lower() for f in output_format_fields)
            has_structured = any(
                kw in fmt_text for kw in ("json", "code", "schema", "yaml", "toml")
            )
            return "deterministic" if has_structured else "mixed"
        if category in ("anti_pattern", "boundary"):
            return "mixed"
        if category == "output_format":
            fmt_text = " ".join(str(f).lower() for f in output_format_fields)
            has_structured = any(
                kw in fmt_text for kw in ("json", "code", "schema", "yaml", "toml")
            )
            return "deterministic" if has_structured else "llm_judge"
        return "deterministic"

    @staticmethod
    def _extract_regex_branches(value: str, _depth: int = 0) -> list[str]:
        """Extract individual branches from a regex alternation pattern.

        Handles patterns like (a|b|c), a|b|c, (a|(b|c)), and (a)|(b)|(c).
        Respects escaped parentheses and pipe during depth tracking.
        Recursively expands nested alternations (max depth 3).
        Filters out empty branches.
        Non-alternation values return [value] unchanged.
        """
        if _depth > 3:
            return [value]

        # Step 1: Detect if value contains any unescaped | at any depth
        has_pipe = False
        i = 0
        while i < len(value):
            if value[i] == "\\" and i + 1 < len(value):
                i += 2  # skip escape sequence
                continue
            if value[i] == "|":
                has_pipe = True
                break
            i += 1

        if not has_pipe:
            return [value]

        # Step 2: Strip outermost balanced parens if they wrap the entire expression
        inner = value
        if inner.startswith("(") and inner.endswith(")"):
            # Verify the parens are truly a matching outer pair
            depth = 0
            balanced = True
            for ch in inner[1:-1]:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                if depth < 0:
                    balanced = False
                    break
            if balanced and depth == 0:
                inner = inner[1:-1]

        # Step 3: Split on | at depth 0 (relative to inner), escape-aware
        branches: list[str] = []
        current: list[str] = []
        depth = 0
        i = 0
        while i < len(inner):
            ch = inner[i]
            if ch == "\\" and i + 1 < len(inner):
                current.append(ch)
                current.append(inner[i + 1])
                i += 2
                continue
            if ch == "(":
                depth += 1
                current.append(ch)
            elif ch == ")":
                depth -= 1
                current.append(ch)
            elif ch == "|" and depth == 0:
                branch = "".join(current).strip()
                if branch:
                    branches.append(branch)
                current = []
            else:
                current.append(ch)
            i += 1

        remaining = "".join(current).strip()
        if remaining:
            branches.append(remaining)

        # Step 4: Strip outer balanced parens from each branch
        stripped_branches: list[str] = []
        for b in branches:
            candidate = b
            if candidate.startswith("(") and candidate.endswith(")"):
                inner_depth = 0
                balanced = True
                for ch in candidate[1:-1]:
                    if ch == "(":
                        inner_depth += 1
                    elif ch == ")":
                        inner_depth -= 1
                    if inner_depth < 0:
                        balanced = False
                        break
                if balanced and inner_depth == 0:
                    candidate = candidate[1:-1]
            stripped_branches.append(candidate)

        # Step 5: Recursively expand each branch
        result: list[str] = []
        for b in stripped_branches:
            result.extend(EvalGenerator._extract_regex_branches(b, _depth + 1))

        # Step 6: Deduplicate preserving order (aligns with documented contract)
        if not result:
            return [value]
        seen: set[str] = set()
        deduped: list[str] = []
        for b in result:
            if b not in seen:
                seen.add(b)
                deduped.append(b)
        return deduped

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        """Split text into lowercased word tokens for overlap matching."""
        return set(re.findall(r"[a-zA-Z0-9]+", text.lower()))

    @staticmethod
    def _jaccard_overlap(a_tokens: set[str], b_tokens: set[str]) -> float:
        """Compute Jaccard similarity between two token sets."""
        if not a_tokens or not b_tokens:
            return 0.0
        intersection = a_tokens & b_tokens
        max_len = max(len(a_tokens), len(b_tokens))
        return len(intersection) / max_len if max_len > 0 else 0.0

    def _compute_section_coverage(self, section_items: list[Any], assertion_set: set[str]) -> float:
        """Compute coverage of a section (workflow, anti_patterns, output_format).

        Expands regex alternation patterns in assertion values before matching,
        so patterns like (Parse|Generate|Execute) are correctly matched against
        individual section items. Falls back to token-overlap matching
        (>=60% Jaccard similarity) when substring matching fails.
        """
        if not section_items:
            return 1.0  # No items to cover = automatic pass

        # Expand each assertion value into individual branches
        expanded: list[str] = []
        for a in assertion_set:
            expanded.extend(self._extract_regex_branches(a))
        # Filter empty strings: "" in "anything" is always True, inflating coverage
        expanded = [b for b in expanded if b]

        covered = 0
        for item in section_items:
            item_str = str(item) if not isinstance(item, str) else item
            item_lower = item_str.lower()
            item_tokens = self._tokenize(item_str)
            matched = False
            for b in expanded:
                b_lower = b.lower()
                if item_lower in b_lower or b_lower in item_lower:
                    matched = True
                    break
                b_tokens = self._tokenize(b)
                if self._jaccard_overlap(item_tokens, b_tokens) >= 0.6:
                    matched = True
                    break
            if matched:
                covered += 1
        return covered / len(section_items)

    def _has_sufficient_evals(self, evals: dict[str, Any]) -> bool:
        """Check if evals have sufficient cases."""
        eval_cases = evals.get("eval_cases", [])
        if not eval_cases:
            for key in [
                "evals",
                "cases",
                "test_cases",
                "evaluations",
                "eval",
            ]:
                if key in evals and isinstance(evals[key], list):
                    eval_cases = evals[key]
                    break

        # No eval cases = insufficient
        if not eval_cases:
            return False

        # Has eval cases = sufficient (assertions checked in _calculate_coverage)
        return True

    def _get_eval_cases(self, evals: dict[str, Any] | str) -> list[dict[str, Any]]:
        """Extract eval_cases from evals dict, checking multiple possible keys."""
        if not isinstance(evals, dict):
            return []
        eval_cases = evals.get("eval_cases", [])
        if not eval_cases:
            for key in [
                "evals",
                "cases",
                "test_cases",
                "evaluations",
                "eval",
            ]:
                if key in evals and isinstance(evals[key], list):
                    eval_cases = evals[key]
                    break
        return eval_cases

    # Keyword-only assertion values to penalize (case-insensitive)
    _KEYWORD_BLACKLIST: frozenset[str] = frozenset(
        {
            "skill",
            "SKILL",
            "SKILL.md",
            "skill.md",
            "skill_cert",
        }
    )

    def _calculate_coverage(self, evals: dict[str, Any], skill_spec: dict[str, Any]) -> float:
        eval_cases = self._get_eval_cases(evals)
        if not eval_cases:
            return 0.0

        assertion_set = {
            a.get("value", a.get("name", ""))
            for case in eval_cases
            for a in case.get("assertions", [])
        }
        # Filter out keyword-only assertions from coverage scoring
        filtered_assertions = {
            a for a in assertion_set if a.strip().lower() not in self._KEYWORD_BLACKLIST
        }
        # Count unique assertion types per eval case as a gentle quality signal.
        # Baseline 0.75 for single-type cases, ramps to 1.0 at 2+ types per case.
        type_counts = []
        for case in eval_cases:
            types_in_case = {a.get("type") for a in case.get("assertions", []) if a.get("type")}
            type_counts.append(len(types_in_case))
        avg_types = sum(type_counts) / max(len(type_counts), 1)
        type_diversity_factor = 0.5 + 0.5 * min(1.0, avg_types / 2.0)

        workflow_coverage = self._compute_section_coverage(
            skill_spec.get("workflow_steps", []), filtered_assertions
        )
        anti_pattern_coverage = self._compute_section_coverage(
            [str(p) for p in skill_spec.get("anti_patterns", [])], filtered_assertions
        )
        output_coverage = self._compute_section_coverage(
            skill_spec.get("output_format", []), filtered_assertions
        )

        base_score = workflow_coverage * 0.5 + anti_pattern_coverage * 0.3 + output_coverage * 0.2

        # Don't penalize when there's nothing to cover (empty spec = automatic 1.0 baseline)
        has_spec_items = bool(
            skill_spec.get("workflow_steps")
            or skill_spec.get("anti_patterns")
            or skill_spec.get("output_format")
        )
        if not has_spec_items:
            return base_score
        return base_score * type_diversity_factor

    def _prepare_review_prompt(
        self, evals: dict[str, Any], skill_spec: dict[str, Any], coverage: float
    ) -> str:
        return f"""
Review the following evaluation test cases for the skill:

Skill Spec: {json.dumps(skill_spec, indent=2)}
Current Evals: {json.dumps(evals, indent=2)}
Current Coverage: {coverage:.2f}

Analyze the eval cases and identify:
1. Which workflow steps are NOT covered by any eval case assertions
2. Which anti-patterns are NOT covered by any eval case assertions
3. Which output formats are NOT covered by any eval case assertions
4. Whether the eval cases are diverse enough (normal, boundary, failure, trigger)
5. Whether the assertions are meaningful and verifiable — flag any that only check for
   a single keyword (e.g. contains "skill") without structural context
6. Whether each eval case uses at least 2 different assertion types

Return a JSON object with:
- coverage: current coverage value
- gaps: array of strings describing uncovered areas
- needs_improvement: boolean indicating if more evals are needed
"""

    def _parse_review_response(self, response: str, current_coverage: float) -> dict[str, Any]:
        parsed = self._extract_json(response)

        if parsed is None:
            return {
                "coverage": current_coverage,
                "gaps": ["Could not parse review response"],
                "needs_improvement": True,
            }

        if "coverage" not in parsed:
            parsed["coverage"] = current_coverage
        if "gaps" not in parsed:
            parsed["gaps"] = []
        if "needs_improvement" not in parsed:
            parsed["needs_improvement"] = len(parsed["gaps"]) > 0

        return parsed

    def _prepare_gap_filling_prompt(self, gaps: dict[str, Any], skill_spec: dict[str, Any]) -> str:
        return f"""
Based on the identified gaps, generate additional evaluation test cases to improve coverage:

Skill Spec: {json.dumps(skill_spec, indent=2)}
Identified Gaps: {gaps.get("gaps", [])}
Current Coverage: {gaps.get("coverage", 0.0)}

Generate additional eval cases to address the gaps. Focus on:
- Workflow steps that are not covered
- Anti-patterns that are not tested
- Output formats that are not verified
- Boundary and failure cases if missing
- Trigger cases if not sufficient

Return a JSON object with an array of eval_cases in the same format as before.
"""

    def _merge_evals(
        self, current_evals: dict[str, Any], supplementary_evals: dict[str, Any]
    ) -> dict[str, Any]:
        # Create a copy of current evals
        merged = {}
        for key, value in current_evals.items():
            if isinstance(value, list):
                merged[key] = value[:]
            else:
                merged[key] = value

        # Find the eval_cases key in current evals
        current_eval_cases_key = self._find_eval_cases_key(merged)
        current_eval_cases = merged[current_eval_cases_key] if current_eval_cases_key else None

        # Find the eval_cases key in supplementary evals
        supplementary_eval_cases_key = self._find_eval_cases_key(supplementary_evals)
        supplementary_eval_cases = (
            supplementary_evals[supplementary_eval_cases_key]
            if supplementary_eval_cases_key
            else None
        )

        if current_eval_cases is not None and supplementary_eval_cases:
            # Assign new IDs to supplementary evals to avoid conflicts
            current_max_id = max([case.get("id", 0) for case in current_eval_cases], default=0)
            for i, case in enumerate(supplementary_eval_cases):
                case_copy = case.copy()
                case_copy["id"] = current_max_id + i + 1
                current_eval_cases.append(case_copy)

        return merged

    def _find_eval_cases_key(self, evals: dict[str, Any]) -> str | None:
        """Find the eval_cases key in evals dict. Returns key name or None."""
        for key in ["eval_cases", "evals", "cases", "test_cases", "evaluations", "eval"]:
            if key in evals and isinstance(evals[key], list):
                return key
        return None
