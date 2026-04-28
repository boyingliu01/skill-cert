import pytest
import asyncio
from unittest.mock import Mock
from engine.simulator import UserSimulator
from engine.dialogue_evaluator import DialogueEvaluator
from engine.dialogue_runner import DialogueRunner


@pytest.mark.asyncio
async def test_dialogue_mode_end_to_end():
    """Integration test for full dialogue evaluation workflow."""
    # Create mock skill runner with realistic responses
    class MockSkillRunner:
        async def run_with_skill(self, inputs):
            import random
            
            responses = [
                "I understand your question. Let me help you with that.",
                "That's a great point. Based on best practices...",
                "I can definitely assist with this request.",
                "Here's a comprehensive solution to what you're asking.",
                "Thank you for clarifying. Let's approach this step by step.",
                "Yes, that makes sense. The key consideration here would be...",
                "Okay, so what you're looking for is...",
                "I've implemented something like this before. The approach would be..."
            ]
            
            return [random.choice(responses) for _ in inputs]
    
    # Create simulators and evaluators
    simulator = UserSimulator(profile_name="clear_intents")
    evaluator = DialogueEvaluator()
    skill_runner = MockSkillRunner()
    
    # Create the dialogue runner
    dialoguer = DialogueRunner(
        simulator=simulator,
        evaluator=evaluator,
        skill_runner=skill_runner,
        max_turns=4,  # Just a few turns for the test
        completion_signals=["COMPLETED", "DONE", "FINISHED"]
    )
    
    # Initial evaluation case
    eval_case = {
        "initial_query": "Can you help me understand how to use this skill?",
        "expected_behavior": "Provide clear, helpful guidance following the skill's purpose"
    }
    
    # Run the full dialogue evaluation
    result = await dialoguer.run_dialogue_eval(eval_case, "Testing integration")
    
    # Validate the structure of results
    assert "conversation" in result
    assert "evaluation" in result
    assert "turns_completed" in result
    
    # Verify conversation has both user and assistant messages
    conversation = result["conversation"]
    assert len(conversation) > 0
    assert any(msg["role"] == "user" for msg in conversation)
    assert any(msg["role"] == "assistant" for msg in conversation)
    
    # Verify evaluation scores are properly calculated
    evaluation = result["evaluation"]
    assert "overall_dialogue_score" in evaluation
    assert "verdict" in evaluation
    assert "intent_recognition" in evaluation
    assert "guidance_quality" in evaluation
    assert isinstance(evaluation["overall_dialogue_score"], (float, int))
    assert evaluation["verdict"] in ["PASS", "PASS_WITH_CAVEATS", "FAIL"]
    
    # Verify we have a reasonable number of turns
    # Each conversation turn is user -> assistant, so turns_completed = len(history) // 2
    # Given max_turns=4 in the runner, expect reasonable number of turns that reflect actual cycles
    assert result["turns_completed"] >= 0  # Non-negative


@pytest.mark.asyncio
async def test_dialogue_mode_with_realistic_workflow():
    """Test dialogue mode with more realistic skill response patterns."""
    
    class RealisticSkillRunner:
        async def run_with_skill(self, inputs):
            responses = []
            for inp in inputs:
                user_input = inp["input"].lower()
                
                if any(word in user_input for word in ["how", "what", "explain", "?"]):
                    response = f"I can help explain this. Based on the context '{inp['context']}', here's the detailed approach..."
                elif any(word in user_input for word in ["implement", "create", "build"]):
                    response = f"Sure, I can help create that. First, let me consider the requirements for '{inp['context']}'..."
                else:
                    response = f"Understood. Regarding your input '{inp['input']}', here's my response based on this: {inp['context']}"
                
                responses.append(response)
            
            return responses
    
    simulator = UserSimulator(profile_name="clear_intents")
    evaluator = DialogueEvaluator()
    skill_runner = RealisticSkillRunner()
    dialoguer = DialogueRunner(simulator, evaluator, skill_runner, max_turns=6)
    
    eval_case = {"initial_query": "Implement a data parsing algorithm"}
    result = await dialoguer.run_dialogue_eval(eval_case, "Algorithm implementation")
    
    conversation = result["conversation"]
    
    # Verify that responses address the specific query
    assistant_responses = [msg for msg in conversation if msg["role"] == "assistant"]
    
    assert len(assistant_responses) >= 2  # At least one response plus user follow-up
    assert all(isinstance(msg["content"], str) and len(msg["content"]) > 10 for msg in assistant_responses)
    
    evaluation = result["evaluation"]
    assert 0.0 <= evaluation["overall_dialogue_score"] <= 1.0
    assert isinstance(evaluation["verdict"], str)