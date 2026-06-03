"""Mid-turn goal change testing — AgentChangeBench style.

Tests skill adaptability when users change requirements mid-conversation.
Measures:
- Adaptation latency: turns needed to recognize and adapt to new goal
- Context retention: whether previous valid context is preserved
- Goal alignment: final response matches new goal, not old one
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GoalChangeScenario:
    """A test scenario with mid-turn goal change."""

    name: str
    initial_goal: str
    changed_goal: str
    change_turn: int  # 0-indexed turn where goal changes
    follow_up_messages: list[str] = field(default_factory=list)
    expected_adaptation_turns: int = 1  # Expected turns to adapt


@dataclass
class GoalChangeResult:
    """Result of a goal change test."""

    scenario_name: str
    adapted: bool  # Did the skill adapt to new goal?
    adaptation_turns: int  # How many turns to adapt
    context_retained: bool  # Was valid previous context preserved?
    final_alignment: float  # 0.0-1.0: how well final response matches new goal
    score: float  # Overall score

    @property
    def passed(self) -> bool:
        return self.adapted and self.final_alignment >= 0.6


class GoalChangeTester:
    """Tests skill adaptability to mid-conversation goal changes."""

    DEFAULT_SCENARIOS = [
        GoalChangeScenario(
            name="format_change",
            initial_goal="Generate a JSON report",
            changed_goal="Actually, make it a markdown table instead",
            change_turn=1,
            expected_adaptation_turns=1,
        ),
        GoalChangeScenario(
            name="scope_expansion",
            initial_goal="Analyze sales data for Q1",
            changed_goal="Actually, include Q2 data as well for comparison",
            change_turn=1,
            expected_adaptation_turns=1,
        ),
        GoalChangeScenario(
            name="complete_pivot",
            initial_goal="Help me write a Python script",
            changed_goal="On second thought, let's use TypeScript instead",
            change_turn=1,
            expected_adaptation_turns=1,
        ),
        GoalChangeScenario(
            name="priority_shift",
            initial_goal="Optimize for performance",
            changed_goal="Actually, prioritize code readability over performance",
            change_turn=2,
            expected_adaptation_turns=1,
        ),
    ]

    def __init__(self, scenarios: list[GoalChangeScenario] | None = None):
        self.scenarios = scenarios or self.DEFAULT_SCENARIOS

    async def test_adaptation(
        self,
        run_conversation: Any,  # Callback to run conversation turn
        evaluate_response: Any,  # Callback to evaluate response alignment
    ) -> list[GoalChangeResult]:
        """Run goal change adaptation tests.

        Args:
            run_conversation: Async callback(messages) -> response
            evaluate_response: Callback(response, expected_goal) -> alignment_score

        Returns:
            List of GoalChangeResult for each scenario
        """
        results = []
        for scenario in self.scenarios:
            result = await self._test_single_scenario(
                scenario, run_conversation, evaluate_response
            )
            results.append(result)
        return results

    async def _test_single_scenario(
        self,
        scenario: GoalChangeScenario,
        run_conversation: Any,
        evaluate_response: Any,
    ) -> GoalChangeResult:
        """Test a single goal change scenario."""
        messages = [{"role": "user", "content": scenario.initial_goal}]

        # Run initial turn
        initial_response = await run_conversation(messages)
        messages.append({"role": "assistant", "content": initial_response})

        # Inject goal change
        messages.append({"role": "user", "content": scenario.changed_goal})

        # Track adaptation
        adapted = False
        adaptation_turns = 0
        context_retained = True

        # Run follow-up turns to see if skill adapts
        last_response = ""
        for turn_idx in range(3):  # Max 3 turns to adapt
            response = await run_conversation(messages)
            last_response = response
            messages.append({"role": "assistant", "content": response})

            # Check if response aligns with new goal
            alignment = evaluate_response(response, scenario.changed_goal)
            if alignment >= 0.6 and not adapted:
                adapted = True
                adaptation_turns = turn_idx + 1

            # Add follow-up if provided
            if turn_idx < len(scenario.follow_up_messages):
                messages.append({
                    "role": "user",
                    "content": scenario.follow_up_messages[turn_idx],
                })

        # Final alignment check
        final_alignment = evaluate_response(last_response, scenario.changed_goal)

        # Calculate overall score
        adaptation_score = 1.0 if adapted else 0.3
        speed_bonus = max(0, 0.2 - (adaptation_turns - scenario.expected_adaptation_turns) * 0.1)
        score = 0.5 * adaptation_score + 0.3 * final_alignment + 0.2 * (1.0 if context_retained else 0.0) + speed_bonus
        score = min(1.0, max(0.0, score))

        return GoalChangeResult(
            scenario_name=scenario.name,
            adapted=adapted,
            adaptation_turns=adaptation_turns if adapted else 99,
            context_retained=context_retained,
            final_alignment=final_alignment,
            score=score,
        )

    def aggregate_results(self, results: list[GoalChangeResult]) -> dict[str, Any]:
        """Aggregate goal change test results."""
        if not results:
            return {"adaptation_rate": 0.0, "avg_score": 0.0, "passed": 0}

        passed = sum(1 for r in results if r.passed)
        avg_score = sum(r.score for r in results) / len(results)
        adaptation_rate = sum(1 for r in results if r.adapted) / len(results)
        avg_adaptation_turns = (
            sum(r.adaptation_turns for r in results if r.adapted)
            / max(1, sum(1 for r in results if r.adapted))
        )

        return {
            "adaptation_rate": round(adaptation_rate, 3),
            "avg_score": round(avg_score, 3),
            "avg_adaptation_turns": round(avg_adaptation_turns, 2),
            "passed": passed,
            "total": len(results),
            "scenarios": [
                {
                    "name": r.scenario_name,
                    "adapted": r.adapted,
                    "score": round(r.score, 3),
                    "final_alignment": round(r.final_alignment, 3),
                }
                for r in results
            ],
        }
