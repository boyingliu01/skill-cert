"""Hook/guardrail detection for SKILL.md files.

Analyzes whether a SKILL.md defines safety hooks (/careful, /freeze, /guard)
and operational hooks (/context-save, /context-restore) for agent guardrails.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SAFETY_HOOK_PATTERNS: list[str] = [
    r"/careful\b",
    r"/freeze\b",
    r"/guard\b",
]

OPERATIONAL_HOOK_PATTERNS: list[str] = [
    r"/context-save\b",
    r"/context-restore\b",
    r"/qa\b",
    r"/browse\b",
]

ALL_HOOK_PATTERNS: list[tuple[str, str]] = [
    ("safety", p) for p in SAFETY_HOOK_PATTERNS
] + [("operational", p) for p in OPERATIONAL_HOOK_PATTERNS]


@dataclass
class HooksResult:
    safety_hooks: list[str] = field(default_factory=list)
    operational_hooks: list[str] = field(default_factory=list)
    score: float = 0.0
    issues: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.score >= 50.0


def detect_hooks(content: str) -> HooksResult:
    """Detect hook/guardrail usage in a SKILL.md file.

    Args:
        content: Full text content of SKILL.md.

    Returns:
        HooksResult with detected hooks and scoring.
    """
    if not content.strip():
        return HooksResult(score=0.0, issues=["Empty SKILL.md content"])

    found_safety: set[str] = set()
    found_operational: set[str] = set()
    issues: list[str] = []

    for category, pattern_str in ALL_HOOK_PATTERNS:
        pattern = re.compile(pattern_str)
        if pattern.search(content):
            hook_name = pattern_str.strip("\\b")
            if category == "safety":
                found_safety.add(hook_name)
            else:
                found_operational.add(hook_name)

    safety_count = len(found_safety)
    op_count = len(found_operational)
    total_hooks = safety_count + op_count

    # Scoring:
    # - Each safety hook: 20 points (max 3 = 60)
    # - Each operational hook: 10 points (max 4 = 40)
    # - Total max: 100
    safety_score = min(safety_count * 20.0, 60.0)
    op_score = min(op_count * 10.0, 40.0)
    score = safety_score + op_score

    if safety_count == 0:
        issues.append(
            "No safety hooks (/careful, /freeze, /guard) detected. "
            "Safety hooks prevent destructive operations."
        )
    if op_count == 0:
        issues.append(
            "No operational hooks (/context-save, /context-restore, /qa) detected. "
            "Operational hooks enable session management and QA workflows."
        )

    return HooksResult(
        safety_hooks=sorted(found_safety),
        operational_hooks=sorted(found_operational),
        score=score,
        issues=issues,
    )


__all__ = ["HooksResult", "detect_hooks"]
