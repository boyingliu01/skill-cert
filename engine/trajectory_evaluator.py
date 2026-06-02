"""Trajectory evaluator — repetition detection, path correctness, and path optimization."""

import json
from typing import Any

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """Single tool call in a trajectory."""

    tool_name: str
    params: dict[str, Any] = Field(default_factory=dict)
    timestamp: float = 0.0


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
    path_correctness_score: float = Field(
        ge=0.0, le=1.0, description="1.0 = perfect path match"
    )
    path_optimization_score: float = Field(
        ge=0.0, le=1.0, description="1.0 = no unnecessary calls"
    )
    repeated_calls: list[str] = Field(
        default_factory=list, description="List of repeated tool names"
    )
    missing_expected: list[str] = Field(default_factory=list)
    unnecessary_calls: list[str] = Field(default_factory=list)


class TrajectoryEvaluator:
    """Evaluates LLM agent trajectories for quality metrics."""

    def detect_repetition(
        self, steps: list[TrajectoryStep]
    ) -> tuple[float, list[str]]:
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
            if (
                exp_idx < len(expected.tool_names)
                and tool == expected.tool_names[exp_idx]
            ):
                matches += 1
                exp_idx += 1
        missing = expected.tool_names[exp_idx:]
        score = matches / len(expected.tool_names)
        return score, missing

    def assess_optimization(
        self, steps: list[TrajectoryStep]
    ) -> tuple[float, list[str]]:
        """Assess if there are unnecessary tool call steps.

        Detects consecutive same-tool duplicate calls.
        """
        unnecessary: list[str] = []
        tool_steps = [
            s for s in steps if s.tool_call is not None
        ]
        tool_calls = [
            s.tool_call for s in tool_steps
            if s.tool_call is not None
        ]
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

        total = (
            rep_score * 0.4 + path_score * 0.35 + opt_score * 0.25
        )

        return TrajectoryScore(
            total_score=round(total, 3),
            repetition_score=rep_score,
            path_correctness_score=path_score,
            path_optimization_score=opt_score,
            repeated_calls=repeated,
            missing_expected=missing,
            unnecessary_calls=unnecessary,
        )
