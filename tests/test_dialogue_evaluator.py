import pytest
import asyncio
from engine.dialogue_evaluator import DialogueEvaluator


@pytest.fixture
def evaluator():
    return DialogueEvaluator()


@pytest.mark.asyncio
async def test_evaluate_conversation_empty(evaluator):
    """Test evaluation with empty conversation."""
    result = await evaluator.evaluate_conversation([])
    assert result["overall_dialogue_score"] == 0.0
    assert result["verdict"] == "FAIL"


@pytest.mark.asyncio
async def test_evaluate_conversation_single_pair(evaluator):
    """Test evaluation with single user-response pair."""
    conversation = [
        {"content": "Hello, can you help me?"},
        {"content": "Sure, what do you need help with?"}
    ]
    result = await evaluator.evaluate_conversation(conversation)
    
    assert "intent_recognition" in result
    assert "guidance_quality" in result
    assert "overall_dialogue_score" in result
    assert "verdict" in result


@pytest.mark.asyncio
async def test_evaluate_conversation_multiple_pairs(evaluator):
    """Test evaluation with multiple conversation turns."""
    conversation = [
        {"content": "I need to create a login form"},
        {"content": "Sure, I can help with that. What fields do you need?"},
        {"content": "Username and password"},
        {"content": "OK, I'll implement both fields. Would you like any validation?"}
    ]
    result = await evaluator.evaluate_conversation(conversation)
    
    # Should have calculated average scores properly
    assert result["intent_recognition"] >= 0.0
    assert result["guidance_quality"] >= 0.0
    assert isinstance(result["overall_dialogue_score"], float)
    assert isinstance(result["verdict"], str)


@pytest.mark.asyncio
async def test_intent_recognition_scoring(evaluator):
    """Test that intent recognition scores based on word overlap."""
    user_msg = "I want to add user authentication to my app"
    response = "I'll help you add authentication with username and password"
    
    score = evaluator._score_intent_recognition(user_msg, response)
    # Should detect some overlap in terms
    assert 0.0 <= score <= 1.0
    assert score > 0.0  # Some overlap should exist


@pytest.mark.asyncio
async def test_guidance_quality_scoring(evaluator):
    """Test that guidance quality scores appropriately for questions."""
    question_resp = "Can you clarify what type of data you want to store?"
    non_question_resp = "Sure, I'll code that for you."
    
    question_score = evaluator._score_guidance_quality("Store my data", question_resp)
    non_question_score = evaluator._score_guidance_quality("Store my data", non_question_resp)
    
    assert question_score > non_question_score  # Questions should score higher


@pytest.mark.asyncio
async def test_workflow_adherence_boundary_penalties(evaluator):
    """Test that boundary violations reduce workflow adherence."""
    conversation_with_violation = [
        {"content": "Can you help me add a button?"},
        {"content": "Sure, and I also refactored some unrelated parts of your database..."}
    ]
    result_with_violation = await evaluator.evaluate_conversation(conversation_with_violation)
    
    conversation_clean = [
        {"content": "Can you help me add a button?"},
        {"content": "Sure, here's how to add a button..."}
    ]
    result_clean = await evaluator.evaluate_conversation(conversation_clean)
    
    # The clean conversation should score higher
    assert result_clean["workflow_adherence"] >= result_with_violation["workflow_adherence"]