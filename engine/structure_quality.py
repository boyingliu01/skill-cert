"""Structure quality analysis — tool permission isolation and script usage detection."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Tool Permission Isolation Check ──────────────────────────────

TOOLS_MD_PATTERN = re.compile(r"tools\.md|tools\s*:", re.IGNORECASE)
DANGEROUS_TOOL_PATTERNS = [
    re.compile(r"(shell|bash|exec|run)", re.IGNORECASE),
    re.compile(r"(http[_-]?client|fetch|request)", re.IGNORECASE),
    re.compile(r"(file[_-]?(read|write|delete|edit))", re.IGNORECASE),
]
SCRIPT_REF_PATTERN = re.compile(
    r"(script[s]?/|\.py\b|\.sh\b|\.js\b|\.ts\b|run_cmd|subprocess|exec\b)",
    re.IGNORECASE,
)


@dataclass
class ToolPermissionResult:
    """Result of tool permission isolation analysis."""

    has_tools_md: bool = False
    dangerous_tools_allowed: list[str] = field(default_factory=list)
    score: float = 100.0
    issues: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.score >= 60.0


@dataclass
class ScriptUsageResult:
    """Result of script usage detection."""

    script_references: list[str] = field(default_factory=list)
    has_scripts: bool = False
    script_count: int = 0
    score: float = 0.0
    issues: list[str] = field(default_factory=list)


def check_tool_permission(content: str) -> ToolPermissionResult:
    if not content:
        return ToolPermissionResult(score=0.0, issues=["Empty content"])
    issues: list[str] = []
    has_tools = bool(TOOLS_MD_PATTERN.search(content))
    found_dangerous: list[str] = []
    for pat in DANGEROUS_TOOL_PATTERNS:
        matches = pat.findall(content)
        if matches:
            found_dangerous.append(pat.pattern)
    deductions = 0.0
    if not has_tools:
        deductions += 30.0
        issues.append("No tools.md whitelist found. Define allowed tools per module.")
    if found_dangerous:
        deductions += min(len(found_dangerous) * 15.0, 60.0)
        issues.append(
            f"Dangerous tools referenced without explicit whitelist: {', '.join(found_dangerous)}"
        )
    return ToolPermissionResult(
        has_tools_md=has_tools,
        dangerous_tools_allowed=found_dangerous,
        score=max(0.0, 100.0 - deductions),
        issues=issues,
    )


def check_script_usage(skill_dir: str | Path) -> ScriptUsageResult:
    skill_path = Path(skill_dir)
    if not skill_path.exists():
        return ScriptUsageResult(issues=["Skill directory not found"])
    sk_script_dir = skill_path / "scripts"
    ref_script_dir = skill_path / "references" / "scripts"
    found_scripts: list[str] = []
    for d in [sk_script_dir, ref_script_dir]:
        if d.exists() and d.is_dir():
            for f in sorted(d.rglob("*")):
                if f.is_file() and not f.name.startswith("."):
                    found_scripts.append(str(f.relative_to(skill_path)))
    has_scripts = len(found_scripts) > 0
    score = min(len(found_scripts) * 20.0, 100.0) if has_scripts else 0.0
    issues: list[str] = []
    if not has_scripts:
        issues.append(
            "No scripts/ directory found. Skills should use scripts to "
            "augment LLM capabilities for configuration, HTTP calls, "
            "environment detection, and complex computation."
        )
    return ScriptUsageResult(
        script_references=found_scripts,
        has_scripts=has_scripts,
        script_count=len(found_scripts),
        score=score,
        issues=issues,
    )


__all__ = [
    "ToolPermissionResult",
    "ScriptUsageResult",
    "check_tool_permission",
    "check_script_usage",
]
