"""Unit tests for the harness LLM-judge (FakeAdapter, score clamping, id filtering)."""

import json

import pytest

from engine.harness.judge import JUDGE_SCHEMA, HarnessJudge
from engine.harness.models import JudgeResult, Rubric, RubricItem, Task


class ScriptedAdapter:
    def __init__(self, response: str):
        self.response = response
        self.calls: list[dict] = []

    def chat(self, messages, system=None, timeout=120, response_format=None):
        self.calls.append({"prompt": messages[-1]["content"], "response_format": response_format})
        return self.response


def make_task() -> Task:
    return Task(
        id="t1",
        description="Do the thing.",
        input_files=[],
        rubrics=Rubric(
            task_completion=[RubricItem(id="t1-tc1", criterion="done well", points=2)],
            instruction_following=[RubricItem(id="t1-if1", criterion="skill format", points=3)],
        ),
    )


def judge_payload(items, reasoning="overall fine"):
    return json.dumps({"reasoning": reasoning, "items": items}, ensure_ascii=False)


def test_judge_parses_and_passes_schema():
    adapter = ScriptedAdapter(
        judge_payload(
            [
                {"rubric_id": "t1-tc1", "score": 8, "evidence": "did it"},
                {"rubric_id": "t1-if1", "score": 5.5, "evidence": "partial format"},
            ]
        )
    )
    result = HarnessJudge(adapter).judge(
        make_task(), "demo-skill", "# skill body", "final answer", "tool_call_count: 2"
    )

    assert isinstance(result, JudgeResult)
    assert result.reasoning == "overall fine"
    assert result.score_map() == {"t1-tc1": 8.0, "t1-if1": 5.5}
    call = adapter.calls[0]
    assert call["response_format"] == JUDGE_SCHEMA


def test_judge_clamps_out_of_range_scores():
    adapter = ScriptedAdapter(
        judge_payload(
            [
                {"rubric_id": "t1-tc1", "score": 15},
                {"rubric_id": "t1-if1", "score": -3},
            ]
        )
    )
    result = HarnessJudge(adapter).judge(make_task(), "s", "c", "out", "traj")
    assert result.score_map() == {"t1-tc1": 10.0, "t1-if1": 0.0}


def test_judge_drops_unknown_ids_and_bad_scores():
    adapter = ScriptedAdapter(
        judge_payload(
            [
                {"rubric_id": "t1-tc1", "score": 7},
                {"rubric_id": "hallucinated-id", "score": 10},
                {"rubric_id": "t1-if1", "score": "not-a-number"},
            ]
        )
    )
    result = HarnessJudge(adapter).judge(make_task(), "s", "c", "out", "traj")
    assert result.score_map() == {"t1-tc1": 7.0}


def test_judge_prompt_contains_all_inputs():
    adapter = ScriptedAdapter(judge_payload([{"rubric_id": "t1-tc1", "score": 1}]))
    HarnessJudge(adapter).judge(
        make_task(),
        "demo-skill",
        "# SKILL SECRET BODY",
        "GREETING-PROTO v1",
        "tool_sequence: skill -> read\nduration_s: 3.2",
    )
    prompt = adapter.calls[0]["prompt"]
    assert "Do the thing." in prompt
    assert "SKILL SECRET BODY" in prompt
    assert "GREETING-PROTO v1" in prompt
    assert "skill -> read" in prompt
    assert "t1-tc1" in prompt  # rubric json embedded
    # frontmatter stripped from the template
    assert not prompt.startswith("---")


def test_judge_degrades_on_400_and_extracts_fenced_json():
    class DegradingAdapter(ScriptedAdapter):
        def __init__(self):
            super().__init__("unused")
            self.first = True

        def chat(self, messages, system=None, timeout=120, response_format=None):
            if self.first and response_format is not None:
                self.first = False
                raise RuntimeError("API returned 400. Detail: no json_schema")
            self.calls.append(
                {"prompt": messages[-1]["content"], "response_format": response_format}
            )
            return (
                "Sure!\n```json\n" + judge_payload([{"rubric_id": "t1-tc1", "score": 9}]) + "\n```"
            )

    result = HarnessJudge(DegradingAdapter()).judge(make_task(), "s", "c", "out", "traj")
    assert result.score_map() == {"t1-tc1": 9.0}


def test_judge_non_json_response_raises():
    adapter = ScriptedAdapter("I cannot judge this, sorry.")
    with pytest.raises(ValueError, match="did not return a JSON object"):
        HarnessJudge(adapter).judge(make_task(), "s", "c", "out", "traj")
