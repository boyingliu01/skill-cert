"""Unit tests for harness task generation (FakeAdapter, schema parsing, degradation)."""

import json

import pytest

from adapters.base import StructuredOutputRejectedError
from engine.harness.taskgen import TASKGEN_SCHEMA, TaskGenerator


class ScriptedAdapter:
    """Fake ModelAdapter: picks the response whose substring appears in the prompt."""

    def __init__(self, scripts):
        # scripts: list of (substring, response); first match wins, last repeats
        self.scripts = list(scripts)
        self.calls: list[dict] = []

    def chat(self, messages, system=None, timeout=120, response_format=None):
        self.calls.append({"prompt": messages[-1]["content"], "response_format": response_format})
        prompt = messages[-1]["content"]
        for substring, response in self.scripts:
            if substring in prompt:
                return response
        return self.scripts[-1][1]


TASKGEN_PAYLOAD = {
    "leakage_check": "checked, no leakage",
    "tasks": [
        {
            "id": "t1",
            "description": "Summarize the notes.",
            "input_files": [{"path": "notes.txt", "content": "hello world"}],
            "rubrics": {
                "task_completion": [{"id": "t1-tc1", "criterion": "mentions hello", "points": 2}],
                "instruction_following": [
                    {"id": "t1-if1", "criterion": "uses skill format", "points": 3}
                ],
            },
        },
        {
            "id": "t1",  # duplicate id on purpose
            "description": "Sort the list.",
            "rubrics": {
                "task_completion": [{"criterion": "sorted ascending", "points": "bad"}],
                "instruction_following": [],
            },
        },
        {"id": "t3", "description": "", "rubrics": {}},  # empty description -> dropped
    ],
}


def make_adapter(payload=None, fenced=False):
    payload = payload if payload is not None else TASKGEN_PAYLOAD
    text = json.dumps(payload, ensure_ascii=False)
    if fenced:
        text = f"Here you go:\n```json\n{text}\n```"
    return ScriptedAdapter([("任务生成器", text)])


def test_generate_parses_tasks_and_passes_schema(tmp_path):
    adapter = make_adapter()
    result = TaskGenerator(adapter).generate("demo-skill", "a demo", "# Demo\nbody", n_tasks=6)

    assert len(result.tasks) == 2
    t1 = result.tasks[0]
    assert t1.id == "t1"
    assert t1.description == "Summarize the notes."
    assert t1.input_files[0].path == "notes.txt"
    assert t1.rubrics.task_completion[0].points == 2
    assert t1.rubrics.instruction_following[0].id == "t1-if1"
    assert result.leakage_check == "checked, no leakage"

    call = adapter.calls[0]
    assert call["response_format"] == TASKGEN_SCHEMA
    assert "demo-skill" in call["prompt"]
    assert "# Demo" in call["prompt"]
    assert "6" in call["prompt"]  # task count injected


def test_generate_dedupes_ids_and_repairs_fields(tmp_path):
    result = TaskGenerator(make_adapter()).generate("demo-skill", "", "body", n_tasks=6)

    ids = [t.id for t in result.tasks]
    assert len(ids) == len(set(ids))
    t2 = result.tasks[1]
    assert t2.id.startswith("t1-")  # deduped suffix
    # missing rubric ids get prefix-based ids; invalid points coerce to 1
    assert t2.rubrics.task_completion[0].id == f"{t2.id}-tc1"
    assert t2.rubrics.task_completion[0].points == 1


def test_generate_truncates_to_n_tasks():
    adapter = make_adapter()
    result = TaskGenerator(adapter).generate("demo-skill", "", "body", n_tasks=1)
    assert len(result.tasks) == 1


def test_generate_no_tasks_raises():
    adapter = make_adapter({"leakage_check": "", "tasks": []})
    with pytest.raises(ValueError, match="no tasks"):
        TaskGenerator(adapter).generate("demo-skill", "", "body")


def test_generate_degrades_on_rejected_schema_with_fenced_json():
    """Gateway rejects response_format -> plain retry + fenced-JSON extraction."""

    class DegradingAdapter(ScriptedAdapter):
        def __init__(self):
            super().__init__([("任务生成器", "unused")])
            self.first = True

        def chat(self, messages, system=None, timeout=120, response_format=None):
            if self.first and response_format is not None:
                self.first = False
                raise StructuredOutputRejectedError(
                    "Gateway rejected response_format for model 'm'. Detail: schema unsupported"
                )
            self.calls.append(
                {"prompt": messages[-1]["content"], "response_format": response_format}
            )
            return f"```json\n{json.dumps(TASKGEN_PAYLOAD)}\n```"

    adapter = DegradingAdapter()
    result = TaskGenerator(adapter).generate("demo-skill", "", "body")
    assert len(result.tasks) == 2
    # second (degraded) call went out without response_format
    assert adapter.calls[-1]["response_format"] is None


def test_generate_propagates_unrelated_errors():
    class FailingAdapter(ScriptedAdapter):
        def chat(self, messages, system=None, timeout=120, response_format=None):
            raise RuntimeError("Invalid API key")

    with pytest.raises(RuntimeError, match="Invalid API key"):
        TaskGenerator(FailingAdapter([("任务生成器", "x")])).generate("demo-skill", "", "body")
