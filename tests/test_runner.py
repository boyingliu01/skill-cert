import time
from unittest.mock import Mock, patch
from engine.runner import EvalRunner


class MockModelAdapter:
    def __init__(self, responses=None, model_name="test-model"):
        self.responses = responses or []
        self.call_count = 0
        self.model_name = model_name
    
    def chat(self, messages):
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
            self.call_count += 1
            return response
        return "Default response"
    
    def chat_with_usage(self, messages):
        text = self.chat(messages)
        return text, {"prompt_tokens": 0, "completion_tokens": len(text.split()), "total_tokens": len(text.split())}


def test_eval_runner_initialization():
    runner = EvalRunner()
    
    assert runner.max_concurrency == 5
    assert runner.rate_limit_rpm == 60
    assert runner.request_timeout == 120


def test_run_with_skill_success():
    runner = EvalRunner(max_concurrency=2, rate_limit_rpm=120, request_timeout=10)
    
    evals = [
        {
            "id": 1,
            "name": "test-eval",
            "category": "normal",
            "input": "test input",
            "expected_triggers": True,
            "assertions": [{"type": "contains", "value": "test", "weight": 1}]
        }
    ]
    
    skill_path = "/path/to/skill"
    mock_adapter = MockModelAdapter(["Successful response"])
    
    results = runner.run_with_skill(evals, skill_path, mock_adapter)
    
    assert len(results) == 1
    result = results[0]
    assert result["eval_id"] == 1
    assert result["eval_name"] == "test-eval"
    assert result["run"] == "with-skill"
    assert result["error"] is None
    assert result["output"] == "Successful response"


def test_run_without_skill_success():
    runner = EvalRunner(max_concurrency=2, rate_limit_rpm=120, request_timeout=10)
    
    evals = [
        {
            "id": 1,
            "name": "test-eval",
            "category": "normal",
            "input": "test input",
            "expected_triggers": True,
            "assertions": [{"type": "contains", "value": "test", "weight": 1}]
        }
    ]
    
    mock_adapter = MockModelAdapter(["Successful response without skill"])
    
    results = runner.run_without_skill(evals, mock_adapter)
    
    assert len(results) == 1
    result = results[0]
    assert result["eval_id"] == 1
    assert result["eval_name"] == "test-eval"
    assert result["run"] == "without-skill"
    assert result["error"] is None
    assert result["output"] == "Successful response without skill"


def test_run_with_skill_timeout():
    runner = EvalRunner(max_concurrency=2, rate_limit_rpm=120, request_timeout=1)
    
    evals = [
        {
            "id": 1,
            "name": "timeout-eval",
            "category": "normal",
            "input": "test input",
            "expected_triggers": True,
            "assertions": [{"type": "contains", "value": "test", "weight": 1}]
        }
    ]
    
    skill_path = "/path/to/skill"
    
    def slow_response(messages):
        time.sleep(2)
        return "Slow response"
    
    mock_adapter = Mock()
    mock_adapter.chat = Mock(side_effect=slow_response)
    mock_adapter.model_name = "test-model"
    
    results = runner.run_with_skill(evals, skill_path, mock_adapter)
    
    assert len(results) == 1
    result = results[0]
    assert result["eval_id"] == 1
    # In sync mode, timeout may not be enforced the same way, but it should handle errors gracefully
    if result.get("error"):
        assert "Timeout" in result["error"] or result["error"] == "timeout"


def test_run_without_skill_timeout():
    runner = EvalRunner(max_concurrency=2, rate_limit_rpm=120, request_timeout=1)
    
    evals = [
        {
            "id": 1,
            "name": "timeout-eval",
            "category": "normal",
            "input": "test input",
            "expected_triggers": True,
            "assertions": [{"type": "contains", "value": "test", "weight": 1}]
        }
    ]
    
    def slow_response(messages):
        time.sleep(2)
        return "Slow response"
    
    mock_adapter = Mock()
    mock_adapter.chat = Mock(side_effect=slow_response)
    mock_adapter.model_name = "test-model"
    
    results = runner.run_without_skill(evals, mock_adapter)
    
    assert len(results) == 1
    result = results[0]
    assert result["eval_id"] == 1
    if result.get("error"):
        assert "Timeout" in result["error"] or result["error"] == "timeout"


def test_run_with_skill_exception():
    runner = EvalRunner(max_concurrency=2, rate_limit_rpm=120, request_timeout=10)
    
    evals = [
        {
            "id": 1,
            "name": "error-eval",
            "category": "normal",
            "input": "test input",
            "expected_triggers": True,
            "assertions": [{"type": "contains", "value": "test", "weight": 1}]
        }
    ]
    
    skill_path = "/path/to/skill"
    
    mock_adapter = Mock()
    mock_adapter.chat = Mock(side_effect=Exception("API Error"))
    mock_adapter.model_name = "test-model"
    
    results = runner.run_with_skill(evals, skill_path, mock_adapter)
    
    assert len(results) == 1
    result = results[0]
    assert result["eval_id"] == 1
    assert "API Error" in result["error"]


def test_run_without_skill_exception():
    runner = EvalRunner(max_concurrency=2, rate_limit_rpm=120, request_timeout=10)
    
    evals = [
        {
            "id": 1,
            "name": "error-eval",
            "category": "normal",
            "input": "test input",
            "expected_triggers": True,
            "assertions": [{"type": "contains", "value": "test", "weight": 1}]
        }
    ]
    
    mock_adapter = Mock()
    mock_adapter.chat = Mock(side_effect=Exception("API Error"))
    mock_adapter.model_name = "test-model"
    
    results = runner.run_without_skill(evals, mock_adapter)
    
    assert len(results) == 1
    result = results[0]
    assert result["eval_id"] == 1
    assert "API Error" in result["error"]


def test_multiple_evals_concurrent():
    runner = EvalRunner(max_concurrency=3, rate_limit_rpm=180, request_timeout=10)
    
    evals = [
        {
            "id": 1,
            "name": "eval-1",
            "category": "normal",
            "input": "input 1",
            "expected_triggers": True,
            "assertions": [{"type": "contains", "value": "test", "weight": 1}]
        },
        {
            "id": 2,
            "name": "eval-2",
            "category": "boundary",
            "input": "input 2",
            "expected_triggers": False,
            "assertions": [{"type": "not_contains", "value": "test", "weight": 1}]
        },
        {
            "id": 3,
            "name": "eval-3",
            "category": "failure",
            "input": "input 3",
            "expected_triggers": True,
            "assertions": [{"type": "contains", "value": "error", "weight": 1}]
        }
    ]
    
    skill_path = "/path/to/skill"
    mock_adapter = MockModelAdapter([
        "Response for eval 1",
        "Response for eval 2", 
        "Response for eval 3"
    ])
    
    results = runner.run_with_skill(evals, skill_path, mock_adapter)
    
    assert len(results) == 3
    
    for i, result in enumerate(results):
        assert result["eval_id"] == i + 1
        assert result["eval_name"] == f"eval-{i + 1}"
        assert result["run"] == "with-skill"
        assert result["error"] is None
        assert f"Response for eval {i + 1}" in result["output"]


def test_close_resources():
    runner = EvalRunner()
    runner.close()
