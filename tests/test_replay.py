import pytest
import asyncio
import tempfile
import json
import os
from unittest.mock import Mock
from engine.replay import HistoryReplay


@pytest.fixture
def mock_skill_runner():
    """Mock skill runner for testing."""
    runner = Mock()
    runner.run_with_skill = Mock()
    return runner


@pytest.fixture
def sample_session_file():
    """Create a temporary session file for testing."""
    session_data = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
        {"role": "user", "content": "How are you?"},
        {"role": "assistant", "content": "I'm doing well!"}
    ]
    
    temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.jsonl')
    for item in session_data:
        temp_file.write(json.dumps(item) + '\n')
    temp_file.close()
    
    yield temp_file.name
    os.unlink(temp_file.name)


def test_load_session_valid_file(sample_session_file):
    """Test loading a valid session file."""
    replay = HistoryReplay(Mock())  # We don't need the skill runner for this test
    
    session = replay.load_session(sample_session_file)
    
    assert len(session) == 4
    assert session[0]["role"] == "user"
    assert session[0]["content"] == "Hello"
    assert session[1]["role"] == "assistant"
    assert session[1]["content"] == "Hi there!"


def test_load_session_malformed_lines(caplog):
    """Test loading a session with some malformed lines."""
    # Create a temporary file with one good line and one bad line
    temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.jsonl')
    temp_file.write('{"role": "user", "content": "Hello"}\n')
    temp_file.write('{malformed_json}\n')  # Invalid JSON
    temp_file.write('{"role": "assistant", "content": "Hi"}\n')
    temp_file.close()
    
    try:
        replay = HistoryReplay(Mock())
        session = replay.load_session(temp_file.name)
        
        # Should have loaded 2 good records
        assert len(session) == 2
        assert session[0]["role"] == "user"
        assert session[1]["role"] == "assistant"
        
        # Should have logged a warning for malformed line
        assert "Skipping malformed" in caplog.text
    finally:
        os.unlink(temp_file.name)


@pytest.mark.asyncio
async def test_replay_session(mock_skill_runner):
    """Test replaying a session with mocked skill."""
    # Mock the skill runner to return predictable results
    def side_effect(inputs):
        # For each input, return a processed version
        return [f"Processed: {inp['input']}" for inp in inputs]
    
    mock_skill_runner.run_with_skill.side_effect = side_effect
    
    replay = HistoryReplay(mock_skill_runner)
    
    # Simulate a session with 2 user messages
    session_data = [
        {"role": "user", "content": "First message"},
        {"role": "assistant", "content": "First response"},
        {"role": "user", "content": "Second message"},
        {"role": "assistant", "content": "Second response"}
    ]
    
    results = await replay.replay_session(session_data, "Test context")
    
    # Should have processed the 2 user messages
    assert len(results) == 2
    
    # First result should correspond to first user message
    assert results[0]["user_message"] == "First message"
    assert results[0]["new_response"] == "Processed: First message"
    assert results[0]["context_length"] == 0  # No prior context initially
    
    # Second result should have more context
    assert results[1]["user_message"] == "Second message"
    assert results[1]["new_response"] == "Processed: Second message"
    assert results[1]["context_length"] == 2  # Has context of previous interaction


@pytest.mark.asyncio
async def test_replay_session_empty_conversation(mock_skill_runner):
    """Test replaying with empty or user-only session."""
    mock_skill_runner.run_with_skill.return_value = ["No response needed"]
    
    replay = HistoryReplay(mock_skill_runner)
    
    # Test with empty session
    results = await replay.replay_session([], "Test context")
    assert len(results) == 0
    
    # Test with only assistant messages
    session_data = [
        {"role": "assistant", "content": "Assistant only response"}
    ]
    results = await replay.replay_session(session_data, "Test context")
    assert len(results) == 0
    
    # Test with only user message
    session_data = [
        {"role": "user", "content": "Only user message"}
    ]
    results = await replay.replay_session(session_data, "Test context")
    assert len(results) == 1
    assert results[0]["user_message"] == "Only user message"