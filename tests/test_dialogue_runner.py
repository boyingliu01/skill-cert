import pytest
import asyncio
from unittest.mock import Mock
from engine.simulator import UserSimulator
from engine.dialogue_evaluator import DialogueEvaluator
from engine.dialogue_runner import DialogueRunner


@pytest.fixture
def mock_skill_runner():
    """Mock skill runner for testing."""
    runner = Mock()
    runner.run_with_skill = Mock()
    return runner


@pytest.fixture
def evaluator():
    return DialogueEvaluator()


@pytest.fixture
def simulator():
    return UserSimulator(profile_name="clear_intents")


@pytest.mark.asyncio
async def test_run_dialogue_eval_basic(simulator, evaluator, mock_skill_runner):
    """Test basic dialogue evaluation run."""
    # Setup mock return value
    mock_skill_runner.run_with_skill.return_value = ["Test response"]
    
    runner = DialogueRunner(
        simulator=simulator,
        evaluator=evaluator,
        skill_runner=mock_skill_runner,
        max_turns=2
    )
    
    eval_case = {
        "initial_query": "Test query"
    }
    
    result = await runner.run_dialogue_eval(eval_case, "Test context")
    
    # Verify the result structure
    assert "conversation" in result
    assert "evaluation" in result
    assert "turns_completed" in result
    assert len(result["conversation"]) >= 2  # At least user + AI response
    assert isinstance(result["turns_completed"], int)


@pytest.mark.asyncio
async def test_run_dialogue_eval_completes_on_signal(simulator, evaluator, mock_skill_runner):
    """Test dialogue evaluation completes when completion signal is detected."""
    # First call returns normal response, second indicates completion
    mock_skill_runner.run_with_skill.side_effect = [
        ["Working on it..."],  # First response
        ["COMPLETED: Here is what you asked for"]  # Completion signal
    ]
    
    r = DialogueRunner(
        simulator=simulator,
        evaluator=evaluator,
        skill_runner=mock_skill_runner,
        max_turns=5  # Higher max turns
    )
    
    eval_case = {}
    result = await r.run_dialogue_eval(eval_case, "Test context")
    
    # Should have stopped early due to completion signal
    assert result["turns_completed"] <= 2
    # Conversation should end with the completion response
    assert "COMPLETED:" in result["conversation"][-1]["content"]


@pytest.mark.asyncio
async def test_is_conversation_complete_various_signals(simulator, evaluator, mock_skill_runner):
    """Test that completion signals work correctly."""
    runner = DialogueRunner(
        simulator=simulator,
        evaluator=evaluator,
        skill_runner=mock_skill_runner
    )
    
    # Test various completion signals
    assert runner._is_conversation_complete([
        {"role": "user", "content": "test"},
        {"role": "assistant", "content": "working..."},
        {"role": "user", "content": "continue"},
        {"role": "assistant", "content": "COMPLETED: Finished!"}
    ])
    
    assert runner._is_conversation_complete([
        {"role": "user", "content": "test"},
        {"role": "assistant", "content": "working..."},
        {"role": "user", "content": "continue"},
        {"role": "assistant", "content": "HERE IS THE SOLUTION"}
    ])
    
    # Should be falsy for short conversations
    assert not runner._is_conversation_complete([{"role": "user", "content": "hi"}])
    
    # Should be falsy for messages without completion signals
    assert not runner._is_conversation_complete([
        {"role": "user", "content": "test"},
        {"role": "assistant", "content": "working..."},
        {"role": "user", "content": "continue"},
        {"role": "assistant", "content": "still working..."}
    ])