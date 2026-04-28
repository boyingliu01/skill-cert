import asyncio
from unittest.mock import AsyncMock, patch
import pytest
from yaml import safe_load
from engine.simulator import UserSimulator, mock_llm_callback
from pathlib import Path


@pytest.mark.asyncio
async def test_simulator_loads_profiles():
    """Test that the simulator properly loads user profiles from YAML config."""
    with patch('builtins.open', read_data='''
profiles:
  - name: "clear_intents"
    description: "User provides direct, clear requests with all necessary details upfront"
    initial_messages:
      - "I want to create a Python function that calculates the factorial of a number. Can you implement this?"
    follow_up_style: "structured"
    weight: 0.3
    
  - name: "vague_intents"
    description: "User gives unclear, incomplete requests that need clarification and guidance"
    initial_messages:
      - "I need something that processes data but I'm not sure how yet. Can you help me figure it out?"
    follow_up_style: "exploratory"
    weight: 0.5
    
  - name: "chaotic_intents"
    description: "User changes topic mid-conversation, goes off-track, introduces random tangents"
    initial_messages:
      - "By the way, can you show me how to implement a bubble sort? I was thinking about algorithms earlier..."
    follow_up_style: "disjointed"
    weight: 0.2
'''):
        with patch('yaml.safe_load') as mock_safe_load:
            config_data = {
                "profiles": [
                    {
                        "name": "clear_intents", 
                        "description": "Direct clear requests",
                        "initial_messages": ["Test message"],
                        "follow_up_style": "structured",
                        "weight": 0.3
                    },
                    {
                        "name": "vague_intents",
                        "description": "Unclear requests",
                        "initial_messages": ["Vague message"],
                        "follow_up_style": "exploratory",
                        "weight": 0.5
                    },
                    {
                        "name": "chaotic_intents",
                        "description": "Random topic changes",
                        "initial_messages": ["Chaotic message"],
                        "follow_up_style": "disjointed",
                        "weight": 0.2
                    }
                ]
            }
            mock_safe_load.return_value = config_data
            
            # Create simulator for each profile
            profiles_to_test = ["clear_intents", "vague_intents", "chaotic_intents"]
            
            for profile_name in profiles_to_test:
                mock_callback = AsyncMock()
                simulator = UserSimulator(
                    profile_name=profile_name,
                    seed=42,
                    llm_callback=mock_callback
                )
                
                # Check that profile is properly loaded
                assert simulator.profile_name == profile_name
                assert isinstance(simulator.profiles, dict)
                assert profile_name in simulator.profiles


@pytest.mark.asyncio
async def test_get_initial_message_deterministic():
    """Test that the same seed produces the same initial message."""
    with patch('builtins.open', read_data='''
profiles:
  - name: "clear_intents"
    description: "User provides direct, clear requests"
    initial_messages:
      - "First test message"
      - "Second test message"
      - "Third test message"
    follow_up_style: "structured"
    weight: 0.3
'''):
        with patch('yaml.safe_load') as mock_safe_load:
            config_data = {
                "profiles": [
                    {
                        "name": "clear_intents", 
                        "description": "Direct clear requests",
                        "initial_messages": ["First test message", "Second test message", "Third test message"],
                        "follow_up_style": "structured",
                        "weight": 0.3
                    }
                ]
            }
            mock_safe_load.return_value = config_data
            
            # Create simulators with the same seed
            mock_callback = AsyncMock()
            simulator1 = UserSimulator(
                profile_name="clear_intents",
                seed=123,
                llm_callback=mock_callback
            )
            
            mock_callback2 = AsyncMock()
            simulator2 = UserSimulator(
                profile_name="clear_intents",
                seed=123,
                llm_callback=mock_callback2
            )
            
            # Get initial messages
            initial_message1 = simulator1.get_initial_message()
            initial_message2 = simulator2.get_initial_message()
            
            # Should get the same message since same seed gives same RNG state
            assert initial_message1 == initial_message2
            
            # Check that history was updated properly for both
            assert len(simulator1.history) == 1
            assert len(simulator2.history) == 1
            assert simulator1.history[0]["role"] == "user"
            assert simulator2.history[0]["role"] == "user"
            assert simulator1.history[0]["content"] == simulator2.history[0]["content"]


@pytest.mark.asyncio
async def test_generate_next_message_with_mock_llm():
    """Test that next message generation works with mock LLM callback."""
    # Create an async mock for the llm_callback that returns different responses
    mock_callback = AsyncMock()
    mock_callback.return_value = "Mocked user follow-up message"
    
    # Mock the config loading
    with patch('builtins.open', read_data='''
profiles:
  - name: "clear_intents"
    description: "User provides direct, clear requests"
    initial_messages:
      - "Please implement a function to reverse a string"
    follow_up_style: "structured"
    weight: 0.3
'''):
        with patch('yaml.safe_load') as mock_safe_load:
            config_data = {
                "profiles": [
                    {
                        "name": "clear_intents", 
                        "description": "Direct clear requests",
                        "initial_messages": ["Please implement a function to reverse a string"],
                        "follow_up_style": "structured",
                        "weight": 0.3
                    }
                ]
            }
            mock_safe_load.return_value = config_data
            
            simulator = UserSimulator(
                profile_name="clear_intents",
                seed=42,
                llm_callback=mock_callback
            )
            
            # Get an initial message
            initial_msg = simulator.get_initial_message()
            
            # Test generating next message
            skill_response = "Here's a Python function to reverse a string: `def reverse_string(s): return s[::-1]`"
            next_message = await simulator.generate_next_message(skill_response)
            
            # Check that the callback was called
            assert mock_callback.called
            assert next_message == "Mocked user follow-up message"
            
            # Check that history was updated properly
            # Should have 3 messages: initial user msg, assistant msg, follow-up user msg
            assert len(simulator.history) == 3
            assert simulator.history[0]["role"] == "user"
            assert simulator.history[1]["role"] == "assistant"
            assert simulator.history[2]["role"] == "user"
            
            # Check that history truncation occurs after generating more messages
            mock_callback.reset_mock()
            mock_callback.return_value = "Another follow-up"
            
            # Add several exchanges to test truncation at 6 messages
            # We start with 3 messages, then each call adds (assistant, user) pair
            # After additing more messages and truncating to 6, we should end up with just the last 6
            for i in range(5):  # This will create additional conversations 
                skill_resp = f"This is response #{i+2}"
                await simulator.generate_next_message(skill_resp)
                # At each iteration: history has 3+2*i messages after each exchange, then truncated to at most 6
                assert len(simulator.history) <= 6  # Always maintained to be 6 or less
            
            # After all additions, we should have exactly 6 messages
            assert len(simulator.history) == 6
                        
            # Test that character truncation works - simpler approach
            truncation_test_mock = AsyncMock(return_value="Generated User Response")
            with patch('builtins.open', read_data='''
profiles:
  - name: "vague_intents"
    description: "User gives unclear, incomplete requests"
    initial_messages:
      - "Help me with code"
    follow_up_style: "exploratory" 
    weight: 0.5
'''):
                with patch('yaml.safe_load') as char_mock_safe_load:
                    char_mock_config = {
                        "profiles": [
                            {
                                "name": "vague_intents", 
                                "description": "Unclear requests",
                                "initial_messages": ["Help me with code"],
                                "follow_up_style": "exploratory",
                                "weight": 0.5
                            }
                        ]
                    }
                    char_mock_safe_load.return_value = char_mock_config
                    
                    simulator_trunc = UserSimulator(
                        profile_name="vague_intents",
                        seed=200,
                        llm_callback=truncation_test_mock
                    )
                    
                    # Add long assistant response to history manually to test truncation
                    long_content = "A" * 250  # More than 200 chars
                    simulator_trunc.history.append({
                        "role": "assistant",
                        "content": long_content
                    })
                    
                    # Add few more to make total history > 6 for truncation test
                    for i in range(5):
                        simulator_trunc.history.append({
                            "role": "user" if i % 2 == 0 else "assistant",
                            "content": f"Message {i}"
                        })
                    
                    # Force a new message generation to trigger truncation  
                    mock_callback_for_trunc = AsyncMock(return_value="Truncated Test Response")
                    simulator_trunc.llm_callback = mock_callback_for_trunc
                    
                    # Generate next message with a long response to trigger history processing
                    await simulator_trunc.generate_next_message("Long assistant response " + "B" * 250)
                    
                    # Validate that history was truncated to 6 max 
                    assert len(simulator_trunc.history) <= 6
                    
                    # And that some content was truncated
                    truncated_found = any("[truncated]" in msg["content"] for msg in simulator_trunc.history)
                    assert truncated_found  # Expect at least one message to have been truncated