"""Unit tests for the shared structured-output helper (degrade contract)."""

import json

import pytest

from adapters.base import StructuredOutputRejectedError
from engine.harness.llm_json import chat_json

SCHEMA = {"type": "json_schema", "json_schema": {"name": "x", "schema": {}}}


class RecordingAdapter:
    def __init__(self, behaviors):
        # behaviors: list of callables(response_format) -> str | Exception, repeated by call
        self.behaviors = behaviors
        self.calls: list[dict] = []

    def chat(self, messages, system=None, timeout=120, response_format=None):
        self.calls.append({"prompt": messages[-1]["content"], "response_format": response_format})
        behavior = self.behaviors[min(len(self.calls) - 1, len(self.behaviors) - 1)]
        result = behavior(response_format)
        if isinstance(result, BaseException):
            raise result
        return result


def test_chat_json_passes_schema_and_parses_object():
    adapter = RecordingAdapter([lambda rf: json.dumps({"a": 1})])

    assert chat_json(adapter, "prompt", SCHEMA) == {"a": 1}
    assert adapter.calls[0]["response_format"] == SCHEMA


def test_chat_json_retries_without_schema_on_rejection():
    def behavior(response_format):
        if response_format is not None:
            raise StructuredOutputRejectedError("Gateway rejected response_format")
        return '```json\n{"a": 2}\n```'

    adapter = RecordingAdapter([behavior])

    assert chat_json(adapter, "prompt", SCHEMA) == {"a": 2}
    assert adapter.calls[-1]["response_format"] is None


def test_chat_json_propagates_other_runtime_errors():
    adapter = RecordingAdapter([lambda rf: RuntimeError("Invalid API key")])

    with pytest.raises(RuntimeError, match="Invalid API key"):
        chat_json(adapter, "prompt", SCHEMA)


def test_chat_json_rejects_non_object_payloads():
    adapter = RecordingAdapter([lambda rf: "[1, 2]"])

    with pytest.raises(ValueError, match="did not return a JSON object"):
        chat_json(adapter, "prompt", SCHEMA)
