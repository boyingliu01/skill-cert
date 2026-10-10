"""Public LLM-response JSON extraction for the whole engine.

Owned here rather than inside ``EvalGenerator`` because several evaluation
paths (testgen, harness taskgen/judge) need the same tolerant parsing and must
not reach into another module's private methods.
"""

from __future__ import annotations

import json
import re
from typing import Any


def repair_json_trailing_commas(text: str) -> str | None:
    """Remove trailing commas before closing braces/brackets (common LLM mistake)."""
    try:
        repaired = re.sub(r",(\s*[}\]])", r"\1", text)
        json.loads(repaired)
        return repaired
    except (json.JSONDecodeError, ValueError):
        return None


def strip_markdown_fences(text: str) -> str:
    """Strip markdown JSON fences and return clean JSON text."""
    lines = text.split("\n")
    fences = []
    in_fence = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_fence:
                in_fence = False
            elif stripped.startswith("```json") or stripped == "```":
                in_fence = True
            continue
        if not in_fence or stripped:
            fences.append(line)
    return "\n".join(fences)


def balanced_brace_extract(response: str) -> dict[str, Any] | None:
    """Strategy 2: Find first valid outermost {..} via balanced brace counting."""
    start = response.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escape_next = False
        for i in range(start, len(response)):
            ch = response[i]
            if escape_next:
                escape_next = False
                continue
            if ch == "\\" and in_string:
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = response[start : i + 1]
                    try:
                        parsed = json.loads(candidate)
                        if isinstance(parsed, dict):
                            return parsed
                    except (json.JSONDecodeError, ValueError):
                        pass
                    break
        start = response.find("{", start + 1)
    return None


def largest_first_extract(response: str) -> dict[str, Any] | None:
    """Strategy 3: Find all top-level {..} blocks, try largest to smallest."""
    blocks: list[tuple[int, int]] = []
    start = response.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escape_next = False
        for i in range(start, len(response)):
            ch = response[i]
            if escape_next:
                escape_next = False
                continue
            if ch == "\\" and in_string:
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    blocks.append((start, i + 1))
                    break
        start = response.find("{", start + 1)

    blocks.sort(key=lambda b: b[1] - b[0], reverse=True)
    for s, e in blocks:
        try:
            parsed = json.loads(response[s:e])
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            continue
    return None


# Names of the four fallback levels, in the order ``extract_json`` tries them, so
# a caller can report *which* level produced the object instead of only that it
# produced one. A model that quietly needs level 3 is worth seeing.
#
# ``largest-first`` is listed because the chain is documented as four levels, but
# it can never be the level that matches: it enumerates exactly the same
# candidate blocks as ``balanced`` (every '{' scanned to its depth-0 close) and
# only reorders them, so whenever it would return an object, ``balanced`` has
# already returned one. The engine therefore has three live levels, not four.
JSON_LEVELS: tuple[str, ...] = ("fences", "balanced", "largest-first", "strict=False")


def extract_json_with_level(response: str) -> tuple[dict[str, Any], int] | None:
    """``extract_json`` plus the index into ``JSON_LEVELS`` of the level that matched.

    Returns ``None`` when nothing parsed. Prefer ``extract_json`` unless the
    winning level matters: this is the same code path, one tuple wider.
    """
    return _extract(response, with_level=True)


def extract_json(response: str) -> dict[str, Any] | None:
    """Extract JSON object from LLM response using 4-level fallback.

    Strategy 1: Strip markdown fences + repair trailing commas + json.loads
    Strategy 2: Balanced brace counting to find outermost {..} (with repair)
    Strategy 3: Largest-first — try all {..} blocks largest to smallest (with repair)
    Strategy 4: json.loads with strict=False on full response (with repair)
    """
    return _extract(response, with_level=False)


def _extract(response: str, *, with_level: bool) -> Any:
    """The shared 4-level chain; ``with_level`` selects the tuple return shape."""

    def _hit(parsed: dict[str, Any], level: int):
        return (parsed, level) if with_level else parsed

    if not response or not response.strip():
        return None

    # Strategy 1: Strip markdown fences + json.loads (with trailing comma repair)
    try:
        cleaned = strip_markdown_fences(response)
        start_idx = cleaned.find("{")
        end_idx = cleaned.rfind("}") + 1
        if start_idx != -1 and end_idx > start_idx:
            candidate = cleaned[start_idx:end_idx]
            repaired = repair_json_trailing_commas(candidate)
            if repaired is not None:
                parsed = json.loads(repaired)
                if isinstance(parsed, dict):
                    return _hit(parsed, 0)
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return _hit(parsed, 0)
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 2: Balanced brace extraction — find first valid outermost {..}
    result = balanced_brace_extract(response)
    if result is not None:
        return _hit(result, 1)

    # Strategy 3: Largest-first — find all {..} blocks, try largest first
    result = largest_first_extract(response)
    if result is not None:
        return _hit(result, 2)

    # Strategy 4: json.loads with strict=False on full response (with repair)
    try:
        repaired = repair_json_trailing_commas(response)
        if repaired is not None:
            parsed = json.loads(repaired, strict=False)
            if isinstance(parsed, dict):
                return _hit(parsed, 3)
        parsed = json.loads(response, strict=False)
        if isinstance(parsed, dict):
            return _hit(parsed, 3)
    except (json.JSONDecodeError, ValueError):
        pass

    # Also try strict=False on the first{..}last slice (with repair)
    try:
        start_idx = response.find("{")
        end_idx = response.rfind("}") + 1
        if start_idx != -1 and end_idx > start_idx:
            candidate = response[start_idx:end_idx]
            repaired = repair_json_trailing_commas(candidate)
            if repaired is not None:
                parsed = json.loads(repaired, strict=False)
                if isinstance(parsed, dict):
                    return _hit(parsed, 3)
            parsed = json.loads(candidate, strict=False)
            if isinstance(parsed, dict):
                return _hit(parsed, 3)
    except (json.JSONDecodeError, ValueError):
        pass

    return None
