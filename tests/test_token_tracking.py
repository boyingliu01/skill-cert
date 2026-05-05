"""Tests for real token tracking implementation.

These tests verify:
1. TokenUsage dataclass creation
2. Anthropic adapter extracting usage from API response
3. OpenAI adapter extracting usage from API response
4. Runner using real token counts
5. Token budget enforcement (violation when exceeded)
"""

import pytest
from unittest.mock import MagicMock, patch


# Test 1: TokenUsage dataclass creation
def test_token_usage_dataclass_creation():
    """TokenUsage dataclass should be importable and work correctly."""
    from adapters.base import TokenUsage
    
    # Test basic creation
    usage = TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150)
    assert usage.input_tokens == 100
    assert usage.output_tokens == 50
    assert usage.total_tokens == 150
    
    # Test to_dict method
    result = usage.to_dict()
    assert result == {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
    
    # Test from_dict class method
    usage2 = TokenUsage.from_dict({"input_tokens": 200, "output_tokens": 75, "total_tokens": 275})
    assert usage2.input_tokens == 200
    assert usage2.output_tokens == 75
    assert usage2.total_tokens == 275


def test_token_usage_default_values():
    """TokenUsage should have default values for backward compatibility."""
    from adapters.base import TokenUsage
    
    usage = TokenUsage()
    assert usage.input_tokens == 0
    assert usage.output_tokens == 0
    assert usage.total_tokens == 0


# Test 2: LLMResponse dataclass with token_usage
def test_llm_response_dataclass_creation():
    """LLMResponse should include token_usage field."""
    from adapters.base import LLMResponse, TokenUsage
    
    usage = TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150)
    response = LLMResponse(text="Hello world", token_usage=usage, latency_ms=1.5)
    
    assert response.text == "Hello world"
    assert response.token_usage == usage
    assert response.latency_ms == 1.5


def test_llm_response_backward_compatible():
    """LLMResponse should work when token_usage is None (backward compatible)."""
    from adapters.base import LLMResponse
    
    response = LLMResponse(text="Hello world")
    assert response.text == "Hello world"
    assert response.token_usage is None
    assert response.latency_ms == 0.0


def test_llm_response_to_dict():
    """LLMResponse should serialize to dict correctly."""
    from adapters.base import LLMResponse, TokenUsage
    
    usage = TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150)
    response = LLMResponse(text="Hello", token_usage=usage, latency_ms=2.0)
    
    result = response.to_dict()
    assert result["text"] == "Hello"
    assert result["token_usage"] == {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
    assert result["latency_ms"] == 2.0


# Test 3: Anthropic adapter extracting usage from API response
def test_anthropic_adapter_extracts_usage():
    """Anthropic adapter should extract usage from API response."""
    from adapters.anthropic_compat import AnthropicCompatAdapter
    
    adapter = AnthropicCompatAdapter(
        base_url="https://api.anthropic.com",
        api_key="test-key",
        model="claude-3-sonnet"
    )
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "content": [{"type": "text", "text": "Test response"}],
        "usage": {
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_read_input_tokens": 25
        }
    }
    
    with patch.object(adapter.session, 'post', return_value=mock_response):
        content, usage = adapter.chat_with_usage([{"role": "user", "content": "Hello"}])
        
        assert content == "Test response"
        assert usage["prompt_tokens"] == 100
        assert usage["completion_tokens"] == 50
        assert usage["total_tokens"] == 150


def test_anthropic_adapter_usage_fields():
    """Anthropic adapter should map correct field names."""
    from adapters.anthropic_compat import AnthropicCompatAdapter
    
    adapter = AnthropicCompatAdapter(
        base_url="https://api.anthropic.com",
        api_key="test-key",
        model="claude-3-sonnet"
    )
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "content": [{"type": "text", "text": "Response"}],
        "usage": {
            "input_tokens": 500,
            "output_tokens": 250,
            "cache_read_input_tokens": 100
        }
    }
    
    with patch.object(adapter.session, 'post', return_value=mock_response):
        content, usage = adapter.chat_with_usage([{"role": "user", "content": "Test"}])
        
        # Verify mapping is correct
        assert usage["prompt_tokens"] == 500
        assert usage["completion_tokens"] == 250
        assert usage["total_tokens"] == 750  # 500 + 250


# Test 4: OpenAI adapter extracting usage from API response  
def test_openai_adapter_extracts_usage():
    """OpenAI adapter should extract usage from API response."""
    from adapters.openai_compat import OpenAICompatAdapter
    
    adapter = OpenAICompatAdapter(
        base_url="https://api.openai.com",
        api_key="test-key",
        model="gpt-4"
    )
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Test response"}}],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150
        }
    }
    
    with patch.object(adapter.client, 'post', return_value=mock_response):
        content, usage = adapter.chat_with_usage([{"role": "user", "content": "Hello"}])
        
        assert content == "Test response"
        assert usage["prompt_tokens"] == 100
        assert usage["completion_tokens"] == 50
        assert usage["total_tokens"] == 150


def test_openai_adapter_usage_fields():
    """OpenAI adapter should map correct field names."""
    from adapters.openai_compat import OpenAICompatAdapter
    
    adapter = OpenAICompatAdapter(
        base_url="https://api.openai.com",
        api_key="test-key",
        model="gpt-4"
    )
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Response"}}],
        "usage": {
            "prompt_tokens": 1000,
            "completion_tokens": 500,
            "total_tokens": 1500
        }
    }
    
    with patch.object(adapter.client, 'post', return_value=mock_response):
        content, usage = adapter.chat_with_usage([{"role": "user", "content": "Test"}])
        
        # Verify mapping is correct
        assert usage["prompt_tokens"] == 1000
        assert usage["completion_tokens"] == 500
        assert usage["total_tokens"] == 1500


# Test 5: Runner using real token counts
class MockAdapterWithUsage:
    """Mock adapter that returns real token usage."""
    def __init__(self):
        self.model_name = "test-model"
        self.call_count = 0
        
    def chat(self, messages):
        return "Test response"
    
    def chat_with_usage(self, messages):
        self.call_count += 1
        usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        return f"Response {self.call_count}", usage


def test_runner_uses_real_token_counts():
    """Runner should use real token counts from adapter."""
    from engine.runner import EvalRunner
    
    runner = EvalRunner(max_concurrency=1, model_name="test-model")
    adapter = MockAdapterWithUsage()
    
    evals = [
        {
            "id": 1,
            "name": "test-eval",
            "category": "normal",
            "input": "test input",
            "assertions": []
        }
    ]
    
    results = runner.run_with_skill(evals, "/path/to/skill.md", adapter)
    
    assert len(results) == 1
    result = results[0]
    # Should use real tokens from chat_with_usage
    assert result["tokens_used"] == 150
    assert result["token_breakdown"]["prompt_tokens"] == 100
    assert result["token_breakdown"]["completion_tokens"] == 50
    assert result["token_breakdown"]["total_tokens"] == 150


def test_runner_total_tokens_accumulates():
    """Runner should accumulate total_tokens across all evals."""
    from engine.runner import EvalRunner
    
    runner = EvalRunner(max_concurrency=2, model_name="test-model")
    adapter = MockAdapterWithUsage()
    
    evals = [
        {"id": 1, "name": "eval-1", "category": "normal", "input": "test 1", "assertions": []},
        {"id": 2, "name": "eval-2", "category": "normal", "input": "test 2", "assertions": []},
    ]
    
    runner.run_with_skill(evals, "/path/to/skill.md", adapter)
    
    # Should accumulate: 150 + 150 = 300
    assert runner.total_tokens == 300


# Test 6: Token budget enforcement with real tokens
class MockTraceWithTokens:
    """Mock trace with real token data."""
    def __init__(self, tokens=0):
        self.tokens = tokens
        self.steps = 5
        self.tool_call_count = 3
        self.time_ms = 5000


def test_token_budget_enforcement_within_budget():
    """Token budget should pass when under limit."""
    from engine.envelope import EnvelopeChecker
    
    checker = EnvelopeChecker(token_budget=50000)
    trace = MockTraceWithTokens(tokens=30000)
    
    result = checker.check(trace)
    assert result.passed is True
    assert len(result.violations) == 0


def test_token_budget_enforcement_exceeded():
    """Token budget should fail when exceeded."""
    from engine.envelope import EnvelopeChecker
    
    checker = EnvelopeChecker(token_budget=50000)
    trace = MockTraceWithTokens(tokens=60000)
    
    result = checker.check(trace)
    assert result.passed is False
    assert any("token_budget exceeded" in v for v in result.violations)


def test_token_budget_enforcement_at_boundary():
    """Token budget should pass at exact boundary."""
    from engine.envelope import EnvelopeChecker
    
    checker = EnvelopeChecker(token_budget=50000)
    trace = MockTraceWithTokens(tokens=50000)
    
    result = checker.check(trace)
    assert result.passed is True


# Test 7: Backward compatibility - adapter without usage
class MockAdapterWithoutUsage:
    """Mock adapter without chat_with_usage method."""
    def __init__(self):
        self.model_name = "test-model"
        
    def chat(self, messages):
        return "Response without usage"


def test_runner_fallback_for_old_adapters():
    """Runner should fallback to estimation for old adapters without chat_with_usage."""
    from engine.runner import EvalRunner
    
    runner = EvalRunner(max_concurrency=1, model_name="test-model")
    adapter = MockAdapterWithoutUsage()
    
    evals = [
        {
            "id": 1,
            "name": "test-eval", 
            "category": "normal",
            "input": "test input",
            "assertions": []
        }
    ]
    
    # Need to patch to avoid actual API calls
    with patch.object(adapter, 'chat', return_value="Response without usage"):
        results = runner.run_with_skill(evals, "/path/to/skill.md", adapter)
    
    assert len(results) == 1
    result = results[0]
    # Should still have some token count (estimated from response length)
    assert result["tokens_used"] >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
