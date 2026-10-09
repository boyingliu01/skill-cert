"""LLM-judge for harness runs (structured output; input includes trajectory
and the full skill definition so instruction-following can be judged fairly)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .llm_json import chat_json
from .models import JudgeItemResult, JudgeResult, Task

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"

JUDGE_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "harness_judge",
        "schema": {
            "type": "object",
            "properties": {
                "reasoning": {"type": "string"},
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "rubric_id": {"type": "string"},
                            "score": {"type": "number"},
                            "evidence": {"type": "string"},
                        },
                        "required": ["rubric_id", "score"],
                    },
                },
            },
            "required": ["items", "reasoning"],
        },
    },
}


class HarnessJudge:
    """Scores one run against the task's hidden rubric."""

    def __init__(self, model_adapter: Any, prompts_dir: Path | None = None):
        self.adapter = model_adapter
        self.prompts_dir = prompts_dir or PROMPTS_DIR

    def judge(
        self,
        task: Task,
        skill_name: str,
        skill_content: str,
        final_output: str,
        trajectory_summary: str,
        timeout: int = 180,
    ) -> JudgeResult:
        template = self._load_template()
        rubric_json = json.dumps(task.rubrics.model_dump(), ensure_ascii=False, indent=2)
        input_files = "\n".join(f"- {f.path}" for f in task.input_files) or "(none)"
        prompt = (
            template.replace("{task_id}", str(task.id))
            .replace("{task_description}", str(task.description))
            .replace("{input_files}", input_files)
            .replace("{skill_name}", str(skill_name))
            .replace("{skill_content}", str(skill_content))
            .replace("{final_output}", str(final_output))
            .replace("{trajectory_summary}", str(trajectory_summary))
            # rubric JSON last: it legitimately contains braces and must not be
            # affected by earlier placeholder substitutions
            .replace("{rubric_json}", rubric_json)
        )
        data = chat_json(self.adapter, prompt, JUDGE_SCHEMA, timeout)
        return self._parse_result(data, task)

    def _load_template(self) -> str:
        text = (self.prompts_dir / "harness-judge.md").read_text(encoding="utf-8")
        if text.startswith("---"):
            end = text.find("\n---", 3)
            if end != -1:
                text = text[end + 4 :]
        return text.strip()

    @staticmethod
    def _parse_result(data: dict[str, Any], task: Task) -> JudgeResult:
        valid_ids = {item.id for item in task.rubrics.all_items()}
        items: list[JudgeItemResult] = []
        raw_items = data.get("items")
        for raw in raw_items if isinstance(raw_items, list) else []:
            if not isinstance(raw, dict):
                continue
            rubric_id = str(raw.get("rubric_id") or "")
            if rubric_id not in valid_ids:
                logger.warning(
                    "judge returned unknown rubric_id '%s' (task %s) — dropped",
                    rubric_id,
                    task.id,
                )
                continue
            try:
                raw_score = raw.get("score")
                if raw_score is None:
                    continue
                score = float(raw_score)
            except (TypeError, ValueError):
                continue
            items.append(
                JudgeItemResult(
                    rubric_id=rubric_id,
                    score=max(0.0, min(10.0, score)),
                    evidence=str(raw.get("evidence") or ""),
                )
            )
        return JudgeResult(items=items, reasoning=str(data.get("reasoning") or ""))
