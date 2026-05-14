"""Multi-skill conflict detection — identifies interference when multiple skills load simultaneously."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from itertools import combinations
from typing import Any


class ConflictType(str, Enum):
    TRIGGER_OVERLAP = "trigger_overlap"
    PROMPT_CONTAMINATION = "prompt_contamination"
    TOKEN_OVERFLOW = "token_overflow"


class ConflictSeverity(str, Enum):
    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


DEFAULT_TOKEN_BUDGET = 100_000


@dataclass
class SkillConflict:
    conflict_type: ConflictType
    severity: ConflictSeverity
    skill_a: str
    skill_b: str
    description: str = ""
    trigger_word: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        base = f"[{self.conflict_type.value}] {self.skill_a} <-> {self.skill_b}"
        if self.trigger_word:
            base += f" (trigger: '{self.trigger_word}')"
        base += f" severity={self.severity.value}"
        if self.description:
            base += f": {self.description}"
        return base

    def to_dict(self) -> dict[str, Any]:
        return {
            "conflict_type": self.conflict_type.value,
            "severity": self.severity.value,
            "skill_a": self.skill_a,
            "skill_b": self.skill_b,
            "description": self.description,
            "trigger_word": self.trigger_word,
            "details": self.details,
        }


class MultiSkillAnalyzer:
    """Analyses N skills loaded into the same context for interference."""

    def __init__(self) -> None:
        self._skills: list[dict[str, Any]] = []

    def inject_multiple_skills(self, skills: list[dict[str, Any]]) -> None:
        self._skills = list(skills)

    # ── Trigger conflicts ───────────────────────────────────────────────

    def test_trigger_conflicts(self) -> list[SkillConflict]:
        if len(self._skills) < 2:
            return []

        conflicts: list[SkillConflict] = []
        for a, b in combinations(enumerate(self._skills), 2):
            idx_a, sa = a
            idx_b, sb = b
            triggers_a = {t.lower().strip() for t in sa.get("triggers", []) if t.strip()}
            triggers_b = {t.lower().strip() for t in sb.get("triggers", []) if t.strip()}
            if not triggers_a or not triggers_b:
                continue

            exact = triggers_a & triggers_b
            substring: set[str] = set()
            for ta in triggers_a:
                for tb in triggers_b:
                    if ta != tb and (ta in tb or tb in ta):
                        substring.add(ta if len(ta) <= len(tb) else tb)

            all_overlaps = exact | substring
            for word in all_overlaps:
                severity = self._trigger_severity(len(exact), len(substring))
                conflicts.append(SkillConflict(
                    conflict_type=ConflictType.TRIGGER_OVERLAP,
                    severity=severity,
                    skill_a=sa["name"],
                    skill_b=sb["name"],
                    trigger_word=word,
                    description=f"Both skills trigger on '{word}'",
                ))

        return conflicts

    def _trigger_severity(self, exact_count: int, substring_count: int) -> ConflictSeverity:
        total = exact_count + substring_count
        if total == 0:
            return ConflictSeverity.NONE
        if exact_count >= 3 or substring_count >= 5:
            return ConflictSeverity.HIGH
        if exact_count >= 2 or substring_count >= 3:
            return ConflictSeverity.MODERATE
        if exact_count >= 1:
            return ConflictSeverity.LOW
        return ConflictSeverity.LOW

    # ── Prompt contamination ────────────────────────────────────────────

    def test_prompt_contamination(self) -> list[SkillConflict]:
        if len(self._skills) < 2:
            return []

        conflicts: list[SkillConflict] = []
        seen_pairs: set[tuple[str, str]] = set()

        for a, b in combinations(enumerate(self._skills), 2):
            _, sa = a
            _, sb = b
            pair_key = (sa["name"], sb["name"])
            if pair_key in seen_pairs:
                continue

            reasons: list[str] = []
            overlap_items: list[str] = []

            wf_overlap = self._set_overlap(
                {s.get("name", "") for s in sa.get("workflow_steps", []) if s.get("name")},
                {s.get("name", "") for s in sb.get("workflow_steps", []) if s.get("name")},
            )
            if wf_overlap:
                reasons.append(f"shared workflow steps: {', '.join(sorted(wf_overlap))}")
                overlap_items.extend(wf_overlap)

            ap_overlap = self._set_overlap(
                {s.lower() for s in sa.get("anti_patterns", [])},
                {s.lower() for s in sb.get("anti_patterns", [])},
            )
            if ap_overlap:
                reasons.append(f"shared anti-patterns: {', '.join(sorted(ap_overlap))}")
                overlap_items.extend(ap_overlap)

            of_overlap = self._set_overlap(
                {f.lower() for f in sa.get("output_format", [])},
                {f.lower() for f in sb.get("output_format", [])},
            )
            if of_overlap:
                reasons.append(f"shared output format fields: {', '.join(sorted(of_overlap))}")
                overlap_items.extend(of_overlap)

            desc_triggers = self._description_hijack_risk(sa, sb)
            if desc_triggers:
                reasons.append(f"skill '{sa['name']}' description mentions triggers of '{sb['name']}'")

            desc_similarity = self._description_similarity(sa, sb)
            if desc_similarity > 0.3:
                reasons.append(f"high description keyword overlap ({desc_similarity:.0%})")

            if reasons:
                seen_pairs.add(pair_key)
                severity = self._contamination_severity(len(reasons), desc_similarity)
                conflicts.append(SkillConflict(
                    conflict_type=ConflictType.PROMPT_CONTAMINATION,
                    severity=severity,
                    skill_a=sa["name"],
                    skill_b=sb["name"],
                    description="; ".join(reasons),
                    details={"shared_items": sorted(set(overlap_items)), "description_overlap": round(desc_similarity, 4)},
                ))

        return conflicts

    def _description_hijack_risk(self, sa: dict, sb: dict) -> list[str]:
        desc = sa.get("description", "").lower()
        if not desc:
            return []
        triggers_b = {t.lower().strip() for t in sb.get("triggers", []) if t.strip()}
        return [t for t in triggers_b if t and len(t) > 2 and t in desc]

    @staticmethod
    def _description_similarity(sa: dict, sb: dict) -> float:
        desc_a = set(re.findall(r"\b\w{4,}\b", sa.get("description", "").lower()))
        desc_b = set(re.findall(r"\b\w{4,}\b", sb.get("description", "").lower()))
        if not desc_a or not desc_b:
            return 0.0
        return len(desc_a & desc_b) / max(len(desc_a | desc_b), 1)

    @staticmethod
    def _set_overlap(a: set, b: set) -> set:
        return a & b

    @staticmethod
    def _contamination_severity(reason_count: int, desc_sim: float) -> ConflictSeverity:
        if reason_count >= 4 or desc_sim > 0.7:
            return ConflictSeverity.HIGH
        if reason_count >= 3 or desc_sim > 0.5:
            return ConflictSeverity.MODERATE
        if reason_count >= 2 or desc_sim > 0.3:
            return ConflictSeverity.LOW
        return ConflictSeverity.LOW

    # ── Token overflow ──────────────────────────────────────────────────

    def test_token_overflow(self, token_budget: int = DEFAULT_TOKEN_BUDGET) -> list[SkillConflict]:
        total_chars = sum(s.get("content_length", 0) for s in self._skills)
        if total_chars <= token_budget:
            return []

        excess = total_chars - token_budget
        severity = self._overflow_severity(excess, token_budget)
        skill_names = [s["name"] for s in self._skills]
        return [SkillConflict(
            conflict_type=ConflictType.TOKEN_OVERFLOW,
            severity=severity,
            skill_a=skill_names[0] if skill_names else "unknown",
            skill_b=skill_names[-1] if len(skill_names) > 1 else "",
            description=f"Combined content ({total_chars:,} chars) exceeds budget ({token_budget:,})",
            details={"total_chars": total_chars, "budget": token_budget, "excess": excess, "skill_count": len(self._skills)},
        )]

    @staticmethod
    def _overflow_severity(excess: int, budget: int) -> ConflictSeverity:
        ratio = excess / budget if budget > 0 else 1.0
        if ratio > 1.0:
            return ConflictSeverity.HIGH
        if ratio > 0.5:
            return ConflictSeverity.MODERATE
        return ConflictSeverity.LOW

    # ── Full analysis ───────────────────────────────────────────────────

    def analyze(self, token_budget: int = DEFAULT_TOKEN_BUDGET) -> dict[str, Any]:
        if not self._skills:
            return {
                "conflicts": [],
                "overall_risk": "none",
                "summary": "No skills loaded — nothing to analyse.",
                "skill_count": 0,
            }

        trigger = self.test_trigger_conflicts()
        contamination = self.test_prompt_contamination()
        overflow = self.test_token_overflow(token_budget)

        all_conflicts = trigger + contamination + overflow

        overall_risk = self._overall_risk(all_conflicts)
        summary = self._build_summary(trigger, contamination, overflow)

        return {
            "conflicts": all_conflicts,
            "overall_risk": overall_risk.value,
            "summary": summary,
            "skill_count": len(self._skills),
            "trigger_conflicts": len(trigger),
            "prompt_contamination_conflicts": len(contamination),
            "token_overflow_conflicts": len(overflow),
        }

    @staticmethod
    def _overall_risk(conflicts: list[SkillConflict]) -> ConflictSeverity:
        if not conflicts:
            return ConflictSeverity.NONE
        severity_order = {
            ConflictSeverity.NONE: 0,
            ConflictSeverity.LOW: 1,
            ConflictSeverity.MODERATE: 2,
            ConflictSeverity.HIGH: 3,
        }
        max_sev = max(conflicts, key=lambda c: severity_order.get(c.severity, 0))
        return max_sev.severity

    @staticmethod
    def _build_summary(
        trigger: list[SkillConflict],
        contamination: list[SkillConflict],
        overflow: list[SkillConflict],
    ) -> str:
        parts: list[str] = []
        if trigger:
            trigger_words = sorted({c.trigger_word for c in trigger})
            words_str = ", ".join(f"'{w}'" for w in trigger_words)
            parts.append(f"Trigger conflicts detected on {len(trigger)} overlaps: {words_str}")
        if contamination:
            parts.append(f"Prompt contamination risk in {len(contamination)} skill pair(s)")
        if overflow:
            o = overflow[0]
            parts.append(f"Token overflow: {o.details.get('total_chars', 0):,} chars vs {o.details.get('budget', 0):,} budget")
        if not parts:
            return "No conflicts detected — skills are safe to combine."
        return "; ".join(parts)
