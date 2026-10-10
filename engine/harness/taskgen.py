"""Task + hidden-rubric generation for harness evaluation (LLM structured output)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .llm_json import chat_json
from .models import InputFile, Rubric, RubricItem, Task, TaskGenResult
from .util import render_template, strip_frontmatter

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


def _rubric_item_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "criterion": {"type": "string"},
            "points": {"type": "integer"},
        },
        "required": ["id", "criterion", "points"],
    }


TASKGEN_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "harness_taskgen",
        "schema": {
            "type": "object",
            "properties": {
                "leakage_check": {"type": "string"},
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "description": {"type": "string"},
                            "input_files": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "path": {"type": "string"},
                                        "content": {"type": "string"},
                                    },
                                    "required": ["path", "content"],
                                },
                            },
                            "rubrics": {
                                "type": "object",
                                "properties": {
                                    "task_completion": {
                                        "type": "array",
                                        "items": _rubric_item_schema(),
                                    },
                                    "instruction_following": {
                                        "type": "array",
                                        "items": _rubric_item_schema(),
                                    },
                                },
                                "required": ["task_completion", "instruction_following"],
                            },
                        },
                        "required": ["id", "description", "rubrics"],
                    },
                },
            },
            "required": ["tasks", "leakage_check"],
        },
    },
}


def _coerce_input_files(raw: Any) -> list[InputFile]:
    files: list[InputFile] = []
    if not isinstance(raw, list):
        return files
    for item in raw:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        files.append(InputFile(path=path, content=str(item.get("content") or "")))
    return files


def _coerce_rubric_items(raw: Any, prefix: str) -> list[RubricItem]:
    items: list[RubricItem] = []
    if not isinstance(raw, list):
        return items
    for j, item in enumerate(raw):
        if not isinstance(item, dict):
            # a rubric item that never becomes an item silently shrinks the score
            # denominator — say so at the default log level
            logger.warning("rubric item %s%d is not an object and was dropped", prefix, j + 1)
            continue
        criterion = str(item.get("criterion") or "").strip()
        if not criterion:
            logger.warning("rubric item %s%d has no criterion and was dropped", prefix, j + 1)
            continue
        try:
            points = int(item.get("points") or 1)
        except (TypeError, ValueError):
            points = 1
        if points < 1:
            # correction is right for scoring, invisible would hide poor model
            # output — taskgen runs once per evaluation, so warn
            logger.warning("rubric item %s%d points %d clamped to 1", prefix, j + 1, points)
            points = 1
        items.append(
            RubricItem(
                id=str(item.get("id") or f"{prefix}{j + 1}"),
                criterion=criterion,
                points=points,
            )
        )
    return items


class TaskGenerator:
    """Generates tasks + hidden rubrics from a skill definition."""

    def __init__(self, model_adapter: Any, prompts_dir: Path | None = None):
        self.adapter = model_adapter
        self.prompts_dir = prompts_dir or PROMPTS_DIR

    def generate(
        self,
        skill_name: str,
        skill_description: str,
        skill_content: str,
        n_tasks: int = 6,
        timeout: int = 180,
    ) -> TaskGenResult:
        template = strip_frontmatter(
            (self.prompts_dir / "harness-taskgen.md").read_text(encoding="utf-8")
        )
        prompt = render_template(
            template,
            {
                "task_count": str(max(1, n_tasks)),
                "skill_name": str(skill_name),
                "skill_description": str(skill_description or "(none)"),
                "skill_content": str(skill_content),
            },
        )
        data = chat_json(self.adapter, prompt, TASKGEN_SCHEMA, timeout)
        return self._parse_result(data, n_tasks)

    @staticmethod
    def _parse_result(data: dict[str, Any], n_tasks: int) -> TaskGenResult:
        raw_tasks = data.get("tasks")
        if not isinstance(raw_tasks, list) or not raw_tasks:
            raise ValueError("taskgen response contains no tasks")

        seen_ids: set[str] = set()
        tasks: list[Task] = []
        for i, raw in enumerate(raw_tasks[: max(1, n_tasks)]):
            if not isinstance(raw, dict):
                continue
            description = str(raw.get("description") or "").strip()
            if not description:
                continue
            task_id = str(raw.get("id") or f"task-{i + 1}")
            while task_id in seen_ids:
                task_id = f"{task_id}-{i + 1}"
            seen_ids.add(task_id)

            rubrics_raw: dict[str, Any] = {}
            if isinstance(raw.get("rubrics"), dict):
                rubrics_raw = raw["rubrics"]
            tasks.append(
                Task(
                    id=task_id,
                    description=description,
                    input_files=_coerce_input_files(raw.get("input_files")),
                    rubrics=Rubric(
                        task_completion=_coerce_rubric_items(
                            rubrics_raw.get("task_completion"), prefix=f"{task_id}-tc"
                        ),
                        instruction_following=_coerce_rubric_items(
                            rubrics_raw.get("instruction_following"), prefix=f"{task_id}-if"
                        ),
                    ),
                )
            )
        if not tasks:
            raise ValueError("taskgen response has no valid tasks")
        return TaskGenResult(tasks=tasks, leakage_check=str(data.get("leakage_check") or ""))
