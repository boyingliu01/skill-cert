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

STRUCTURED_KEYWORDS = frozenset(
    {
        "code",
        "schema",
        "yaml",
        "toml",
        "xml",
        "csv",
        "tsv",
        "proto",
        "sql",
        "graphql",
        "rest api",
    }
)

WEAK_STRUCTURED_KEYWORDS = frozenset(
    {
        "json",
    }
)

JSON_CONTAINS_PATTERNS = [
    re.compile(r"json.*格式.*保留", re.IGNORECASE),
    re.compile(r"json.*用于", re.IGNORECASE),
    re.compile(r"包含.*json", re.IGNORECASE),
    re.compile(r"输出.*json", re.IGNORECASE),
    re.compile(r"结构化.*数据", re.IGNORECASE),
    re.compile(r"verdict.*json", re.IGNORECASE),
    re.compile(r"格式.*json", re.IGNORECASE),
]

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

NL_OUTPUT_PATTERNS = [
    re.compile(r"\b报告\b", re.IGNORECASE),
    re.compile(r"\b分析\b", re.IGNORECASE),
    re.compile(r"\b评审\b", re.IGNORECASE),
    re.compile(r"\bmarkdown\b", re.IGNORECASE),
    re.compile(r"\b可读\b", re.IGNORECASE),
    re.compile(r"\b文档\b", re.IGNORECASE),
]


@dataclass(frozen=True)
class OutputType:
    """Classification result for skill output type."""

    strategy: str
    confidence: float
    signals: list[str] = field(default_factory=list)


def _is_json_containment(fmt_text: str) -> bool:
    """Check if JSON mention is about containing JSON elements vs being pure JSON."""
    return any(p.search(fmt_text) for p in JSON_CONTAINS_PATTERNS)


def classify_output_type(skill_spec: dict[str, Any]) -> OutputType:
    """Classify a skill's output type using score-based detection.

    Score >= 3 → natural_language, < 3 → structured.
    No LLM calls — regex/string matching only.
    """
    score = 0.0
    signals: list[str] = []

    if not skill_spec:
        return OutputType(strategy="structured", confidence=0.5, signals=["empty_spec"])

    output_format = skill_spec.get("output_format", [])
    if output_format:
        fmt_text = " ".join(str(f).lower() for f in output_format)
        has_strong_structured = any(kw in fmt_text for kw in STRUCTURED_KEYWORDS)
        has_weak_structured = any(kw in fmt_text for kw in WEAK_STRUCTURED_KEYWORDS)

        if has_strong_structured:
            score -= 2.0
            signals.append(f"strong_structured_format: {fmt_text}")
        elif has_weak_structured:
            if _is_json_containment(fmt_text):
                score += 0.5
                signals.append(f"json_containment: {fmt_text}")
            else:
                score -= 1.0
                signals.append(f"json_format: {fmt_text}")
        else:
            score += 1.0
            signals.append(f"non_structured_format: {fmt_text}")

    workflow_steps = skill_spec.get("workflow_steps", [])
    if workflow_steps:
        n_steps = len(workflow_steps) if isinstance(workflow_steps, list) else 0
        if n_steps >= 5:
            score += 2.0
            signals.append(f"complex_workflow: {n_steps} steps")
        elif n_steps >= 2:
            score += 1.5
            signals.append(f"workflow_steps: {n_steps} steps")
        elif n_steps == 1:
            score += 0.5
            signals.append("workflow_steps: 1 step")

    description = skill_spec.get("description", "")
    if description:
        flow_matches = sum(1 for p in FLOW_PATTERNS if p.search(str(description)))
        nl_matches = sum(1 for p in NL_OUTPUT_PATTERNS if p.search(str(description)))

        if flow_matches >= 2:
            score += 1.5
            signals.append(f"flow_language: {flow_matches} patterns")
        elif flow_matches == 1:
            score += 0.75
            signals.append("flow_language: 1 pattern")

        if nl_matches >= 2:
            score += 1.0
            signals.append(f"nl_indicators: {nl_matches} patterns")
        elif nl_matches == 1:
            score += 0.5
            signals.append("nl_indicators: 1 pattern")

    triggers = skill_spec.get("triggers", [])
    if triggers and len(triggers) >= 2:
        score += 0.5
        signals.append(f"triggers: {len(triggers)} patterns")

    strategy = "natural_language" if score >= 3.0 else "structured"
    confidence = max(0.3, min(1.0, abs(score) / 5.0))

    logger.debug(
        "classify_output_type: score=%.2f, strategy=%s, confidence=%.2f, signals=%s",
        score,
        strategy,
        confidence,
        signals,
    )

    return OutputType(strategy=strategy, confidence=confidence, signals=signals)
