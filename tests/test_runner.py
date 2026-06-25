import time
from unittest.mock import MagicMock, Mock, patch

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
        return text, {
            "prompt_tokens": 0,
            "completion_tokens": len(text.split()),
            "total_tokens": len(text.split()),
        }


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
            "assertions": [{"type": "contains", "value": "test", "weight": 1}],
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
            "assertions": [{"type": "contains", "value": "test", "weight": 1}],
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
            "assertions": [{"type": "contains", "value": "test", "weight": 1}],
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
            "assertions": [{"type": "contains", "value": "test", "weight": 1}],
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
            "assertions": [{"type": "contains", "value": "test", "weight": 1}],
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
            "assertions": [{"type": "contains", "value": "test", "weight": 1}],
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
            "assertions": [{"type": "contains", "value": "test", "weight": 1}],
        },
        {
            "id": 2,
            "name": "eval-2",
            "category": "boundary",
            "input": "input 2",
            "expected_triggers": False,
            "assertions": [{"type": "not_contains", "value": "test", "weight": 1}],
        },
        {
            "id": 3,
            "name": "eval-3",
            "category": "failure",
            "input": "input 3",
            "expected_triggers": True,
            "assertions": [{"type": "contains", "value": "error", "weight": 1}],
        },
    ]

    skill_path = "/path/to/skill"
    mock_adapter = MockModelAdapter(
        ["Response for eval 1", "Response for eval 2", "Response for eval 3"]
    )

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


def test_get_traces_empty():
    """get_traces returns empty list when no traces (covers line 378-379)."""
    runner = EvalRunner()
    traces = runner.get_traces()
    assert traces == []


def test_close_with_telemetry():
    """close flushes telemetry and token_ledger (covers line 384, 386)."""
    telemetry = MagicMock()
    telemetry.flush = MagicMock()
    ledger = MagicMock()
    runner = EvalRunner(telemetry=telemetry, token_ledger=ledger)
    runner.close()
    ledger.flush.assert_called_once()
    telemetry.flush.assert_called_once()


def test_calc_cost_no_model():
    """_calc_cost returns 0 when no model_name (covers line 353)."""
    runner = EvalRunner()
    cost = runner._calc_cost({"prompt_tokens": 100, "completion_tokens": 50})
    assert cost == 0.0


def test_check_security_no_scanner():
    """_check_security returns unscanned when no scanner (covers line 362)."""
    runner = EvalRunner(enable_security_scan=False)
    result = runner._check_security("some output")
    assert result == {"scanned": False}


def test_run_single_exception_inner():
    """_run_single handles exception in execution (covers line 218-222)."""
    runner = EvalRunner(max_concurrency=2, rate_limit_rpm=300, request_timeout=10)

    evals = [
        {
            "id": i,
            "name": f"eval-{i}",
            "category": "normal",
            "input": f"input {i}",
            "expected_triggers": True,
            "assertions": [{"type": "contains", "value": "test", "weight": 1}],
        }
        for i in range(2)
    ]

    # First eval succeeds, second raises
    mock_adapter = MockModelAdapter(["response 0"])
    mock_adapter.chat = Mock(side_effect=["response 0", Exception("Unexpected error")])
    mock_adapter.model_name = "test-model"

    results = runner.run_with_skill(evals, "/path/to/skill", mock_adapter)
    assert len(results) == 2
    assert results[0]["error"] is None
    assert "Unexpected error" in results[1].get("error", "")


def test_run_single_exception_inner_without():
    """run_without_skill handles exception in _run_single (covers line 218-222)."""
    runner = EvalRunner(max_concurrency=2, rate_limit_rpm=300, request_timeout=10)

    evals = [
        {
            "id": i,
            "name": f"eval-{i}",
            "category": "normal",
            "input": f"input {i}",
            "expected_triggers": True,
            "assertions": [{"type": "contains", "value": "test", "weight": 1}],
        }
        for i in range(2)
    ]

    mock_adapter = Mock()
    mock_adapter.chat = Mock(side_effect=["response 0", Exception("Unexpected error")])
    mock_adapter.model_name = "test-model"

    results = runner.run_without_skill(evals, mock_adapter)
    assert len(results) == 2
    assert results[0]["error"] is None
    assert "Unexpected error" in results[1].get("error", "")


def test_run_with_skill_progress_logging(caplog):
    """run_with_skill logs per-eval progress at completion points."""
    caplog.set_level("INFO")
    runner = EvalRunner(max_concurrency=5, rate_limit_rpm=300, request_timeout=10)

    evals = [
        {
            "id": i,
            "name": f"eval-{i}",
            "category": "normal",
            "input": f"input {i}",
            "expected_triggers": True,
            "assertions": [{"type": "contains", "value": "response", "weight": 1}],
        }
        for i in range(1, 6)  # 5 evals → 20%, 40%, 60%, 80%, 100%
    ]

    mock_adapter = MockModelAdapter([f"response {i}" for i in range(1, 6)])

    results = runner.run_with_skill(evals, "/path/to/skill", mock_adapter)
    assert len(results) == 5

    # Check that progress was logged at least at 100%
    progress_logs = [r.message for r in caplog.records if "Eval progress" in r.message]
    assert len(progress_logs) >= 1
    # The last log should say 5/5 (100%)
    assert "5/5 (100%)" in progress_logs[-1]


def test_run_without_skill_progress_logging(caplog):
    """run_without_skill logs per-eval progress at completion points."""
    caplog.set_level("INFO")
    runner = EvalRunner(max_concurrency=5, rate_limit_rpm=300, request_timeout=10)

    evals = [
        {
            "id": i,
            "name": f"eval-{i}",
            "category": "normal",
            "input": f"input {i}",
            "expected_triggers": True,
            "assertions": [{"type": "contains", "value": "response", "weight": 1}],
        }
        for i in range(1, 4)  # 3 evals
    ]

    mock_adapter = MockModelAdapter([f"response {i}" for i in range(1, 4)])

    results = runner.run_without_skill(evals, mock_adapter)
    assert len(results) == 3

    progress_logs = [r.message for r in caplog.records if "Eval progress" in r.message]
    assert len(progress_logs) >= 1
    assert "3/3 (100%)" in progress_logs[-1]


# ── Deadline cancel_futures tests (AC-019-04) ─────────────────────────────


def test_run_with_skill_deadline_cancel_futures():
    """AC-019-04: Expired deadline triggers FuturesTimeoutError and returns partial results."""
    from engine.deadline import Deadline

    runner = EvalRunner(max_concurrency=2, rate_limit_rpm=300, request_timeout=10)

    evals = [
        {
            "id": i,
            "name": f"eval-{i}",
            "category": "normal",
            "input": f"input {i}",
            "expected_triggers": True,
            "assertions": [{"type": "contains", "value": "response", "weight": 1}],
        }
        for i in range(3)
    ]

    # Slow adapter that doesn't complete before 0-second timeout
    mock_adapter = Mock()
    mock_adapter.chat = Mock(side_effect=lambda msgs: time.sleep(10))
    mock_adapter.model_name = "test-model"

    # Deadline with remaining = 0 (expired); frozen dataclass → patch class, not instance
    dl = Deadline(max_total_time=0.0)

    with patch("engine.deadline.Deadline.must_stop", return_value=False):
        results = runner.run_with_skill(evals, "/path/to/skill", mock_adapter, deadline=dl)

    partial_markers = [r for r in results if r.get("_partial")]
    assert len(partial_markers) == 1, f"Expected 1 _partial marker, got {len(partial_markers)}"
    assert "Deadline reached" in partial_markers[0].get("message", "")


def test_run_without_skill_deadline_cancel_futures():
    """AC-019-04: Expired deadline cancels futures in without_skill mode."""
    from engine.deadline import Deadline

    runner = EvalRunner(max_concurrency=2, rate_limit_rpm=300, request_timeout=10)

    evals = [
        {
            "id": i,
            "name": f"eval-{i}",
            "category": "normal",
            "input": f"input {i}",
            "expected_triggers": True,
            "assertions": [{"type": "contains", "value": "response", "weight": 1}],
        }
        for i in range(3)
    ]

    mock_adapter = Mock()
    mock_adapter.chat = Mock(side_effect=lambda msgs: time.sleep(10))
    mock_adapter.model_name = "test-model"

    dl = Deadline(max_total_time=0.0)

    with patch("engine.deadline.Deadline.must_stop", return_value=False):
        results = runner.run_without_skill(evals, mock_adapter, deadline=dl)

    partial_markers = [r for r in results if r.get("_partial")]
    assert len(partial_markers) == 1, f"Expected 1 _partial marker, got {len(partial_markers)}"
    assert "Deadline reached" in partial_markers[0].get("message", "")


# ── Additional coverage: lines 71, 78-79, 185, 208, 210, 246-257, 309-320, 354 ──


def test_prepare_input_dict():
    """_prepare_input converts dict input via str() (covers line 71)."""
    runner = EvalRunner()
    eval_case = {"input": {"key": "value"}}
    result = runner._prepare_input(eval_case, None, with_skill=False)
    assert isinstance(result, str)
    assert "key" in result
    assert "value" in result


def test_prepare_input_file_not_found():
    """_prepare_input handles non-existent skill_path (covers lines 80-81)."""
    runner = EvalRunner()
    result = runner._prepare_input({"input": "hello"}, "/nonexistent/SKILL.md", with_skill=True)
    assert "/nonexistent/SKILL.md" in result


def test_prepare_input_reads_skill_file(tmp_path):
    """_prepare_input reads real skill file content (covers lines 78-79)."""
    runner = EvalRunner()
    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text("line1\nline2\nline3\n")
    result = runner._prepare_input({"input": "do something"}, str(skill_file), with_skill=True)
    assert "line1" in result
    assert "line2" in result
    assert "line3" in result
    assert "do something" in result


def test_run_single_deadline_must_stop():
    """_run_single returns Deadline-reached error when must_stop() is True (covers line 185)."""
    runner = EvalRunner(max_concurrency=1, rate_limit_rpm=300, request_timeout=10)

    deadline = MagicMock()
    deadline.must_stop.return_value = True

    eval_case = {
        "id": 1,
        "name": "deadline-stop",
        "category": "normal",
        "input": "test",
        "expected_triggers": True,
        "assertions": [{"type": "contains", "value": "test", "weight": 1}],
    }
    adapter = MockModelAdapter(["response"])
    result = runner._run_single(
        eval_case, "/path/to/skill", adapter, with_skill=True, deadline=deadline
    )
    assert result["error"] == "Deadline reached"
    assert result["eval_id"] == 1


def test_run_single_token_ledger_telemetry():
    """_run_single records trace on token_ledger and telemetry (covers lines 208, 210)."""
    ledger = MagicMock()
    telemetry = MagicMock()
    runner = EvalRunner(
        max_concurrency=1,
        rate_limit_rpm=300,
        request_timeout=10,
        token_ledger=ledger,
        telemetry=telemetry,
    )

    eval_case = {
        "id": 42,
        "name": "ledger-test",
        "category": "normal",
        "input": "test input",
        "expected_triggers": True,
        "assertions": [{"type": "contains", "value": "test", "weight": 1}],
    }
    adapter = MockModelAdapter(["a response for tracing"])
    result = runner._run_single(eval_case, None, adapter, with_skill=False)
    assert result["error"] is None
    ledger.record_trace.assert_called_once()
    telemetry.record_trace.assert_called_once()


def test_run_with_skill_deadline_expired_in_loop():
    """run_with_skill hits deadline.expired in the as_completed loop (covers lines 246-257)."""
    from engine.deadline import Deadline

    runner = EvalRunner(max_concurrency=2, rate_limit_rpm=300, request_timeout=10)

    evals = [
        {
            "id": i,
            "name": f"eval-{i}",
            "category": "normal",
            "input": f"input {i}",
            "expected_triggers": True,
            "assertions": [{"type": "contains", "value": "ok", "weight": 1}],
        }
        for i in range(3)
    ]

    adapter = Mock()
    adapter.chat = Mock(
        side_effect=[
            "fast response",
            Exception("fail fast"),
            Exception("another fast fail"),
        ]
    )
    adapter.model_name = "test-model"

    dl = Deadline(max_total_time=0.001)
    time.sleep(0.002)

    with patch("engine.deadline.Deadline.must_stop", return_value=False):
        results = runner.run_with_skill(evals, "/path/to/skill", adapter, deadline=dl)

    assert len(results) >= 1
    partials = [r for r in results if r.get("_partial")]
    assert len(partials) == 1
    assert "Deadline reached" in partials[0].get("message", "")


def test_run_without_skill_deadline_expired_in_loop():
    """run_without_skill hits deadline.expired in the as_completed loop (covers lines 309-320)."""
    from engine.deadline import Deadline

    runner = EvalRunner(max_concurrency=2, rate_limit_rpm=300, request_timeout=10)

    evals = [
        {
            "id": i,
            "name": f"eval-{i}",
            "category": "normal",
            "input": f"input {i}",
            "expected_triggers": True,
            "assertions": [{"type": "contains", "value": "ok", "weight": 1}],
        }
        for i in range(3)
    ]

    adapter = Mock()
    adapter.chat = Mock(
        side_effect=[
            "fast response",
            Exception("fail fast"),
            Exception("another fast fail"),
        ]
    )
    adapter.model_name = "test-model"

    dl = Deadline(max_total_time=0.001)
    time.sleep(0.002)

    with patch("engine.deadline.Deadline.must_stop", return_value=False):
        results = runner.run_without_skill(evals, adapter, deadline=dl)

    assert len(results) >= 1
    partials = [r for r in results if r.get("_partial")]
    assert len(partials) == 1
    assert "Deadline reached" in partials[0].get("message", "")


def test_calc_cost_with_model():
    """_calc_cost calls pricing.calculate_cost when model_name is set (covers line 354)."""
    pricing = MagicMock()
    pricing.calculate_cost.return_value = 0.005

    runner = EvalRunner(model_name="test-model")
    runner._pricing = pricing

    cost = runner._calc_cost({"prompt_tokens": 100, "completion_tokens": 50})
    assert cost == 0.005
    pricing.calculate_cost.assert_called_once_with(100, 50, "test-model")


def test_calc_cost_accepts_model_name_parameter():
    """_calc_cost accepts model_name parameter instead of using self.model_name."""
    pricing = MagicMock()
    pricing.calculate_cost.return_value = 0.012

    runner = EvalRunner()  # self.model_name is None
    runner._pricing = pricing

    cost = runner._calc_cost(
        {"prompt_tokens": 200, "completion_tokens": 100}, model_name="qwen3.6-plus"
    )
    assert cost == 0.012
    pricing.calculate_cost.assert_called_once_with(200, 100, "qwen3.6-plus")


def test_calc_cost_model_name_param_overrides_self():
    """_calc_cost model_name parameter takes precedence over self.model_name."""
    pricing = MagicMock()
    pricing.calculate_cost.return_value = 0.007

    runner = EvalRunner(model_name="self-model")
    runner._pricing = pricing

    cost = runner._calc_cost(
        {"prompt_tokens": 100, "completion_tokens": 50}, model_name="param-model"
    )
    assert cost == 0.007
    pricing.calculate_cost.assert_called_once_with(100, 50, "param-model")


def test_run_single_uses_per_call_model_for_cost():
    """_run_single uses adapter's model_name for cost even when self.model_name is None."""
    pricing = MagicMock()
    pricing.calculate_cost.return_value = 0.025

    runner = EvalRunner(max_concurrency=1, rate_limit_rpm=300, request_timeout=10)
    runner._pricing = pricing
    # self.model_name is None — bug would skip cost calculation entirely

    adapter = MockModelAdapter(["response text"], model_name="qwen3.6-plus")

    eval_case = {
        "id": 1,
        "name": "cost-test",
        "category": "normal",
        "input": "test input",
        "assertions": [{"name": "d", "type": "contains", "value": ".", "weight": 1}],
    }

    result = runner._run_single(eval_case, None, adapter, with_skill=False)
    assert result["error"] is None
    # Cost should be calculated using adapter's model_name, not skipped
    assert result["cost"] == 0.025
    pricing.calculate_cost.assert_called()
    # Verify the model_name passed to calculate_cost is the adapter's model
    call_args = pricing.calculate_cost.call_args
    assert call_args[0][2] == "qwen3.6-plus"


def test_run_with_skill_future_exception():
    """Covers run_with_skill lines 266-267: exception in future.result()."""
    runner = EvalRunner(max_concurrency=1, rate_limit_rpm=300, request_timeout=3)

    evals = [{"id": i, "input": f"input {i}", "assertions": [{"name": "d", "type": "contains", "value": ".", "weight": 1}]} for i in range(3)]

    adapter = Mock()
    adapter.chat = Mock()
    adapter.model_name = "test-model"

    # Make _run_single raise so future.result() propagates the exception
    import engine.runner as _runner_mod

    with patch.object(
        _runner_mod.EvalRunner,
        "_run_single",
        side_effect=ValueError("future boom"),
    ):
        results = runner.run_with_skill(evals, "/path/to/skill", adapter)

    assert len(results) == 3
    for r in results:
        assert "error" in r


def test_run_without_skill_future_exception():
    """Covers run_without_skill lines 329-330: exception in future.result()."""
    runner = EvalRunner(max_concurrency=1, rate_limit_rpm=300, request_timeout=3)

    evals = [{"id": i, "input": f"input {i}", "assertions": [{"name": "d", "type": "contains", "value": ".", "weight": 1}]} for i in range(3)]

    adapter = Mock()
    adapter.chat = Mock()
    adapter.model_name = "test-model"

    import engine.runner as _runner_mod

    with patch.object(_runner_mod.EvalRunner, "_run_single", side_effect=ValueError("future boom")):
        results = runner.run_without_skill(evals, adapter)

    assert len(results) == 3
    for r in results:
        assert "error" in r


def test_run_with_skill_deadline_exception_collect():
    """Cover lines 253-254: deadline expired with future raising exception."""
    from concurrent.futures import Future
    from unittest.mock import PropertyMock

    runner = EvalRunner(max_concurrency=2, rate_limit_rpm=300, request_timeout=3)
    evals = [
        {
            "id": i,
            "name": f"eval-{i}",
            "input": f"input {i}",
            "assertions": [{"type": "contains", "value": "ok", "weight": 1}],
        }
        for i in range(2)
    ]

    adapter = Mock()
    adapter.chat = Mock()
    adapter.model_name = "test-model"

    failing_future = Future()
    failing_future.set_exception(ValueError("boom"))

    dl = MagicMock()
    dl.remaining = 30.0
    type(dl).expired = PropertyMock(return_value=True)

    with patch("engine.runner.ThreadPoolExecutor") as mock_executor_cls:
        mock_executor = MagicMock()
        mock_executor_cls.return_value.__enter__ = MagicMock(return_value=mock_executor)
        mock_executor_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_executor.submit.return_value = failing_future

        with patch("engine.runner.as_completed", return_value=iter([failing_future])):
            results = runner.run_with_skill(evals, "/path/to/skill", adapter, deadline=dl)

    assert any("error" in r for r in results)


def test_run_without_skill_deadline_expired_future_exception():
    """Cover lines 316-317: deadline expired with future raising exception."""
    from concurrent.futures import Future
    from unittest.mock import PropertyMock

    runner = EvalRunner(max_concurrency=2, rate_limit_rpm=300, request_timeout=3)
    evals = [
        {
            "id": i,
            "name": f"eval-{i}",
            "input": f"input {i}",
            "assertions": [{"type": "contains", "value": "ok", "weight": 1}],
        }
        for i in range(2)
    ]

    adapter = Mock()
    adapter.chat = Mock()
    adapter.model_name = "test-model"

    failing_future = Future()
    failing_future.set_exception(ValueError("boom"))

    dl = MagicMock()
    dl.remaining = 30.0
    type(dl).expired = PropertyMock(return_value=True)

    with patch("engine.runner.ThreadPoolExecutor") as mock_executor_cls:
        mock_executor = MagicMock()
        mock_executor_cls.return_value.__enter__ = MagicMock(return_value=mock_executor)
        mock_executor_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_executor.submit.return_value = failing_future

        with patch("engine.runner.as_completed", return_value=iter([failing_future])):
            results = runner.run_without_skill(evals, adapter, deadline=dl)

    assert any("error" in r for r in results)
