"""Skill output type classifier — score-based detection for assertion strategy routing.

Determines whether a skill produces structured output (JSON/code/schema) or
natural language output, so TestGen can route evals to the correct assertion
strategy. Pure function — no LLM calls, <1ms overhead.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Keywords that signal structured output formats
STRUCTURED_KEYWORDS = frozenset({
    "json", "code", "schema", "yaml", "toml", "xml",
    "csv", "tsv", "proto", "sql", "graphql", "rest api",
})

# Flow-language patterns in description that signal natural language output
FLOW_PATTERNS = [
    re.compile(r"\bstep[- ]by[- ]step\b", re.IGNORECASE),
    re.compile(r"\bfirst\b.*\bthen\b", re.IGNORECASE),
    re.compile(r"\bfinally\b", re.IGNORECASE),
    re.compile(r"\bin this order\b", re.IGNORECASE),
    re.compile(r"\bthe following steps?\b", re.IGNORECASE),
    re.compile(r"\bwalkthrough\b", re.IGNORECASE),
    re.compile(r"\bphase \d\b", re.IGNORECASE),
    re.compile(r"\bround \d\b", re.IGNORECASE),
]


@dataclass(frozen=True)
class OutputType:
    """Classification result for skill output type."""

    strategy: str  # "natural_language" or "structured"
    confidence: float  # 0.0 to 1.0
    signals: list[str] = field(default_factory=list)  # why this classification


def classify_output_type(skill_spec: dict[str, Any]) -> OutputType:
    """Classify a skill's output type using score-based detection.

    Score >= 3 → natural_language, < 3 → structured.
    No LLM calls — regex/string matching only.

    Args:
        skill_spec: Parsed skill specification dict (from SkillSpec.model_dump()).

    Returns:
        OutputType with strategy, confidence, and contributing signals.
    """
    score = 0.0
    signals: list[str] = []

    # Empty spec → structured with low confidence
    if not skill_spec:
        return OutputType(strategy="structured", confidence=0.5, signals=["empty_spec"])

    # 1. Check output_format field for structured keywords
    output_format = skill_spec.get("output_format", [])
    if output_format:
        fmt_text = " ".join(str(f).lower() for f in output_format)
        has_structured = any(kw in fmt_text for kw in STRUCTURED_KEYWORDS)
        if has_structured:
            score -= 1.5
            signals.append(f"structured_format: {fmt_text}")
        else:
            score += 1.0
            signals.append(f"non_structured_format: {fmt_text}")

    # 2. Check workflow_steps presence
    workflow_steps = skill_spec.get("workflow_steps", [])
    if workflow_steps:
        n_steps = len(workflow_steps) if isinstance(workflow_steps, list) else 0
        if n_steps >= 2:
            score += 1.5
            signals.append(f"workflow_steps: {n_steps} steps")
        elif n_steps == 1:
            score += 0.5
            signals.append("workflow_steps: 1 step")

    # 3. Check description for flow language
    description = skill_spec.get("description", "")
    if description:
        flow_matches = sum(1 for p in FLOW_PATTERNS if p.search(str(description)))
        if flow_matches >= 2:
            score += 1.5
            signals.append(f"flow_language: {flow_matches} patterns")
        elif flow_matches == 1:
            score += 0.75
            signals.append("flow_language: 1 pattern")

    # 4. Check triggers presence
    triggers = skill_spec.get("triggers", [])
    if triggers and len(triggers) >= 2:
        score += 0.5
        signals.append(f"triggers: {len(triggers)} patterns")

    # Apply threshold
    strategy = "natural_language" if score >= 3.0 else "structured"

    # Clamp confidence to [0.3, 1.0] range
    confidence = max(0.3, min(1.0, abs(score) / 5.0))

    logger.debug(
        "classify_output_type: score=%.2f, strategy=%s, confidence=%.2f, signals=%s",
        score,
        strategy,
        confidence,
        signals,
    )

    return OutputType(strategy=strategy, confidence=confidence, signals=signals)
