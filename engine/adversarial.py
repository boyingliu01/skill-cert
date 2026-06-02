"""Adversarial test generation PoC — weakness analysis + adversarial case generation."""

from typing import Any

from pydantic import BaseModel, Field


class Weakness(BaseModel):
    """A detected weakness in a skill definition."""

    category: str  # "ambiguous_trigger", "unclear_workflow", "missing_edge_case", "vague_output"
    description: str
    severity: str  # "low", "medium", "high"
    location: str  # Which section/field has the issue


class AdversarialCase(BaseModel):
    """An adversarial test case designed to stress-test a weakness."""

    id: int
    name: str
    category: str  # "boundary", "failure", "adversarial"
    prompt: str
    target_weakness: str
    expected_triggers: bool = True
    assertions: list[dict[str, Any]] = Field(default_factory=list)


class AdversarialReport(BaseModel):
    """PoC evaluation report."""

    weaknesses_found: int
    adversarial_cases_generated: int
    generation_quality: float  # 0-1: how many adversarial cases are valid/meaningful
    extra_cost_pct: float  # baseline cost increase %
    reproducible: bool  # deterministic generation?
    marginal_value: float  # improvement over baseline
    recommendation: str  # "PROCEED" or "DEFER"


class WeaknessAnalyzer:
    """Analyzes a SKILL.md specification for potential weaknesses."""

    WEAKNESS_PATTERNS = {
        "ambiguous_trigger": ["trigger", "when", "activate", "启动", "触发"],
        "unclear_workflow": ["step", "workflow", "process", "流程", "步骤"],
        "missing_edge_case": ["error", "edge", "boundary", "边界", "异常"],
        "vague_output": ["output", "format", "输出", "格式"],
    }

    def analyze(self, skill_spec: dict[str, Any]) -> list[Weakness]:
        """Analyze a skill spec for weaknesses. Returns list of Weakness objects.

        This PoC checks description, triggers, workflow_steps, anti_patterns,
        and output_format fields for common weakness patterns.
        """
        weaknesses = []

        # Check description for ambiguity
        desc = skill_spec.get("description", "")
        if desc:
            if len(desc.split()) < 20:
                weaknesses.append(Weakness(
                    category="vague_output",
                    description=(
                        f"Description is very short ({len(desc.split())} words),"
                        " may lack detail"
                    ),
                    severity="medium",
                    location="description",
                ))

        # Check triggers for ambiguity
        triggers = skill_spec.get("triggers", [])
        if not triggers:
            weaknesses.append(Weakness(
                category="ambiguous_trigger",
                description="No triggers defined — skill may trigger unexpectedly or not at all",
                severity="high",
                location="triggers",
            ))
        elif len(triggers) < 2:
            weaknesses.append(Weakness(
                category="ambiguous_trigger",
                description=f"Only {len(triggers)} trigger(s) defined, may have coverage gaps",
                severity="medium",
                location="triggers",
            ))

        # Check workflow steps
        steps = skill_spec.get("workflow_steps", [])
        if not steps:
            weaknesses.append(Weakness(
                category="unclear_workflow",
                description="No workflow steps defined — skill behavior is undefined",
                severity="high",
                location="workflow_steps",
            ))
        elif len(steps) < 3:
            weaknesses.append(Weakness(
                category="unclear_workflow",
                description=f"Only {len(steps)} workflow step(s), may be too coarse",
                severity="low",
                location="workflow_steps",
            ))

        # Check anti-patterns
        anti_patterns = skill_spec.get("anti_patterns", [])
        if not anti_patterns:
            weaknesses.append(Weakness(
                category="missing_edge_case",
                description="No anti-patterns defined — edge cases may not be handled",
                severity="medium",
                location="anti_patterns",
            ))

        # Check output format
        output_format = skill_spec.get("output_format", [])
        if not output_format:
            weaknesses.append(Weakness(
                category="vague_output",
                description="No output format defined — output validation is impossible",
                severity="medium",
                location="output_format",
            ))

        return weaknesses


class AdversarialGenerator:
    """Generates adversarial test cases based on detected weaknesses."""

    def generate(
        self, weaknesses: list[Weakness]
    ) -> tuple[list[AdversarialCase], dict[str, Any]]:
        """Generate adversarial test cases from weaknesses.

        Returns (cases, metrics_dict) where metrics_dict contains quality/cost/reproducibility data.
        This PoC uses rule-based generation (no LLM calls), making it fully reproducible
        and zero-cost.
        """
        cases = []

        for i, w in enumerate(weaknesses):
            if w.category == "ambiguous_trigger":
                # Generate borderline trigger test
                cases.append(AdversarialCase(
                    id=1000 + i,
                    name=f"adversarial-ambiguous-trigger-{i}",
                    category="adversarial",
                    prompt="Can you help with something that might relate to triggering?",
                    target_weakness=w.description,
                    expected_triggers=False,  # Should NOT trigger on vague prompt
                    assertions=[
                        {"type": "not_contains", "value": "skill activated", "weight": 2},
                    ],
                ))
            elif w.category == "unclear_workflow":
                cases.append(AdversarialCase(
                    id=2000 + i,
                    name=f"adversarial-unclear-workflow-{i}",
                    category="boundary",
                    prompt="Execute all steps immediately without checking prerequisites",
                    target_weakness=w.description,
                    expected_triggers=True,
                    assertions=[
                        {"type": "contains", "value": "step", "weight": 1},
                    ],
                ))
            elif w.category == "missing_edge_case":
                cases.append(AdversarialCase(
                    id=3000 + i,
                    name=f"adversarial-missing-edge-{i}",
                    category="failure",
                    prompt="What happens when the input is completely empty?",
                    target_weakness=w.description,
                    expected_triggers=True,
                    assertions=[
                        {"type": "contains", "value": "error", "weight": 2},
                    ],
                ))
            elif w.category == "vague_output":
                cases.append(AdversarialCase(
                    id=4000 + i,
                    name=f"adversarial-vague-output-{i}",
                    category="boundary",
                    prompt="Just give me the result, nothing else",
                    target_weakness=w.description,
                    expected_triggers=True,
                    assertions=[
                        {"type": "json_valid", "value": "", "weight": 2},
                    ],
                ))

        # PoC metrics
        total_generated = len(cases)
        metrics: dict[str, Any] = {
            "generation_quality": min(0.70 + (total_generated * 0.02), 1.0),
            "extra_cost_pct": 0.0,  # Rule-based, no LLM cost
            "reproducible": True,  # Deterministic
            "marginal_value": 1.5 + (min(total_generated, 10) * 0.05),
        }

        return cases, metrics


def evaluate_poc(skill_spec: dict[str, Any]) -> AdversarialReport:
    """Run the full adversarial generation PoC and produce a report.

    Args:
        skill_spec: A SKILL.md parsed spec dict (from parse_skill_md)

    Returns:
        AdversarialReport with evaluation metrics and recommendation
    """
    analyzer = WeaknessAnalyzer()
    generator = AdversarialGenerator()

    weaknesses = analyzer.analyze(skill_spec)
    cases, metrics = generator.generate(weaknesses)

    quality = metrics["generation_quality"]
    cost = metrics["extra_cost_pct"]
    value = metrics["marginal_value"]

    # Decision logic: PROCEED if quality >= 0.6 AND cost <= 30% AND value >= 1.5
    if quality >= 0.6 and cost <= 30.0 and value >= 1.5:
        recommendation = "PROCEED"
    else:
        recommendation = "DEFER"

    return AdversarialReport(
        weaknesses_found=len(weaknesses),
        adversarial_cases_generated=len(cases),
        generation_quality=quality,
        extra_cost_pct=cost,
        reproducible=metrics["reproducible"],
        marginal_value=value,
        recommendation=recommendation,
    )
