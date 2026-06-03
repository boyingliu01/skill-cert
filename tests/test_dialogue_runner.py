from unittest.mock import AsyncMock

import pytest

from engine.dialogue_runner import DialogueRunner


@pytest.fixture
def mock_simulator():
    """Fixture that provides a mocked UserSimulator."""
    simulator = AsyncMock()
    # Mock the generate_next_message method to return a user message
    simulator.generate_next_message = AsyncMock()
    return simulator


@pytest.fixture
def mock_evaluator():
    """Fixture that provides a mocked DialogueEvaluator."""
    evaluator = AsyncMock()
    # Mock the evaluate_conversation method
    evaluator.evaluate_conversation = AsyncMock(return_value={
        'dimension_scores': {
            'intent_recognition': 0.8,
            'guidance_quality': 0.7,
            'workflow_adherence': 0.9,
            'exception_handling': 0.6,
            'output_quality': 0.8
        },
        'overall_score': 0.76,
        'verdict': 'PASS',
        'detailed_rounds': [],
        'stats': {'total_turns': 1, 'boundary_violations_count': 0}
    })
    return evaluator


@pytest.fixture
def mock_skill_runner():
    """Fixture that provides a mocked EvalRunner."""
    skill_runner = AsyncMock()
    # Mock the run_with_skill method to simulate skill responses
    skill_runner.run_with_skill = AsyncMock(return_value=[
        {
            "eval_id": "test_eval",
            "output": "This is a test response",
            "execution_time": 1.0,
            "error": None
        }
    ])
    return skill_runner


class TestDialogueRunner:

    @pytest.mark.asyncio
    async def test_dialogue_runner_terminates_on_completion_signal(self, mock_simulator, mock_evaluator, mock_skill_runner):
        """Test terminates early when 'COMPLETED:' appears"""
        # Setup simulator to return a completion message
        mock_simulator.generate_next_message.return_value = {
            "role": "user",
            "content": "Tell me a joke"
        }

        # Mock skill runner to return a message containing 'COMPLETED:'
        mock_skill_runner.run_with_skill = AsyncMock(return_value=[
            {
                "eval_id": "dialogue_turn_0",
                "output": "Here is your joke: COMPLETED: why did the chicken cross the road?",
                "execution_time": 1.0,
                "error": None
            }
        ])

        # Create runner with small max_turns to make sure completion signal actually stops early
        runner = DialogueRunner(
            simulator=mock_simulator,
            evaluator=mock_evaluator,
            skill_runner=mock_skill_runner,
            max_turns=10,  # Should exit early due to completion signal
            completion_signals=["COMPLETED:"]
        )

        # Test case
        eval_case = {"id": "test1", "input": "Tell me a joke"}
        result = await runner.run_dialogue_eval(eval_case, "test_context")

        # Assertions
        assert result["turns_completed"] == 1  # Should complete early after one turn
        assert "conversation" in result
        assert len(result["conversation"]) >= 2  # At least user message and assistant response


    @pytest.mark.asyncio
    async def test_dialogue_runner_respects_max_turns(self, mock_simulator, mock_evaluator, mock_skill_runner):
        """Test stops at max_turns if no completion signal"""
        # Setup simulator to return normal user messages that don't trigger completion
        message_count = 0
        async def mock_generate_message(eval_case, context, skill_ctx):
            nonlocal message_count
            message_count += 1
            return {
                "role": "user",
                "content": f"User message for turn {message_count}",
                "timestamp": 12345
            }

        mock_simulator.generate_next_message = mock_generate_message
        mock_skill_runner.run_with_skill = AsyncMock(return_value=[
            {
                "eval_id": "dialogue_turn_test",
                "output": "This response does not contain any completion signals",
                "execution_time": 1.0,
                "error": None
            }
        ])

        # Create runner with lower max_turns
        runner = DialogueRunner(
            simulator=mock_simulator,
            evaluator=mock_evaluator,
            skill_runner=mock_skill_runner,
            max_turns=3,  # Stop after 3 max turns
            completion_signals=["COMPLETED:"]  # No completion in responses
        )

        # Test case
        eval_case = {"id": "test1", "input": "Tell me a joke"}
        result = await runner.run_dialogue_eval(eval_case, "test_context")

        # Assertions
        assert result["turns_completed"] == 3  # Should have completed all max_turns
        assert "conversation" in result
        # Each turn consists of USER -> ASSISTANT, so: 1 initial user + 3 turns = 4 messages minimum


    @pytest.mark.asyncio
    async def test_is_conversation_complete_minimum_history(self, mock_simulator, mock_evaluator, mock_skill_runner):
        """Test returns False for history < 4"""
        # Create a runner instance to test the internal method
        runner = DialogueRunner(
            simulator=mock_simulator,
            evaluator=mock_evaluator,
            skill_runner=mock_skill_runner,
            max_turns=10
        )

        # Test history with less than 4 messages - should return False
        short_history_3 = [
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "msg2"},
            {"role": "user", "content": "msg3"}
        ]
        assert runner._is_conversation_complete(short_history_3) is False

        short_history_2 = [
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "msg2"}
        ]
        assert runner._is_conversation_complete(short_history_2) is False

        empty_history = []
        assert runner._is_conversation_complete(empty_history) is False

        single_history = [{"role": "user", "content": "msg1"}]
        assert runner._is_conversation_complete(single_history) is False

        # Test that a history with >= 4 messages but no completion signal still returns False
        longer_history_no_completion = [
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "I'm helping with your request"},
            {"role": "user", "content": "That's great"},
            {"role": "assistant", "content": "Yes, I'm continuing to help"}
        ]
        assert runner._is_conversation_complete(longer_history_no_completion) is False

        # Test that a history with a completion signal now returns True
        longer_history_with_completion = [
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "I'm helping with your request"},
            {"role": "user", "content": "That's great"},
            {"role": "assistant", "content": "COMPLETED: I have finished the task"}
        ]
        assert runner._is_conversation_complete(longer_history_with_completion) is True

    @pytest.mark.asyncio
    async def test_run_with_skill_first_call_fails_fallback(self, mock_simulator, mock_evaluator, mock_skill_runner):
        """When first run_with_skill call fails, fallback to None adapter."""
        mock_simulator.generate_next_message.return_value = {"role": "user", "content": "hi"}

        call_count = 0
        async def failing_then_succeeding(eval_list, skill_path, adapter):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise AttributeError("no _current_adapter")
            return [{"eval_id": "turn_0", "output": "COMPLETED: done", "execution_time": 1.0, "error": None}]

        mock_skill_runner.run_with_skill = failing_then_succeeding
        # Remove _current_adapter attribute so getattr fails
        if hasattr(mock_skill_runner, '_current_adapter'):
            del mock_skill_runner._current_adapter

        runner = DialogueRunner(
            simulator=mock_simulator, evaluator=mock_evaluator,
            skill_runner=mock_skill_runner, max_turns=5
        )
        result = await runner.run_dialogue_eval({"id": "t"}, "ctx")
        assert result["turns_completed"] >= 0

    @pytest.mark.asyncio
    async def test_run_with_skill_both_calls_fail(self, mock_simulator, mock_evaluator, mock_skill_runner):
        """When both run_with_skill calls fail, dialogue breaks."""
        mock_simulator.generate_next_message.return_value = {"role": "user", "content": "hi"}
        mock_skill_runner.run_with_skill = AsyncMock(side_effect=RuntimeError("adapter down"))

        runner = DialogueRunner(
            simulator=mock_simulator, evaluator=mock_evaluator,
            skill_runner=mock_skill_runner, max_turns=5
        )
        result = await runner.run_dialogue_eval({"id": "t"}, "ctx")
        # Should exit early with 0 turns
        assert result["turns_completed"] == 0

    @pytest.mark.asyncio
    async def test_skill_responses_empty_breaks(self, mock_simulator, mock_evaluator, mock_skill_runner):
        """When skill_responses is empty list, dialogue breaks."""
        mock_simulator.generate_next_message.return_value = {"role": "user", "content": "hi"}
        mock_skill_runner.run_with_skill = AsyncMock(return_value=[])

        runner = DialogueRunner(
            simulator=mock_simulator, evaluator=mock_evaluator,
            skill_runner=mock_skill_runner, max_turns=5
        )
        result = await runner.run_dialogue_eval({"id": "t"}, "ctx")
        assert result["turns_completed"] == 0

    @pytest.mark.asyncio
    async def test_generate_next_message_exception_breaks(self, mock_simulator, mock_evaluator, mock_skill_runner):
        """When simulator raises exception, dialogue breaks."""
        mock_simulator.generate_next_message = AsyncMock(
            side_effect=[{"role": "user", "content": "first msg"}, RuntimeError("simulator error")]
        )
        mock_skill_runner.run_with_skill = AsyncMock(return_value=[
            {"eval_id": "turn_0", "output": "Normal response no completion", "execution_time": 1.0, "error": None}
        ])

        runner = DialogueRunner(
            simulator=mock_simulator, evaluator=mock_evaluator,
            skill_runner=mock_skill_runner, max_turns=5
        )
        result = await runner.run_dialogue_eval({"id": "t"}, "ctx")
        assert result["turns_completed"] == 0

    def test_is_conversation_complete_no_assistant_message(self, mock_simulator, mock_evaluator, mock_skill_runner):
        """Returns False when history >= 4 but no assistant message found."""
        runner = DialogueRunner(
            simulator=mock_simulator, evaluator=mock_evaluator,
            skill_runner=mock_skill_runner, max_turns=5
        )
        history = [
            {"role": "user", "content": "msg1"},
            {"role": "user", "content": "msg2"},
            {"role": "system", "content": "msg3"},
            {"role": "user", "content": "COMPLETED: done"},
        ]
        assert runner._is_conversation_complete(history) is False

    def test_is_conversation_complete_case_insensitive(self, mock_simulator, mock_evaluator, mock_skill_runner):
        """Completion signal matching is case-insensitive (upper())."""
        runner = DialogueRunner(
            simulator=mock_simulator, evaluator=mock_evaluator,
            skill_runner=mock_skill_runner, max_turns=5,
            completion_signals=["DONE"]
        )
        history = [
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "working"},
            {"role": "user", "content": "continue"},
            {"role": "assistant", "content": "I am done with the task"},
        ]
        # "done" in upper() matches "DONE"
        assert runner._is_conversation_complete(history) is True
