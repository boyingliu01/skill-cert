"""Trajectory evaluator — repetition detection, path correctness, and path optimization."""

import json
from typing import Any

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """Single tool call in a trajectory."""

    tool_name: str
    params: dict[str, Any] = Field(default_factory=dict)
    timestamp: float = 0.0
    result: str | None = None


class TrajectoryStep(BaseModel):
    """One step in a trajectory sequence."""

    tool_call: ToolCall | None = None
    message: str | None = None
    step_number: int


class ExpectedPath(BaseModel):
    """Expected tool call sequence for path correctness check."""

    tool_names: list[str]  # ordered list of expected tool names


class TrajectoryScore(BaseModel):
    """Trajectory quality evaluation score."""

    total_score: float = Field(ge=0.0, le=1.0)
    repetition_score: float = Field(
        ge=0.0, le=1.0, description="1.0 = no repetition, lower = more repetition"
    )
    path_correctness_score: float = Field(ge=0.0, le=1.0, description="1.0 = perfect path match")
    path_optimization_score: float = Field(ge=0.0, le=1.0, description="1.0 = no unnecessary calls")
    tool_call_accuracy_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="1.0 = all tool calls correct"
    )
    turn_relevance_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="1.0 = all turns relevant"
    )
    repeated_calls: list[str] = Field(
        default_factory=list, description="List of repeated tool names"
    )
    missing_expected: list[str] = Field(default_factory=list)
    unnecessary_calls: list[str] = Field(default_factory=list)


def _check_tool_correctness(
    tool_steps: list[TrajectoryStep],
    expected_tools: list[str] | None,
) -> float:
    """Check tool call correctness based on expected tools or results."""
    if expected_tools is not None and len(expected_tools) > 0:
        return _check_against_expected_set(tool_steps, set(expected_tools))

    # Fallback: check if tool calls have results (success indicator)
    with_results = sum(
        1 for s in tool_steps if s.tool_call is not None and s.tool_call.result is not None
    )
    return with_results / len(tool_steps)


def _check_against_expected_set(
    tool_steps: list[TrajectoryStep],
    expected_set: set[str],
) -> float:
    """Check how many tool calls match the expected set."""
    correct = sum(
        1 for s in tool_steps if s.tool_call is not None and s.tool_call.tool_name in expected_set
    )
    return correct / len(tool_steps)


class TrajectoryEvaluator:
    """Evaluates LLM agent trajectories for quality metrics."""

    def detect_repetition(self, steps: list[TrajectoryStep]) -> tuple[float, list[str]]:
        """Detect duplicate tool calls (same tool_name + same params).

        Returns (score, repeated_names).
        """
        seen: dict[str, int] = {}
        repeated: list[str] = []
        tool_steps = [s for s in steps if s.tool_call is not None]
        for step in tool_steps:
            tc = step.tool_call
            if tc is None:
                continue
            key = (
                tc.tool_name,
                json.dumps(tc.params, sort_keys=True),
            )
            key_str = f"{key[0]}::{key[1]}"
            if key_str in seen:
                repeated.append(tc.tool_name)
            seen[key_str] = seen.get(key_str, 0) + 1
        if not tool_steps:
            return 1.0, []
        total_tool_steps = len(tool_steps)
        score = 1.0 - (len(repeated) / max(total_tool_steps, 1))
        return max(0.0, score), repeated

    def verify_path_correctness(
        self, steps: list[TrajectoryStep], expected: ExpectedPath
    ) -> tuple[float, list[str]]:
        """Verify tool call sequence matches expected workflow path."""
        actual_tools = [s.tool_call.tool_name for s in steps if s.tool_call]
        if not expected.tool_names:
            return 1.0, []
        # Find longest common subsequence via greedy matching
        matches = 0
        exp_idx = 0
        for tool in actual_tools:
            if exp_idx < len(expected.tool_names) and tool == expected.tool_names[exp_idx]:
                matches += 1
                exp_idx += 1
        missing = expected.tool_names[exp_idx:]
        score = matches / len(expected.tool_names)
        return score, missing

    def assess_optimization(self, steps: list[TrajectoryStep]) -> tuple[float, list[str]]:
        """Assess if there are unnecessary tool call steps.

        Detects consecutive same-tool duplicate calls.
        """
        unnecessary: list[str] = []
        tool_steps = [s for s in steps if s.tool_call is not None]
        tool_calls = [s.tool_call for s in tool_steps if s.tool_call is not None]
        for i in range(1, len(tool_calls)):
            curr = tool_calls[i]
            prev = tool_calls[i - 1]
            if curr.tool_name == prev.tool_name and curr.params == prev.params:
                unnecessary.append(curr.tool_name)
        total = len(tool_calls)
        if total == 0:
            return 1.0, []
        score = 1.0 - (len(unnecessary) / total)
        return max(0.0, score), unnecessary

    def evaluate_tool_call_correctness(
        self,
        steps: list[TrajectoryStep],
        expected_tools: list[str] | None = None,
    ) -> float:
        """Evaluate tool call correctness.

        If expected_tools is provided, checks whether each tool call matches
        an expected tool name. Otherwise, checks whether each tool call has
        a non-empty result (indicating success).

        Returns a score in [0.0, 1.0].
        """
        tool_steps = [s for s in steps if s.tool_call is not None]
        if not tool_steps:
            return 0.0

        return _check_tool_correctness(tool_steps, expected_tools)

    def _calculate_turn_relevance(self, steps: list[TrajectoryStep]) -> float:
        """Calculate turn relevance score.

        A turn is relevant if it either has a tool call or a non-empty message.
        Steps with neither are considered irrelevant.

        Returns a score in [0.0, 1.0].
        """
        if not steps:
            return 0.0

        relevant = 0
        for step in steps:
            if step.tool_call is not None:
                relevant += 1
            elif step.message and step.message.strip():
                relevant += 1
        return relevant / len(steps)

    def evaluate(
        self,
        steps: list[TrajectoryStep],
        expected: ExpectedPath | None = None,
    ) -> TrajectoryScore:
        """Full trajectory evaluation with weighted scoring.

        Weights: repetition=0.4, path_correctness=0.35, optimization=0.25
        """
        rep_score, repeated = self.detect_repetition(steps)
        if expected:
            path_score, missing = self.verify_path_correctness(steps, expected)
        else:
            path_score, missing = 1.0, []
        opt_score, unnecessary = self.assess_optimization(steps)

        total = rep_score * 0.4 + path_score * 0.35 + opt_score * 0.25

        # Turn-level metrics
        expected_tools = expected.tool_names if expected else None
        tca_score = self.evaluate_tool_call_correctness(steps, expected_tools)
        turn_rel = self._calculate_turn_relevance(steps)

        return TrajectoryScore(
            total_score=round(total, 3),
            repetition_score=rep_score,
            path_correctness_score=path_score,
            path_optimization_score=opt_score,
            tool_call_accuracy_score=round(tca_score, 3),
            turn_relevance_score=round(turn_rel, 3),
            repeated_calls=repeated,
            missing_expected=missing,
            unnecessary_calls=unnecessary,
        )
