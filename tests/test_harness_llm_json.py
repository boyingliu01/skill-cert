"""Unit tests for the shared structured-output helper (degrade contract)."""

import json

import pytest

from adapters.base import StructuredOutputRejectedError
from engine.harness.llm_json import chat_json, supports_structured_output

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


class PlainAdapter:
    """Shaped like AnthropicCompatAdapter: no response_format parameter at all."""

    def __init__(self, reply: str):
        self.reply = reply
        self.seen_schema = False

    def chat(self, messages, system=None, timeout=120):
        self.seen_schema = True
        return self.reply


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

    with pytest.raises(ValueError, match="did not return a JSON object") as excinfo:
        chat_json(adapter, "prompt", SCHEMA)

    assert "fences" in str(excinfo.value)


def test_chat_json_names_the_chain_when_no_json_is_found():
    adapter = RecordingAdapter([lambda rf: "I could not do that."])

    with pytest.raises(ValueError, match="extract_json"):
        chat_json(adapter, "prompt", SCHEMA)


def test_supports_structured_output_reads_the_chat_signature():
    assert supports_structured_output(RecordingAdapter([lambda rf: "{}"])) is True
    assert supports_structured_output(PlainAdapter("{}")) is False


def test_supports_structured_output_covers_the_in_repo_adapters():
    """adapters/factory can only build these two — pin what each one accepts.

    Probed unbound on the class so no network client is constructed.
    """
    from adapters.anthropic_compat import AnthropicCompatAdapter
    from adapters.openai_compat import OpenAICompatAdapter

    assert supports_structured_output(AnthropicCompatAdapter) is False
    assert supports_structured_output(OpenAICompatAdapter) is True


def test_chat_json_drops_the_kwarg_for_adapters_without_it():
    """An adapter without response_format must degrade, not abort with TypeError."""
    adapter = PlainAdapter('{"tasks": []}')

    assert chat_json(adapter, "prompt", SCHEMA) == {"tasks": []}
    assert adapter.seen_schema is True


def test_chat_json_still_passes_schema_when_supported():
    adapter = RecordingAdapter([lambda rf: json.dumps({"a": 1})])

    chat_json(adapter, "prompt", SCHEMA)

    assert adapter.calls[0]["response_format"] == SCHEMA
