"""Gotchas analyzer — SKILL.md gotchas density and quality analysis.

Density analysis measures what proportion of a SKILL.md's lines are
team-specific gotchas (as opposed to generic step instructions that
the model already knows). This implements the Anthropic principle:

    "The truly valuable content is usually gotchas. Claude knows how to
    write code and read codebases — writing that into a Skill just
    adds context without adding value."

References:
    - Anthropic: "Lessons from building Claude Code: How we use skills"
    - Issue #75: Anthropic methodology alignment
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── Gotchas Density Analysis ─────────────────────────────────────

# Patterns that indicate generic (non-gotcha) content
GENERIC_STEP_PATTERNS: list[re.Pattern] = [
    re.compile(r"^(#{1,3}\s+)?(step|phase|stage)\s+\d", re.IGNORECASE),
    re.compile(r"^(#{1,3}\s+)?(overview|introduction|background)", re.IGNORECASE),
    re.compile(r"^\d+\.\s+(分析|implement|create|add|build|write|run)", re.IGNORECASE),
    re.compile(r"^(use when|triggers?|when to use)", re.IGNORECASE),
    re.compile(r"^(description|name):", re.IGNORECASE),
]

# Patterns that indicate high-value gotcha content
GOTCHA_PATTERNS: list[re.Pattern] = [
    re.compile(
        r"(don'?t|do not|never|always|must|must not|avoid|watch out|caveat|注意|陷阱)",
        re.IGNORECASE,
    ),
    re.compile(r"(gotcha|gotchas?|anti[-\s]?pattern|pitfall)", re.IGNORECASE),
    re.compile(r"(but only|except when|unless|however|beware)", re.IGNORECASE),
    re.compile(r"(this is (not|different)|unlike|contrary to)", re.IGNORECASE),
    re.compile(r"(team.?specific|our convention|our pattern|we found|we learned)", re.IGNORECASE),
    re.compile(r"(actually|in practice|real world|production|experience shows)", re.IGNORECASE),
    re.compile(r"(staging|prod|production) (return|behave|fail)", re.IGNORECASE),
    re.compile(r"(API (key|secret|token)|credential|certificate)", re.IGNORECASE),
    re.compile(r"(rate limit|throttle|timeout|retry|backoff)", re.IGNORECASE),
    re.compile(r"(migration|deprecat|legacy|version \d|v[0-9]+)", re.IGNORECASE),
]

# Patterns that mark generic "this is what the model already knows" content
KNOWN_LLM_CAPABILITY_PATTERNS: list[re.Pattern] = [
    re.compile(r"(read|write|edit) (the )?(file|code)", re.IGNORECASE),
    re.compile(r"(search|grep|find) (for|the|in) (code|file)", re.IGNORECASE),
    re.compile(r"(run|execute) (the )?(command|test)", re.IGNORECASE),
    re.compile(r"(ask|request|consult) (the )?(user|oracle)", re.IGNORECASE),
]

GOTCHAS_DENSITY_TARGET = 0.15  # 15% of lines should be gotchas


@dataclass
class GotchasDensityResult:
    """Result of SKILL.md gotchas density analysis."""

    total_lines: int = 0
    gotcha_lines: int = 0
    density: float = 0.0
    above_target: bool = False
    top_gotchas: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        """PASS if gotchas density meets target."""
        if self.total_lines == 0:
            return "FAIL"
        if self.above_target:
            return "PASS"
        return "FAIL"


def analyze_gotchas_density(skill_md_content: str) -> GotchasDensityResult:
    """Analyze gotchas density in a SKILL.md file.

    Args:
        skill_md_content: Full text content of SKILL.md.

    Returns:
        GotchasDensityResult with density metrics and issues.
    """
    if not skill_md_content.strip():
        return GotchasDensityResult(
            issues=["Empty SKILL.md content"],
        )

    lines = skill_md_content.split("\n")
    # Strip frontmatter
    content_lines = _strip_frontmatter(lines)
    total_relevant = len(content_lines)

    if total_relevant == 0:
        return GotchasDensityResult(total_lines=0, issues=["No content after frontmatter"])

    # Count gotcha lines
    gotcha_lines: list[str] = []
    for line in content_lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Skip generic/known patterns
        if any(p.search(stripped) for p in GENERIC_STEP_PATTERNS):
            continue
        if any(p.search(stripped) for p in KNOWN_LLM_CAPABILITY_PATTERNS):
            continue
        # Check if it's a gotcha
        if any(p.search(stripped) for p in GOTCHA_PATTERNS):
            gotcha_lines.append(stripped)

    density = len(gotcha_lines) / total_relevant if total_relevant > 0 else 0.0
    above_target = density >= GOTCHAS_DENSITY_TARGET

    issues: list[str] = []
    if not above_target:
        target_pct = int(GOTCHAS_DENSITY_TARGET * 100)
        actual_pct = int(density * 100)
        issues.append(
            f"Gotchas density is {actual_pct}% (target: ≥{target_pct}%). "
            "Add team-specific gotchas: edge cases, environment quirks, "
            "API behaviors that differ from documentation."
        )
        if density == 0:
            issues.append(
                "No gotcha patterns detected. SKILL.md may contain only "
                "generic instructions the model already knows. Consider "
                "adding team-specific experience (gotchas, anti-patterns, "
                "production caveats)."
            )

    return GotchasDensityResult(
        total_lines=total_relevant,
        gotcha_lines=len(gotcha_lines),
        density=round(density, 3),
        above_target=above_target,
        top_gotchas=gotcha_lines[:10],
        issues=issues,
    )


def _strip_frontmatter(lines: list[str]) -> list[str]:
    """Remove YAML frontmatter from lines."""
    if not lines or not lines[0].startswith("---"):
        return lines
    end_idx = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx >= 0:
        return lines[end_idx + 1 :]
    return lines


# ── Verification Assertion Strength Analysis ─────────────────────

# Patterns for different assertion strengths
VERIFICATION_PATTERNS = {
    "programmatic_assertion": [
        re.compile(r"(assert|verify|check|validate)\s+(that\s+)?", re.IGNORECASE),
        re.compile(r"(status.?code|exit.?code|return.?code)", re.IGNORECASE),
        re.compile(r"(data|result|output|response)\s*(==|!=|contains?|in\b)", re.IGNORECASE),
    ],
    "state_verification": [
        re.compile(r"(check|verify|assert).*(state|status|condition|exist)", re.IGNORECASE),
        re.compile(r"(database|db|table|record).*(has|contain|exist|count)", re.IGNORECASE),
        re.compile(r"(file|directory|path).*(exist|create|delete|modif)", re.IGNORECASE),
    ],
    "visual_verification": [
        re.compile(r"(screenshot|image|snapshot|visual)", re.IGNORECASE),
        re.compile(r"(compare|diff|match).*(image|screenshot|snapshot)", re.IGNORECASE),
    ],
}


@dataclass
class VerificationStrengthResult:
    """Result of verification/assertion strength analysis."""

    has_programmatic_assertions: bool = False
    has_state_verification: bool = False
    has_visual_verification: bool = False
    assertion_types_found: list[str] = field(default_factory=list)
    score: float = 0.0  # 0-100
    issues: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.score >= 50.0


def analyze_verification_strength(skill_md_content: str) -> VerificationStrengthResult:
    """Analyze verification/assertion strength in a SKILL.md file.

    Checks for programmatic assertions, state verification, and
    visual verification patterns. Based on the Anthropic principle
    that Product Verification is the highest-value skill category.

    Args:
        skill_md_content: Full text content of SKILL.md.

    Returns:
        VerificationStrengthResult with analysis.
    """
    if not skill_md_content.strip():
        return VerificationStrengthResult(
            score=0.0,
            issues=["Empty SKILL.md content"],
        )

    found_types: list[str] = []
    issues: list[str] = []
    score = 0.0

    for category, patterns in VERIFICATION_PATTERNS.items():
        has_category = any(p.search(skill_md_content) for p in patterns)
        if has_category:
            found_types.append(category)
            if category == "programmatic_assertion":
                score += 50.0
            elif category == "state_verification":
                score += 30.0
            elif category == "visual_verification":
                score += 20.0

    if not found_types:
        issues.append(
            "No verification/assertion patterns found. "
            "Consider adding programmatic assertions (status codes, "
            "state checks, data validation) to strengthen eval reliability."
        )

    return VerificationStrengthResult(
        has_programmatic_assertions="programmatic_assertion" in found_types,
        has_state_verification="state_verification" in found_types,
        has_visual_verification="visual_verification" in found_types,
        assertion_types_found=found_types,
        score=min(score, 100.0),
        issues=issues,
    )


# ── Exclusion Scenarios Analysis ──────────────────────────────────

EXCLUSION_PATTERNS: list[re.Pattern] = [
    re.compile(r"do\s+not\s+(trigger|activate|use|run|apply|invoke)", re.IGNORECASE),
    re.compile(r"don'?t\s+(trigger|activate|use|run|apply)", re.IGNORECASE),
    re.compile(r"never\s+(trigger|activate|use|run|apply)", re.IGNORECASE),
    re.compile(r"不触发|不激活|不应使用|不要触发|排除|不适用", re.IGNORECASE),
    re.compile(r"not\s+(intended|applicable|suitable)\s+for", re.IGNORECASE),
    re.compile(r"excluded\s+from", re.IGNORECASE),
    re.compile(r"should\s+not\s+be\s+(triggered|activated|used|applied)", re.IGNORECASE),
]


@dataclass
class ExclusionResult:
    """Result of exclusion scenario analysis in a skill description."""

    has_exclusion: bool = False
    exclusion_count: int = 0
    exclusion_phrases: list[str] = field(default_factory=list)
    score: float = 0.0
    issues: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.score >= 50.0


def analyze_exclusion_scenarios(description: str) -> ExclusionResult:
    """Analyze a skill description for exclusion scenario coverage.

    Exclusion scenarios define when a skill should NOT trigger — these are
    critical for preventing false positives. This function matches against
    English and Chinese exclusion phrases and scores the coverage.

    Scoring: 0 matches → 0, 1 → 40, 2 → 60, 3+ → 80, 5+ → 100.
    Threshold: >= 50 passes.

    Args:
        description: The skill description text to analyze.

    Returns:
        ExclusionResult with match count, phrases, score, and issues.
    """
    if not description.strip():
        return ExclusionResult(
            issues=["Empty description — no exclusion scenarios found"],
        )

    matched_phrases: list[str] = []
    for pattern in EXCLUSION_PATTERNS:
        for m in pattern.finditer(description):
            matched_phrases.append(m.group())

    exclusion_count = len(matched_phrases)
    has_exclusion = exclusion_count > 0

    if exclusion_count >= 5:
        score = 100.0
    elif exclusion_count >= 3:
        score = 80.0
    elif exclusion_count >= 2:
        score = 60.0
    elif exclusion_count == 1:
        score = 40.0
    else:
        score = 0.0

    issues: list[str] = []
    if score < 50.0:
        if exclusion_count == 0:
            issues.append(
                "No exclusion scenarios defined. Consider specifying when this "
                "skill should NOT trigger (e.g., 'Do not trigger for production "
                "databases', '不触发此技能当...'). Exclusion scenarios reduce false "
                "positives and improve L1 trigger accuracy."
            )
        else:
            issues.append(
                f"Only {exclusion_count} exclusion scenario(s) found (score={score:.0f}). "
                "Consider adding more exclusion scenarios to clearly define when NOT "
                "to trigger this skill."
            )

    return ExclusionResult(
        has_exclusion=has_exclusion,
        exclusion_count=exclusion_count,
        exclusion_phrases=matched_phrases,
        score=score,
        issues=issues,
    )


__all__ = [
    "GotchasDensityResult",
    "analyze_gotchas_density",
    "VerificationStrengthResult",
    "analyze_verification_strength",
    "ExclusionResult",
    "analyze_exclusion_scenarios",
    "EXCLUSION_PATTERNS",
    "GOTCHAS_DENSITY_TARGET",
]
