"""SKILL.md maintainability scorer — readability, completeness, freshness."""

import re
import subprocess
import time
from dataclasses import dataclass

import yaml


@dataclass(frozen=True)
class FreshnessFinding:
    line_number: int
    pattern_type: str
    severity: str
    description: str


def _freshness_finding_to_dict(finding: FreshnessFinding) -> dict:
    """Convert FreshnessFinding to a JSON-serializable dict."""
    return {
        "line_number": finding.line_number,
        "pattern_type": finding.pattern_type,
        "severity": finding.severity,
        "description": finding.description,
    }


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


def _calc_line_length_score(avg_line_length: float) -> float:
    return round(max(0.0, 1.0 - (max(0, avg_line_length - 100) / 100)), 3)


def _calc_depth_score(max_depth: int) -> float:
    return round(1.0 if max_depth <= 3 else max(0.0, 1.0 - (max_depth - 3) * 0.5), 3)


def _calc_todo_score(todo_count: int) -> float:
    return round(max(0.0, 1.0 - todo_count * 0.15), 3)


def _extract_heading_depths(lines: list[str]) -> list[int]:
    depths = []
    for line in lines:
        match = re.match(r"^(#{2,6})\s", line)
        if match:
            depths.append(len(match.group(1)) - 1)
    return depths


TODO_PATTERN = re.compile(r"\b(TODO|FIXME|HACK|XXX|TBD)\b", re.IGNORECASE)


def _compute_readability_metrics(lines: list[str]) -> dict:
    line_lengths = [len(line) for line in lines if line.strip()]
    avg_line_length = sum(line_lengths) / len(line_lengths) if line_lengths else 0
    heading_depths = _extract_heading_depths(lines)
    max_depth = max(heading_depths) if heading_depths else 0
    todo_count = sum(1 for line in lines if TODO_PATTERN.search(line))
    return {
        "avg_line_length": avg_line_length,
        "max_depth": max_depth,
        "todo_count": todo_count,
    }


def readability_score(content: str) -> dict:
    if not content or not content.strip():
        return {
            "avg_line_length": 0,
            "max_depth": 0,
            "todo_count": 0,
            "score": 1.0,
        }

    lines = content.split("\n")
    metrics = _compute_readability_metrics(lines)
    avg_line_length = metrics["avg_line_length"]
    max_depth = metrics["max_depth"]
    todo_count = metrics["todo_count"]
    length_score = _calc_line_length_score(avg_line_length)
    depth_score = _calc_depth_score(max_depth)
    todo_score = _calc_todo_score(todo_count)
    combined = (length_score + depth_score + todo_score) / 3.0

    return {
        "avg_line_length": round(avg_line_length, 1),
        "max_depth": max_depth,
        "todo_count": todo_count,
        "length_score": length_score,
        "depth_score": depth_score,
        "todo_score": todo_score,
        "score": round(combined, 3),
    }


def _check_has_name(fm, content: str) -> bool:
    return bool((fm and fm.get("name")) or re.search(r"^#\s+\S", content, re.MULTILINE))


def _check_has_triggers(fm, content: str) -> bool:
    return bool(_has_section(content, r"Triggers|TRIGGERS?|触发")) or bool(
        fm and (fm.get("triggers") or fm.get("TRIGGERS") or fm.get("TRIGGER"))
    )


def _check_completeness_checks(content: str) -> dict:
    fm = _extract_frontmatter(content)
    if not isinstance(fm, dict):
        fm = None
    return {
        "has_name": _check_has_name(fm, content),
        "has_description": bool(fm and fm.get("description")),
        "has_triggers": _check_has_triggers(fm, content),
        "has_workflow": bool(_has_section(content, r"Workflow|Process|Flow|流程|步骤")),
        "has_anti_patterns": bool(_has_section(content, r"Anti-Patterns|反模式")),
    }


def completeness_score(content: str) -> dict:
    if not content or not content.strip():
        return {
            "has_name": False,
            "has_description": False,
            "has_triggers": False,
            "has_workflow": False,
            "has_anti_patterns": False,
            "score": 0.0,
        }

    checks_dict = _check_completeness_checks(content)
    checks = list(checks_dict.values())[:-1]  # exclude 'score' key
    score = sum(checks) / len(checks) if checks else 0.0

    return {**checks_dict, "score": round(score, 3)}


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
            "patterns": [],
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

    patterns = detect_freshness_patterns(content)

    return {
        "outdated_refs": outdated_refs,
        "has_version": has_version,
        "is_beta": is_beta,
        "score": round(score, 3),
        "patterns": [_freshness_finding_to_dict(f) for f in patterns],
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
            r_pct * w["readability"] + c_pct * w["completeness"] + f_pct * w["freshness"]
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
    return bool(
        re.search(rf"^##\s+[^#\n]*{pattern}[^#\n]*$", content, re.MULTILINE | re.IGNORECASE)
    )


# ─── Freshness Pattern Detectors ──────────────────────────────────────────

SHADOWED_BUILTINS = frozenset({
    "list", "dict", "set", "str", "int", "float", "bool", "tuple", "frozenset",
    "complex", "bytes", "bytearray", "id", "input", "format", "map", "filter",
    "range", "hash", "len", "object", "type", "print", "exec", "eval", "compile",
    "open", "iter", "next", "super", "property", "classmethod", "staticmethod",
    "repr", "ascii", "bin", "hex", "oct", "ord", "chr", "abs", "round", "min",
    "max", "sum", "any", "all", "zip", "sorted", "reversed", "enumerate", "isinstance",
    "issubclass", "callable", "vars", "locals", "globals", "dir", "getattr",
    "setattr", "hasattr", "delattr", "breakpoint", "copyright", "credits",
    "exit", "help", "license", "quit", "__import__",
})

_DEPRECATED_DECORATOR = re.compile(r"^\s*@deprecated\b", re.MULTILINE | re.IGNORECASE)
_STALE_TODO = re.compile(r"\b(TODO|FIXME|HACK|XXX|TBD)\b", re.IGNORECASE)
_IMPORT_SHADOW = re.compile(r"^\s*import\s+(\w+)", re.MULTILINE)
_FROM_IMPORT_SHADOW = re.compile(r"^\s*from\s+\S+\s+import\s+(.+)", re.MULTILINE)
_ASSIGNMENT_SHADOW = re.compile(r"^\s*([a-z_]\w*)\s*=\s*(?!=)", re.MULTILINE)
_ALIAS_SHADOW = re.compile(r"\bas\s+(\w+)", re.MULTILINE)
_CATCH_ALL = re.compile(r"^\s*except\s*(Exception)?\s*:", re.MULTILINE)
_CREDENTIAL_PATTERNS = [
    re.compile(r"""["']sk[_-][^"']*["']""", re.IGNORECASE),
    re.compile(r"""\bapi[_-]?key\s*=\s*["'][^"']+["']""", re.IGNORECASE),
    re.compile(r"""\bsecret\s*=\s*["'][^"']+["']""", re.IGNORECASE),
]


def detect_deprecated_api(content: str) -> list[FreshnessFinding]:
    """Detect @deprecated decorators."""
    if not content:
        return []
    findings = []
    for i, line in enumerate(content.split("\n"), 1):
        if _DEPRECATED_DECORATOR.match(line):
            findings.append(FreshnessFinding(
                line_number=i,
                pattern_type="deprecated_api",
                severity="high",
                description="Deprecated API usage detected",
            ))
    return findings


def detect_stale_todo(
    content: str, file_path: str | None = None
) -> list[FreshnessFinding]:
    """Detect TODO/FIXME/HACK comments older than 90 days via git blame."""
    if not content:
        return []
    lines = content.split("\n")
    todo_lines = [
        (i + 1, line) for i, line in enumerate(lines) if _STALE_TODO.search(line)
    ]
    if not todo_lines:
        return []

    if file_path is None:
        findings = []
        for ln, line in todo_lines:
            m = _STALE_TODO.search(line)
            if m:
                findings.append(FreshnessFinding(
                    line_number=ln,
                    pattern_type="stale_todo",
                    severity="low",
                    description=f"Stale {m.group(1)} comment (no git info)",
                ))
        return findings

    try:
        result = subprocess.run(
            ["git", "blame", "--porcelain", file_path],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            findings = []
            for ln, line in todo_lines:
                m = _STALE_TODO.search(line)
                if m:
                    findings.append(FreshnessFinding(
                        line_number=ln,
                        pattern_type="stale_todo",
                        severity="low",
                        description=f"Stale {m.group(1)} comment (git blame failed)",
                    ))
            return findings
    except (subprocess.SubprocessError, OSError):
        findings = []
        for ln, line in todo_lines:
            m = _STALE_TODO.search(line)
            if m:
                findings.append(FreshnessFinding(
                    line_number=ln,
                    pattern_type="stale_todo",
                    severity="low",
                    description=f"Stale {m.group(1)} comment (git unavailable)",
                ))
        return findings

    now = time.time()
    cutoff = now - 90 * 86400
    line_dates: dict[int, int] = {}
    current_time = None
    current_line_num = None
    for blame_line in result.stdout.split("\n"):
        parts = blame_line.split()
        if len(parts) >= 3 and len(parts[0]) == 40:
            try:
                current_line_num = int(parts[2])
            except (ValueError, IndexError):
                pass
        elif blame_line.startswith("author-time "):
            try:
                current_time = int(blame_line.split()[1])
            except (ValueError, IndexError):
                pass
        elif (
            blame_line.startswith("\t")
            and current_time is not None
            and current_line_num is not None
        ):
            line_dates[current_line_num] = current_time
            current_time = None
            current_line_num = None

    findings = []
    for ln, line in todo_lines:
        m = _STALE_TODO.search(line)
        if not m:
            continue
        author_time = line_dates.get(ln)
        if author_time is None or author_time < cutoff:
            days = (
                int((now - author_time) / 86400) if author_time else "unknown"
            )
            findings.append(FreshnessFinding(
                line_number=ln,
                pattern_type="stale_todo",
                severity="low",
                description=f"Stale {m.group(1)} comment ({days} days old)",
            ))
    return findings


def detect_shadowed_builtins(content: str) -> list[FreshnessFinding]:
    """Detect imports or variable names that shadow Python builtins."""
    if not content:
        return []
    findings = []
    for i, line in enumerate(content.split("\n"), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        m = _IMPORT_SHADOW.match(line)
        if m and m.group(1) in SHADOWED_BUILTINS:
            findings.append(FreshnessFinding(
                line_number=i,
                pattern_type="shadowed_builtin",
                severity="high",
                description=f"Import shadows builtin '{m.group(1)}'",
            ))
            continue

        m = _FROM_IMPORT_SHADOW.match(line)
        if m:
            imports_str = m.group(1)
            alias_m = _ALIAS_SHADOW.search(imports_str)
            if alias_m and alias_m.group(1) in SHADOWED_BUILTINS:
                findings.append(FreshnessFinding(
                    line_number=i,
                    pattern_type="shadowed_builtin",
                    severity="high",
                    description=f"Import alias shadows builtin '{alias_m.group(1)}'",
                ))
                continue
            for name in imports_str.split(","):
                name = name.strip()
                alias_m2 = _ALIAS_SHADOW.search(name)
                if alias_m2:
                    check = alias_m2.group(1)
                else:
                    check = name.split()[0] if name.split() else name
                if check in SHADOWED_BUILTINS:
                    findings.append(FreshnessFinding(
                        line_number=i,
                        pattern_type="shadowed_builtin",
                        severity="high",
                        description=f"Import shadows builtin '{check}'",
                    ))
                    break
            continue

        m = _ASSIGNMENT_SHADOW.match(line)
        if m and m.group(1) in SHADOWED_BUILTINS:
            findings.append(FreshnessFinding(
                line_number=i,
                pattern_type="shadowed_builtin",
                severity="medium",
                description=f"Variable shadows builtin '{m.group(1)}'",
            ))
    return findings


def detect_catch_all_except(content: str) -> list[FreshnessFinding]:
    """Detect except:/except Exception: without re-raise or logging."""
    if not content:
        return []
    lines = content.split("\n")
    findings = []
    i = 0
    while i < len(lines):
        m = _CATCH_ALL.match(lines[i])
        if m:
            except_line = i + 1
            is_bare = m.group(1) is None
            except_indent = len(lines[i]) - len(lines[i].lstrip())
            has_handling = False
            j = i + 1
            while j < len(lines):
                next_line = lines[j]
                if not next_line.strip():
                    j += 1
                    continue
                next_indent = len(next_line) - len(next_line.lstrip())
                if next_indent <= except_indent:
                    break
                if re.search(r"\braise\b", next_line):
                    has_handling = True
                    break
                if re.search(r"\b(?:logger|logging)\b", next_line):
                    has_handling = True
                    break
                j += 1
            if not has_handling:
                findings.append(FreshnessFinding(
                    line_number=except_line,
                    pattern_type="catch_all_except",
                    severity="high" if is_bare else "medium",
                    description=(
                        "Bare except without re-raise or logging"
                        if is_bare
                        else "catch-all except Exception without re-raise or logging"
                    ),
                ))
            i = j
        else:
            i += 1
    return findings


def detect_hardcoded_credentials(
    content: str, is_test_file: bool = False
) -> list[FreshnessFinding]:
    """Detect string literals matching API key patterns."""
    if not content or is_test_file:
        return []
    findings = []
    for i, line in enumerate(content.split("\n"), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for pattern in _CREDENTIAL_PATTERNS:
            if pattern.search(line):
                findings.append(FreshnessFinding(
                    line_number=i,
                    pattern_type="hardcoded_credential",
                    severity="critical",
                    description="Potential hardcoded credential detected",
                ))
                break
    return findings


def detect_freshness_patterns(
    content: str, file_path: str | None = None, is_test_file: bool = False
) -> list[FreshnessFinding]:
    """Run all freshness pattern detectors and return combined findings."""
    if not content:
        return []
    findings: list[FreshnessFinding] = []
    findings.extend(detect_deprecated_api(content))
    findings.extend(detect_stale_todo(content, file_path=file_path))
    findings.extend(detect_shadowed_builtins(content))
    findings.extend(detect_catch_all_except(content))
    findings.extend(detect_hardcoded_credentials(content, is_test_file=is_test_file))
    return findings
