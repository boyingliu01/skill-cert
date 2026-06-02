"""Tests for engine/trajectory_evaluator.py — trajectory quality evaluation."""

import pytest

from engine.trajectory_evaluator import (
    ExpectedPath,
    ToolCall,
    TrajectoryEvaluator,
    TrajectoryScore,
    TrajectoryStep,
)

# ─── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def evaluator() -> TrajectoryEvaluator:
    return TrajectoryEvaluator()


@pytest.fixture
def all_unique_steps() -> list[TrajectoryStep]:
    return [
        TrajectoryStep(
            step_number=1,
            tool_call=ToolCall(tool_name="read_file", params={"path": "foo.txt"}),
        ),
        TrajectoryStep(
            step_number=2,
            tool_call=ToolCall(tool_name="write_file", params={"path": "bar.txt"}),
        ),
        TrajectoryStep(
            step_number=3,
            tool_call=ToolCall(tool_name="run_command", params={"cmd": "ls"}),
        ),
    ]


@pytest.fixture
def repeated_steps() -> list[TrajectoryStep]:
    return [
        TrajectoryStep(
            step_number=1,
            tool_call=ToolCall(tool_name="read_file", params={"path": "foo.txt"}),
        ),
        TrajectoryStep(
            step_number=2,
            tool_call=ToolCall(tool_name="read_file", params={"path": "foo.txt"}),
        ),
        TrajectoryStep(
            step_number=3,
            tool_call=ToolCall(tool_name="write_file", params={"path": "bar.txt"}),
        ),
    ]


@pytest.fixture
def mixed_message_and_tool_steps() -> list[TrajectoryStep]:
    return [
        TrajectoryStep(step_number=1, message="Let me start"),
        TrajectoryStep(
            step_number=2,
            tool_call=ToolCall(tool_name="search", params={"query": "test"}),
        ),
        TrajectoryStep(step_number=3, message="I found something"),
        TrajectoryStep(
            step_number=4,
            tool_call=ToolCall(tool_name="search", params={"query": "test"}),
        ),
    ]


# ─── Test: detect_repetition ────────────────────────────────────────────────

class TestDetectRepetition:

    def test_no_repetition(self, evaluator: TrajectoryEvaluator,
                           all_unique_steps: list[TrajectoryStep]):
        """All different tool calls → repetition_score == 1.0."""
        score, repeated = evaluator.detect_repetition(all_unique_steps)
        assert score == 1.0
        assert repeated == []

    def test_with_repetition(self, evaluator: TrajectoryEvaluator,
                             repeated_steps: list[TrajectoryStep]):
        """3 steps, 2 with same tool+params → repetition_score < 1.0."""
        score, repeated = evaluator.detect_repetition(repeated_steps)
        assert score < 1.0
        assert "read_file" in repeated
        assert len(repeated) == 1

    def test_empty_steps(self, evaluator: TrajectoryEvaluator):
        """No tool calls → all scores 1.0."""
        score, repeated = evaluator.detect_repetition([])
        assert score == 1.0
        assert repeated == []

    def test_steps_with_only_messages(self, evaluator: TrajectoryEvaluator):
        """Steps with only messages, no tool calls."""
        steps = [
            TrajectoryStep(step_number=1, message="Hello"),
            TrajectoryStep(step_number=2, message="World"),
        ]
        score, repeated = evaluator.detect_repetition(steps)
        assert score == 1.0
        assert repeated == []

    def test_multiple_repetitions(self, evaluator: TrajectoryEvaluator):
        """Multiple tools repeated multiple times."""
        steps = [
            TrajectoryStep(step_number=1, tool_call=ToolCall(tool_name="read", params={"f": "a"})),
            TrajectoryStep(step_number=2, tool_call=ToolCall(tool_name="read", params={"f": "a"})),
            TrajectoryStep(step_number=3, tool_call=ToolCall(tool_name="write", params={"f": "b"})),
            TrajectoryStep(step_number=4, tool_call=ToolCall(tool_name="read", params={"f": "a"})),
            TrajectoryStep(step_number=5, tool_call=ToolCall(tool_name="write", params={"f": "b"})),
        ]
        score, repeated = evaluator.detect_repetition(steps)
        assert score < 0.6  # 3 repeats out of 5 tool steps
        assert len(repeated) >= 2

    def test_same_tool_different_params_no_repetition(
        self, evaluator: TrajectoryEvaluator,
    ):
        """Same tool called with different params should not count as repetition."""
        steps = [
            TrajectoryStep(step_number=1, tool_call=ToolCall(tool_name="read", params={"f": "a"})),
            TrajectoryStep(step_number=2, tool_call=ToolCall(tool_name="read", params={"f": "b"})),
        ]
        score, repeated = evaluator.detect_repetition(steps)
        assert score == 1.0
        assert repeated == []

    def test_repetition_with_mixed_messages(
        self, evaluator: TrajectoryEvaluator,
        mixed_message_and_tool_steps: list[TrajectoryStep],
    ):
        """Repetition detection works with messages interleaved."""
        score, repeated = evaluator.detect_repetition(mixed_message_and_tool_steps)
        assert score < 1.0
        assert "search" in repeated


# ─── Test: verify_path_correctness ──────────────────────────────────────────

class TestVerifyPathCorrectness:

    def test_path_perfect_match(self, evaluator: TrajectoryEvaluator,
                                all_unique_steps: list[TrajectoryStep]):
        """Steps match expected path exactly → path_correctness_score == 1.0."""
        expected = ExpectedPath(tool_names=["read_file", "write_file", "run_command"])
        score, missing = evaluator.verify_path_correctness(all_unique_steps, expected)
        assert score == 1.0
        assert missing == []

    def test_path_partial_match(self, evaluator: TrajectoryEvaluator,
                                all_unique_steps: list[TrajectoryStep]):
        """Some tools missing → score < 1.0."""
        expected = ExpectedPath(tool_names=[
            "read_file", "write_file", "run_command", "deploy",
        ])
        score, missing = evaluator.verify_path_correctness(all_unique_steps, expected)
        assert score < 1.0
        assert "deploy" in missing

    def test_path_empty_expected(self, evaluator: TrajectoryEvaluator,
                                 all_unique_steps: list[TrajectoryStep]):
        """No expected path → score 1.0."""
        expected = ExpectedPath(tool_names=[])
        score, missing = evaluator.verify_path_correctness(all_unique_steps, expected)
        assert score == 1.0
        assert missing == []

    def test_path_extra_tools_in_actual(self, evaluator: TrajectoryEvaluator):
        """Actual has more tools than expected — still a perfect match if prefix matches."""
        steps = [
            TrajectoryStep(step_number=1, tool_call=ToolCall(tool_name="read")),
            TrajectoryStep(step_number=2, tool_call=ToolCall(tool_name="write")),
            TrajectoryStep(step_number=3, tool_call=ToolCall(tool_name="deploy")),
        ]
        expected = ExpectedPath(tool_names=["read", "write"])
        score, missing = evaluator.verify_path_correctness(steps, expected)
        assert score == 1.0
        assert missing == []

    def test_path_out_of_order(self, evaluator: TrajectoryEvaluator):
        """Tools in wrong order → partial match only."""
        steps = [
            TrajectoryStep(step_number=1, tool_call=ToolCall(tool_name="write")),
            TrajectoryStep(step_number=2, tool_call=ToolCall(tool_name="read")),
        ]
        expected = ExpectedPath(tool_names=["read", "write"])
        score, missing = evaluator.verify_path_correctness(steps, expected)
        assert score < 1.0
        assert "write" in missing or score == 0.5

    def test_path_no_tool_calls(self, evaluator: TrajectoryEvaluator):
        """No tool calls in actual steps."""
        steps = [
            TrajectoryStep(step_number=1, message="Hello"),
        ]
        expected = ExpectedPath(tool_names=["read"])
        score, missing = evaluator.verify_path_correctness(steps, expected)
        assert score == 0.0
        assert "read" in missing


# ─── Test: assess_optimization ──────────────────────────────────────────────

class TestAssessOptimization:

    def test_no_unnecessary_calls(self, evaluator: TrajectoryEvaluator,
                                  all_unique_steps: list[TrajectoryStep]):
        """All unique calls → optimization_score == 1.0."""
        score, unnecessary = evaluator.assess_optimization(all_unique_steps)
        assert score == 1.0
        assert unnecessary == []

    def test_consecutive_duplicate(self, evaluator: TrajectoryEvaluator):
        """Same tool called twice consecutively → unnecessary detected."""
        steps = [
            TrajectoryStep(step_number=1, tool_call=ToolCall(tool_name="read", params={"f": "a"})),
            TrajectoryStep(step_number=1, tool_call=ToolCall(tool_name="read", params={"f": "a"})),
            TrajectoryStep(step_number=2, tool_call=ToolCall(tool_name="write", params={"f": "b"})),
        ]
        score, unnecessary = evaluator.assess_optimization(steps)
        assert score < 1.0
        assert "read" in unnecessary

    def test_no_tool_calls_optimization(self, evaluator: TrajectoryEvaluator):
        """No tool calls → optimization_score == 1.0."""
        steps = [
            TrajectoryStep(step_number=1, message="Hello"),
        ]
        score, unnecessary = evaluator.assess_optimization(steps)
        assert score == 1.0
        assert unnecessary == []

    def test_non_consecutive_duplicate_not_unnecessary(
        self, evaluator: TrajectoryEvaluator,
    ):
        """Same tool called non-consecutively with different stuff between — not unnecessary."""
        steps = [
            TrajectoryStep(step_number=1, tool_call=ToolCall(tool_name="read", params={"f": "a"})),
            TrajectoryStep(step_number=2, tool_call=ToolCall(tool_name="write", params={"f": "b"})),
            TrajectoryStep(step_number=3, tool_call=ToolCall(tool_name="read", params={"f": "a"})),
        ]
        score, unnecessary = evaluator.assess_optimization(steps)
        assert score == 1.0
        assert unnecessary == []


# ─── Test: full evaluate ────────────────────────────────────────────────────

class TestFullEvaluation:

    def test_full_evaluation(self, evaluator: TrajectoryEvaluator):
        """Complete evaluate() with expected path → total_score computed correctly."""
        steps = [
            TrajectoryStep(step_number=1, tool_call=ToolCall(tool_name="search", params={"q": "test"})),
            TrajectoryStep(step_number=2, tool_call=ToolCall(tool_name="read", params={"f": "a"})),
            TrajectoryStep(step_number=3, tool_call=ToolCall(tool_name="read", params={"f": "a"})),
        ]
        expected = ExpectedPath(tool_names=["search", "read", "write"])
        result = evaluator.evaluate(steps, expected)
        assert isinstance(result, TrajectoryScore)
        assert 0.0 <= result.total_score <= 1.0
        assert "read" in result.repeated_calls
        assert "write" in result.missing_expected

    def test_full_evaluation_no_expected(self, evaluator: TrajectoryEvaluator):
        """evaluate() without expected path → path score is 1.0."""
        steps = [
            TrajectoryStep(step_number=1, tool_call=ToolCall(tool_name="read", params={"f": "a"})),
        ]
        result = evaluator.evaluate(steps)
        assert result.total_score > 0.0
        assert result.path_correctness_score == 1.0

    def test_score_range(self, evaluator: TrajectoryEvaluator):
        """Verify all scores are in [0.0, 1.0] for various inputs."""
        test_cases = [
            [],
            [TrajectoryStep(step_number=1, message="only message")],
            [TrajectoryStep(step_number=1, tool_call=ToolCall(tool_name="x"))],
            [
                TrajectoryStep(step_number=1, tool_call=ToolCall(tool_name="x")),
                TrajectoryStep(step_number=2, tool_call=ToolCall(tool_name="x")),
            ],
            [
                TrajectoryStep(step_number=1, tool_call=ToolCall(tool_name="a", params={"p": "1"})),
                TrajectoryStep(step_number=2, tool_call=ToolCall(tool_name="b", params={"p": "2"})),
                TrajectoryStep(step_number=3, tool_call=ToolCall(tool_name="a", params={"p": "1"})),
                TrajectoryStep(step_number=4, tool_call=ToolCall(tool_name="b", params={"p": "2"})),
            ],
        ]
        for steps in test_cases:
            result = evaluator.evaluate(steps)
            assert 0.0 <= result.total_score <= 1.0, f"total_score out of range: {result.total_score}"
            assert 0.0 <= result.repetition_score <= 1.0
            assert 0.0 <= result.path_correctness_score <= 1.0
            assert 0.0 <= result.path_optimization_score <= 1.0

    def test_weights_produce_correct_total(self, evaluator: TrajectoryEvaluator):
        """Verify weighted formula in evaluate()."""
        steps = [
            TrajectoryStep(step_number=1, tool_call=ToolCall(tool_name="a")),
            TrajectoryStep(step_number=2, tool_call=ToolCall(tool_name="a")),
        ]
        # rep_score = 1.0 - (1/2) = 0.5
        # path_score = 1.0 (no expected)
        # opt_score = 1.0 (no consecutive same params? Actually same tool_name + empty params)
        # Wait: assess_optimization checks tool_name AND params. params are same (empty dict)
        # So: opt_score = 1.0 - (1/2) = 0.5
        # total = 0.5 * 0.4 + 1.0 * 0.35 + 0.5 * 0.25 = 0.2 + 0.35 + 0.125 = 0.675
        result = evaluator.evaluate(steps)
        assert result.total_score == pytest.approx(0.675, abs=0.01)
        assert result.repetition_score == pytest.approx(0.5, abs=0.01)
        assert result.path_correctness_score == 1.0

    def test_result_model_fields(self, evaluator: TrajectoryEvaluator,
                                 all_unique_steps: list[TrajectoryStep]):
        """Verify TrajectoryScore model fields are populated correctly."""
        result = evaluator.evaluate(all_unique_steps)
        assert isinstance(result.repeated_calls, list)
        assert isinstance(result.missing_expected, list)
        assert isinstance(result.unnecessary_calls, list)
        # All scores should be 1.0 for perfect trajectory
        assert result.total_score == 1.0
        assert result.repetition_score == 1.0
        assert result.path_correctness_score == 1.0
        assert result.path_optimization_score == 1.0
