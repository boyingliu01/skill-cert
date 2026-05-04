import json
import logging
from typing import Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class EvalGenerator:
    def __init__(self):
        self.max_rounds = 3
        self.consecutive_no_improvement = 2
        self.coverage_threshold = 0.9
        self.degrade_threshold = 0.7
        self.block_threshold = 0.7
        
        try:
            template_path = Path(__file__).parent.parent / "templates" / "minimum-evals.json"
            if template_path.exists():
                with open(template_path, 'r', encoding='utf-8') as f:
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
                            "assertions": [
                                {"type": "contains", "value": "review", "weight": 1}
                            ]
                        },
                        {
                            "id": 2,
                            "name": "should-not-trigger-test",
                            "category": "trigger",
                            "input": "Hello world",
                            "expected_triggers": False,
                            "assertions": [
                                {"type": "not_contains", "value": "review", "weight": 1}
                            ]
                        },
                        {
                            "id": 3,
                            "name": "normal-operation-test",
                            "category": "normal",
                            "input": "Execute the skill with sample input",
                            "expected_triggers": True,
                            "assertions": [
                                {"type": "contains", "value": "skill", "weight": 1}
                            ]
                        }
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
                        "assertions": [
                            {"type": "contains", "value": "skill", "weight": 1}
                        ]
                    }
                ]
            }

    def generate_initial_evals(self, skill_spec: Dict[str, Any], model_adapter) -> Dict[str, Any]:
        try:
            prompt = self._prepare_generation_prompt(skill_spec)
            response = model_adapter.chat([
                {"role": "user", "content": prompt}
            ])
            evals = self._parse_evals_response(response)
            
            if not self._has_sufficient_evals(evals):
                logger.warning("Generated evals below minimum requirement, using template")
                return self.minimum_evals_template
            
            return evals
        except Exception as e:
            logger.error(f"Failed to generate initial evals: {e}")
            return self.minimum_evals_template

    def review_evals(self, evals: Dict[str, Any], review_adapter) -> Dict[str, Any]:
        try:
            coverage = self._calculate_coverage(evals, review_adapter.skill_spec)
            prompt = self._prepare_review_prompt(evals, review_adapter.skill_spec, coverage)
            response = review_adapter.chat([
                {"role": "user", "content": prompt}
            ])
            gaps = self._parse_review_response(response, coverage)
            return gaps
        except Exception as e:
            logger.error(f"Failed to review evals: {e}")
            return {
                "coverage": 0.0,
                "gaps": ["Failed to review evals"],
                "needs_improvement": True
            }

    def fill_gaps(self, gaps: Dict[str, Any], skill_spec: Dict[str, Any], model_adapter) -> Dict[str, Any]:
        try:
            prompt = self._prepare_gap_filling_prompt(gaps, skill_spec)
            response = model_adapter.chat([
                {"role": "user", "content": prompt}
            ])
            supplementary_evals = self._parse_evals_response(response)
            return supplementary_evals
        except Exception as e:
            logger.error(f"Failed to fill gaps: {e}")
            return {"eval_cases": []}

    def generate_evals_with_convergence(self, skill_spec: Dict[str, Any], model_adapter, review_adapter) -> Dict[str, Any]:
        review_adapter.skill_spec = skill_spec
        
        current_evals = self.generate_initial_evals(skill_spec, model_adapter)
        
        prev_coverage = 0.0
        no_improvement_count = 0
        round_num = 0
        
        while round_num < self.max_rounds:
            review_result = self.review_evals(current_evals, review_adapter)
            current_coverage = review_result.get("coverage", 0.0)
            
            logger.info(f"Round {round_num + 1}: Coverage = {current_coverage:.2f}")
            
            if current_coverage >= self.coverage_threshold:
                logger.info(f"Coverage target ({self.coverage_threshold}) reached at round {round_num + 1}")
                break
            
            if current_coverage <= prev_coverage:
                no_improvement_count += 1
            else:
                no_improvement_count = 0
                
            if no_improvement_count >= self.consecutive_no_improvement:
                logger.info(f"No improvement for {self.consecutive_no_improvement} consecutive rounds, stopping")
                break
            
            if review_result.get("needs_improvement", False):
                supplementary_evals = self.fill_gaps(review_result, skill_spec, model_adapter)
                
                if self._has_sufficient_evals(supplementary_evals):
                    current_evals = self._merge_evals(current_evals, supplementary_evals)
            
            prev_coverage = current_coverage
            round_num += 1
        
        if current_coverage >= self.coverage_threshold:
            logger.info("Eval generation completed with sufficient coverage")
            return current_evals
        elif current_coverage >= self.degrade_threshold:
            logger.warning(f"Eval generation completed with degraded coverage ({current_coverage}), below target but above degrade threshold")
            return current_evals
        elif current_evals.get("eval_cases") or self._get_eval_cases(current_evals):
            logger.warning(f"Eval generation with degraded coverage ({current_coverage}), using generated evals")
            return current_evals
        else:
            logger.error(f"Eval generation failed with insufficient coverage ({current_coverage}), below block threshold")
            return self.minimum_evals_template

    def _prepare_generation_prompt(self, skill_spec: Dict[str, Any]) -> str:
        return f"""
Generate evaluation test cases for the following skill specification:

Skill Name: {skill_spec.get('name', 'Unknown')}
Description: {skill_spec.get('description', 'No description')}
Triggers: {skill_spec.get('triggers', [])}
Workflow Steps: {skill_spec.get('workflow_steps', [])}
Anti-Patterns: {skill_spec.get('anti_patterns', [])}
Output Format: {skill_spec.get('output_format', [])}
Examples: {skill_spec.get('examples', [])}

Generate a JSON object with an array of eval_cases containing:
- id: integer
- name: string
- category: "normal", "boundary", "failure", or "trigger"
- input: string (the input to test the skill with)
- expected_triggers: boolean (whether the skill should trigger)
- assertions: array of objects with type ("contains", "not_contains", "regex", "starts_with", "json_valid"), value, and weight

Minimum requirements:
- At least 4 eval cases total
- At least 5 trigger cases (should_trigger and should_not_trigger)
- Cover workflow steps, anti-patterns, and output formats mentioned in the spec
"""

    def _parse_evals_response(self, response: str) -> Dict[str, Any]:
        try:
            start_idx = response.find('{')
            end_idx = response.rfind('}') + 1
            
            if start_idx != -1 and end_idx != 0:
                json_str = response[start_idx:end_idx]
                parsed = json.loads(json_str)
                
                # Normalize to use eval_cases key
                if "eval_cases" not in parsed:
                    # Look for other possible keys that might contain eval cases
                    for key in ["evals", "cases", "test_cases", "evaluations", "eval"]:
                        if key in parsed and isinstance(parsed[key], list):
                            parsed["eval_cases"] = parsed[key]
                            break
                    else:
                        # If no eval_cases found, wrap the whole response in an eval case
                        parsed["eval_cases"] = [{
                            "id": 1,
                            "name": "fallback-case",
                            "category": "normal",
                            "input": "Execute the skill",
                            "expected_triggers": True,
                            "assertions": [{"type": "contains", "value": "skill", "weight": 1}]
                        }]
                
                return parsed
            else:
                return self.minimum_evals_template
        except json.JSONDecodeError:
            logger.warning("Could not parse JSON from model response, using template")
            return self.minimum_evals_template

    def _has_sufficient_evals(self, evals: Dict[str, Any]) -> bool:
        """Check if evals have sufficient cases."""
        eval_cases = evals.get("eval_cases", [])
        if not eval_cases:
            # Also check for alternative keys
            for key in ["evals", "cases", "test_cases", "evaluations", "eval"]:
                if key in evals and isinstance(evals[key], list):
                    eval_cases = evals[key]
                    break
        
        return len(eval_cases) >= 4

    @staticmethod
    def _get_eval_cases(evals: Dict[str, Any]) -> list:
        eval_cases = evals.get("eval_cases", [])
        if not eval_cases:
            for key in ["evals", "cases", "test_cases", "evaluations", "eval"]:
                if key in evals and isinstance(evals[key], list):
                    return evals[key]
        return eval_cases

    @staticmethod
    def _compute_section_coverage(section_items: list, assertion_set: set) -> float:
        total = len(section_items)
        if total == 0:
            return 1.0
        covered = 0
        for item in section_items:
            search = item.get("name", "") if isinstance(item, dict) else str(item)
            if any(search.lower() in str(val).lower() for val in assertion_set):
                covered += 1
        return covered / total

    def _calculate_coverage(self, evals: Dict[str, Any], skill_spec: Dict[str, Any]) -> float:
        eval_cases = self._get_eval_cases(evals)
        if not eval_cases:
            return 0.0

        assertion_set = {
            a.get("value", "")
            for case in eval_cases
            for a in case.get("assertions", [])
        }

        workflow_coverage = self._compute_section_coverage(
            skill_spec.get("workflow_steps", []), assertion_set
        )
        anti_pattern_coverage = self._compute_section_coverage(
            [str(p) for p in skill_spec.get("anti_patterns", [])], assertion_set
        )
        output_coverage = self._compute_section_coverage(
            skill_spec.get("output_format", []), assertion_set
        )

        return workflow_coverage * 0.5 + anti_pattern_coverage * 0.3 + output_coverage * 0.2

    def _prepare_review_prompt(self, evals: Dict[str, Any], skill_spec: Dict[str, Any], coverage: float) -> str:
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
5. Whether the assertions are meaningful and verifiable

Return a JSON object with:
- coverage: current coverage value
- gaps: array of strings describing uncovered areas
- needs_improvement: boolean indicating if more evals are needed
"""

    def _parse_review_response(self, response: str, current_coverage: float) -> Dict[str, Any]:
        try:
            start_idx = response.find('{')
            end_idx = response.rfind('}') + 1
            
            if start_idx != -1 and end_idx != 0:
                json_str = response[start_idx:end_idx]
                parsed = json.loads(json_str)
                
                if "coverage" not in parsed:
                    parsed["coverage"] = current_coverage
                if "gaps" not in parsed:
                    parsed["gaps"] = []
                if "needs_improvement" not in parsed:
                    parsed["needs_improvement"] = len(parsed["gaps"]) > 0
                
                return parsed
            else:
                return {
                    "coverage": current_coverage,
                    "gaps": ["Could not parse review response"],
                    "needs_improvement": True
                }
        except json.JSONDecodeError:
            return {
                "coverage": current_coverage,
                "gaps": ["Could not parse review response"],
                "needs_improvement": True
            }

    def _prepare_gap_filling_prompt(self, gaps: Dict[str, Any], skill_spec: Dict[str, Any]) -> str:
        return f"""
Based on the identified gaps, generate additional evaluation test cases to improve coverage:

Skill Spec: {json.dumps(skill_spec, indent=2)}
Identified Gaps: {gaps.get('gaps', [])}
Current Coverage: {gaps.get('coverage', 0.0)}

Generate additional eval cases to address the gaps. Focus on:
- Workflow steps that are not covered
- Anti-patterns that are not tested
- Output formats that are not verified
- Boundary and failure cases if missing
- Trigger cases if not sufficient

Return a JSON object with an array of eval_cases in the same format as before.
"""

    def _merge_evals(self, current_evals: Dict[str, Any], supplementary_evals: Dict[str, Any]) -> Dict[str, Any]:
        # Create a copy of current evals
        merged = {}
        for key, value in current_evals.items():
            if isinstance(value, list):
                merged[key] = value[:]
            else:
                merged[key] = value
        
        # Find the eval_cases key in current evals
        current_eval_cases = None
        for key in ["eval_cases", "evals", "cases", "test_cases", "evaluations", "eval"]:
            if key in merged and isinstance(merged[key], list):
                current_eval_cases = merged[key]
                break
        
        # Find the eval_cases key in supplementary evals
        supplementary_eval_cases = None
        for key in ["eval_cases", "evals", "cases", "test_cases", "evaluations", "eval"]:
            if key in supplementary_evals and isinstance(supplementary_evals[key], list):
                supplementary_eval_cases = supplementary_evals[key]
                break
        
        if current_eval_cases is not None and supplementary_eval_cases:
            # Assign new IDs to supplementary evals to avoid conflicts
            current_max_id = max([case.get("id", 0) for case in current_eval_cases], default=0)
            for i, case in enumerate(supplementary_eval_cases):
                case_copy = case.copy()
                case_copy["id"] = current_max_id + i + 1
                current_eval_cases.append(case_copy)
        
        return merged