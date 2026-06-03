"""SkillsBench sweet-spot analysis — multi-skill cognitive overload detection.

Identifies optimal skill loading configurations:
- Sweet spot: number of skills where performance is optimal
- Cognitive overload: point where adding more skills degrades performance
- Conflict zones: skill combinations that interfere with each other
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillLoadResult:
    """Result of loading N skills simultaneously."""

    skill_count: int
    skills_loaded: list[str]
    trigger_accuracy: float
    response_quality: float
    latency_ms: float
    conflicts_detected: int

    @property
    def overall_score(self) -> float:
        """Weighted overall score."""
        return 0.4 * self.trigger_accuracy + 0.4 * self.response_quality + 0.2 * (1.0 - min(1.0, self.latency_ms / 10000))


@dataclass
class SweetSpotAnalysis:
    """Analysis of skill loading sweet spot."""

    sweet_spot_count: int  # Optimal number of concurrent skills
    overload_threshold: int  # Point where performance degrades
    max_recommended: int  # Maximum recommended skills
    degradation_curve: list[dict]  # skill_count -> score mapping
    conflict_pairs: list[tuple[str, str]]  # Skill pairs that conflict
    recommendation: str


class SkillsBenchAnalyzer:
    """Analyzes multi-skill loading to find sweet spots and overload points."""

    # Default thresholds
    SWEET_SPOT_THRESHOLD = 0.85  # Score must be >= this to be in sweet spot
    OVERLOAD_THRESHOLD = 0.70  # Score below this indicates overload
    MAX_SKILLS_HARD_LIMIT = 10  # Absolute maximum skills to test

    def __init__(
        self,
        sweet_spot_threshold: float = SWEET_SPOT_THRESHOLD,
        overload_threshold: float = OVERLOAD_THRESHOLD,
    ):
        self.sweet_spot_threshold = sweet_spot_threshold
        self.overload_threshold = overload_threshold

    def analyze(self, results: list[SkillLoadResult]) -> SweetSpotAnalysis:
        """Analyze skill loading results to find sweet spot.

        Args:
            results: List of SkillLoadResult for different skill counts

        Returns:
            SweetSpotAnalysis with recommendations
        """
        if not results:
            return SweetSpotAnalysis(
                sweet_spot_count=0,
                overload_threshold=0,
                max_recommended=0,
                degradation_curve=[],
                conflict_pairs=[],
                recommendation="No data available for analysis",
            )

        # Sort by skill count
        sorted_results = sorted(results, key=lambda r: r.skill_count)

        # Build degradation curve
        curve = [
            {"skill_count": r.skill_count, "score": round(r.overall_score, 3)}
            for r in sorted_results
        ]

        # Find sweet spot (highest score before degradation)
        sweet_spot = self._find_sweet_spot(sorted_results)

        # Find overload threshold
        overload = self._find_overload_threshold(sorted_results)

        # Detect conflict pairs
        conflicts = self._detect_conflicts(sorted_results)

        # Generate recommendation
        recommendation = self._generate_recommendation(sweet_spot, overload, conflicts)

        return SweetSpotAnalysis(
            sweet_spot_count=sweet_spot,
            overload_threshold=overload,
            max_recommended=max(sweet_spot, 1),
            degradation_curve=curve,
            conflict_pairs=conflicts,
            recommendation=recommendation,
        )

    def _find_sweet_spot(self, results: list[SkillLoadResult]) -> int:
        """Find the skill count with optimal performance."""
        best_count = 1
        best_score = 0.0

        for r in results:
            if r.overall_score >= self.sweet_spot_threshold and r.overall_score > best_score:
                best_score = r.overall_score
                best_count = r.skill_count

        return best_count

    def _find_overload_threshold(self, results: list[SkillLoadResult]) -> int:
        """Find the skill count where performance drops below threshold."""
        for r in sorted(results, key=lambda x: x.skill_count):
            if r.overall_score < self.overload_threshold:
                return max(1, r.skill_count - 1)

        # If never drops below threshold, return max tested
        return results[-1].skill_count if results else 1

    def _detect_conflicts(self, results: list[SkillLoadResult]) -> list[tuple[str, str]]:
        """Detect skill pairs that cause conflicts."""
        conflicts = []

        # Look for results with high conflict counts
        for r in results:
            if r.conflicts_detected > 0 and len(r.skills_loaded) == 2:
                # Direct pair conflict
                if len(r.skills_loaded) >= 2:
                    conflicts.append((r.skills_loaded[0], r.skills_loaded[1]))

        return conflicts

    def _generate_recommendation(
        self, sweet_spot: int, overload: int, conflicts: list[tuple[str, str]]
    ) -> str:
        """Generate human-readable recommendation."""
        parts = []

        if sweet_spot >= 3:
            parts.append(f"Optimal loading: {sweet_spot} concurrent skills")
        else:
            parts.append(f"Conservative loading recommended: max {sweet_spot} skills")

        if overload > sweet_spot:
            parts.append(f"Performance degrades beyond {overload} skills")

        if conflicts:
            conflict_names = [f"{a}+{b}" for a, b in conflicts[:3]]
            parts.append(f"Known conflicts: {', '.join(conflict_names)}")

        return ". ".join(parts)

    def quick_check(self, skill_names: list[str]) -> dict[str, Any]:
        """Quick check if a skill set is within safe limits.

        Args:
            skill_names: List of skill names to check

        Returns:
            Dict with status and recommendations
        """
        count = len(skill_names)

        if count <= 3:
            return {"status": "safe", "message": f"{count} skills: within optimal range"}
        elif count <= 5:
            return {"status": "caution", "message": f"{count} skills: approaching overload threshold"}
        elif count <= self.MAX_SKILLS_HARD_LIMIT:
            return {"status": "warning", "message": f"{count} skills: may cause cognitive overload"}
        else:
            return {
                "status": "error",
                "message": f"{count} skills: exceeds hard limit of {self.MAX_SKILLS_HARD_LIMIT}",
            }
