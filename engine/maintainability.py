"""SKILL.md maintainability scorer — readability, completeness, freshness."""

import re
from dataclasses import dataclass

import yaml


@dataclass(frozen=True)
class MaintainabilityResult:
    total_score: float
    readability_score: float
    completeness_score: float
    freshness_score: float
    grade: str
    readability_details: dict
    completeness_details: dict
    freshness_details: dict


def readability_score(content: str) -> dict:
    """Score readability (0.0-1.0) based on line length, nesting depth, TODOs."""
    if not content or not content.strip():
        return {
            "avg_line_length": 0,
            "max_depth": 0,
            "todo_count": 0,
            "score": 1.0,
        }

    lines = content.split("\n")
    line_lengths = [len(line) for line in lines if line.strip()]
    avg_line_length = sum(line_lengths) / len(line_lengths) if line_lengths else 0

    heading_depths = []
    for line in lines:
        match = re.match(r"^(#{2,6})\s", line)
        if match:
            heading_depths.append(len(match.group(1)) - 1)
    max_depth = max(heading_depths) if heading_depths else 0

    todo_pattern = re.compile(r"\b(TODO|FIXME|HACK|XXX|TBD)\b", re.IGNORECASE)
    todo_count = sum(1 for line in lines if todo_pattern.search(line))

    length_score = max(0.0, 1.0 - (max(0, avg_line_length - 100) / 100))
    depth_score = 1.0 if max_depth <= 3 else max(0.0, 1.0 - (max_depth - 3) * 0.5)
    todo_score = max(0.0, 1.0 - todo_count * 0.15)

    combined = (length_score + depth_score + todo_score) / 3.0

    return {
        "avg_line_length": round(avg_line_length, 1),
        "max_depth": max_depth,
        "todo_count": todo_count,
        "length_score": round(length_score, 3),
        "depth_score": round(depth_score, 3),
        "todo_score": round(todo_score, 3),
        "score": round(combined, 3),
    }


def completeness_score(content: str) -> dict:
    """Score completeness (0.0-1.0) based on required sections."""
    if not content or not content.strip():
        return {
            "has_name": False,
            "has_description": False,
            "has_triggers": False,
            "has_workflow": False,
            "has_anti_patterns": False,
            "score": 0.0,
        }

    fm = _extract_frontmatter(content)
    if not isinstance(fm, dict):
        fm = None

    has_name = bool(
        (fm and fm.get("name")) or re.search(r"^#\s+\S", content, re.MULTILINE)
    )
    has_description = bool(fm and fm.get("description"))
    has_triggers = bool(_has_section(content, r"Triggers|TRIGGERS?|触发")) or bool(
        fm and (fm.get("triggers") or fm.get("TRIGGERS") or fm.get("TRIGGER"))
    )
    has_workflow = bool(
        _has_section(content, r"Workflow|Process|Flow|流程|步骤")
    )
    has_anti_patterns = bool(_has_section(content, r"Anti-Patterns|反模式"))

    checks = [has_name, has_description, has_triggers, has_workflow, has_anti_patterns]
    score = sum(checks) / len(checks) if checks else 0.0

    return {
        "has_name": has_name,
        "has_description": has_description,
        "has_triggers": has_triggers,
        "has_workflow": has_workflow,
        "has_anti_patterns": has_anti_patterns,
        "score": round(score, 3),
    }


FRESHNESS_PATTERNS = [
    re.compile(r"\b(?:Claude\s+[12]|GPT-3\.5|GPT-4(?![-.]))\b"),
    re.compile(r"\bPython\s+3\.[0-6]\b"),
    re.compile(r"\b(?:anthropic[-_]sdk|openai[-_]python)\b", re.IGNORECASE),
    re.compile(r"\bv\d+\.\d+\.\d+[-\w]*\b"),
]


def freshness_score(content: str) -> dict:
    """Score freshness (0.0-1.0) based on outdated references."""
    if not content or not content.strip():
        return {
            "outdated_refs": 0,
            "has_version": False,
            "score": 1.0,
        }

    outdated_refs = 0
    for pattern in FRESHNESS_PATTERNS:
        outdated_refs += len(pattern.findall(content))

    version_match = re.search(
        r"(?:^|\n)\s*Version\s*:\s*(\S+)", content, re.MULTILINE | re.IGNORECASE
    )
    has_version = bool(version_match)

    is_beta = bool(re.search(r"\b(?:alpha|beta|dev|rc)\d*\b", content, re.IGNORECASE))
    penalty = outdated_refs * 0.1 + (0.5 if is_beta else 0)
    score = max(0.0, 1.0 - penalty)

    return {
        "outdated_refs": outdated_refs,
        "has_version": has_version,
        "is_beta": is_beta,
        "score": round(score, 3),
    }


def score_skill_md(content: str) -> MaintainabilityResult:
    """Compute composite maintainability score (0-100)."""
    r = readability_score(content)
    c = completeness_score(content)
    f = freshness_score(content)

    r_pct = r["score"] * 100
    c_pct = c["score"] * 100
    f_pct = f["score"] * 100

    total = r_pct * 0.30 + c_pct * 0.50 + f_pct * 0.20
    total = round(total, 1)

    if total >= 90:
        grade = "A"
    elif total >= 80:
        grade = "B"
    elif total >= 70:
        grade = "C"
    elif total >= 60:
        grade = "D"
    else:
        grade = "F"

    return MaintainabilityResult(
        total_score=total,
        readability_score=round(r_pct, 1),
        completeness_score=round(c_pct, 1),
        freshness_score=round(f_pct, 1),
        grade=grade,
        readability_details=r,
        completeness_details=c,
        freshness_details=f,
    )


class MaintainabilityScorer:
    """Score SKILL.md maintainability from file or content."""

    def __init__(
        self,
        weights: dict | None = None,
    ):
        self.weights = weights or {
            "readability": 30,
            "completeness": 50,
            "freshness": 20,
        }

    def score_file(self, path: str) -> MaintainabilityResult:
        from pathlib import Path as _Path
        file_path = _Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"SKILL.md not found: {path}")
        content = file_path.read_text(encoding="utf-8")
        return self.score_content(content)

    def score_content(self, content: str) -> MaintainabilityResult:
        r = readability_score(content)
        c = completeness_score(content)
        f = freshness_score(content)

        r_pct = r["score"] * 100
        c_pct = c["score"] * 100
        f_pct = f["score"] * 100

        w = self.weights
        total_weight = sum(w.values())
        total = (
            r_pct * w["readability"]
            + c_pct * w["completeness"]
            + f_pct * w["freshness"]
        ) / total_weight
        total = round(total, 1)

        if total >= 90:
            grade = "A"
        elif total >= 80:
            grade = "B"
        elif total >= 70:
            grade = "C"
        elif total >= 60:
            grade = "D"
        else:
            grade = "F"

        return MaintainabilityResult(
            total_score=total,
            readability_score=round(r_pct, 1),
            completeness_score=round(c_pct, 1),
            freshness_score=round(f_pct, 1),
            grade=grade,
            readability_details=r,
            completeness_details=c,
            freshness_details=f,
        )


def _extract_frontmatter(content: str) -> dict | None:
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return None
    try:
        return yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return None


def _has_section(content: str, pattern: str) -> bool:
    return bool(re.search(
        rf"^##\s+[^#\n]*{pattern}[^#\n]*$", content, re.MULTILINE | re.IGNORECASE
    ))
