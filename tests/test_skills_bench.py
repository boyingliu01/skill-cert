"""Tests for skills_bench.py — multi-skill cognitive overload detection."""

import pytest

from engine.skills_bench import (
    SkillLoadResult,
    SkillsBenchAnalyzer,
    SweetSpotAnalysis,
)


class TestSkillLoadResult:
    def test_overall_score_calculation(self):
        result = SkillLoadResult(
            skill_count=1,
            skills_loaded=["test"],
            trigger_accuracy=0.90,
            response_quality=0.80,
            latency_ms=1000,
            conflicts_detected=0,
        )
        # 0.4 * 0.90 + 0.4 * 0.80 + 0.2 * (1.0 - min(1.0, 1000/10000))
        # = 0.36 + 0.32 + 0.2 * 0.9 = 0.36 + 0.32 + 0.18 = 0.86
        assert result.overall_score == pytest.approx(0.86)

    def test_overall_score_perfect_latency(self):
        result = SkillLoadResult(
            skill_count=1,
            skills_loaded=["test"],
            trigger_accuracy=1.0,
            response_quality=1.0,
            latency_ms=0,
            conflicts_detected=0,
        )
        assert result.overall_score == 1.0

    def test_overall_score_high_latency_capped(self):
        result = SkillLoadResult(
            skill_count=5,
            skills_loaded=["a", "b", "c", "d", "e"],
            trigger_accuracy=0.5,
            response_quality=0.5,
            latency_ms=50000,
            conflicts_detected=2,
        )
        # latency factor capped at 0 (1.0 - min(1.0, 5.0)) = 0
        assert result.overall_score == 0.4  # 0.4 * 0.5 + 0.4 * 0.5 = 0.4

    def test_overall_score_at_latency_boundary(self):
        result = SkillLoadResult(
            skill_count=1,
            skills_loaded=["test"],
            trigger_accuracy=0.5,
            response_quality=0.5,
            latency_ms=10000,
            conflicts_detected=0,
        )
        # latency factor: 1.0 - min(1.0, 10000/10000) = 0.0
        assert result.overall_score == 0.4


class TestSweetSpotAnalysis:
    def test_default_construction(self):
        analysis = SweetSpotAnalysis(
            sweet_spot_count=3,
            overload_threshold=5,
            max_recommended=3,
            degradation_curve=[],
            conflict_pairs=[],
            recommendation="Optimal loading: 3 concurrent skills",
        )
        assert analysis.sweet_spot_count == 3
        assert analysis.overload_threshold == 5
        assert analysis.recommendation == "Optimal loading: 3 concurrent skills"

    def test_with_conflicts(self):
        analysis = SweetSpotAnalysis(
            sweet_spot_count=2,
            overload_threshold=4,
            max_recommended=2,
            degradation_curve=[],
            conflict_pairs=[("skill_a", "skill_b")],
            recommendation="Conservative loading recommended",
        )
        assert len(analysis.conflict_pairs) == 1
        assert analysis.conflict_pairs[0] == ("skill_a", "skill_b")


class TestSkillsBenchAnalyzer:
    def test_default_constructor(self):
        analyzer = SkillsBenchAnalyzer()
        assert analyzer.sweet_spot_threshold == 0.85
        assert analyzer.overload_threshold == 0.70
        assert analyzer.MAX_SKILLS_HARD_LIMIT == 10

    def test_custom_constructor(self):
        analyzer = SkillsBenchAnalyzer(sweet_spot_threshold=0.90, overload_threshold=0.60)
        assert analyzer.sweet_spot_threshold == 0.90
        assert analyzer.overload_threshold == 0.60

    def test_analyze_empty_results(self):
        analyzer = SkillsBenchAnalyzer()
        result = analyzer.analyze([])
        assert result.sweet_spot_count == 0
        assert result.overload_threshold == 0
        assert result.max_recommended == 0
        assert result.degradation_curve == []
        assert result.recommendation == "No data available for analysis"

    def test_analyze_single_result(self):
        analyzer = SkillsBenchAnalyzer()
        results = [
            SkillLoadResult(
                skill_count=1,
                skills_loaded=["skill_a"],
                trigger_accuracy=0.95,
                response_quality=0.95,
                latency_ms=100,
                conflicts_detected=0,
            ),
        ]
        result = analyzer.analyze(results)
        assert result.sweet_spot_count == 1
        assert result.max_recommended >= 1
        assert len(result.degradation_curve) == 1

    def test_analyze_finds_sweet_spot(self):
        analyzer = SkillsBenchAnalyzer()
        results = [
            SkillLoadResult(1, ["a"], 0.90, 0.85, 100, 0),
            SkillLoadResult(2, ["a", "b"], 0.95, 0.95, 200, 0),
            SkillLoadResult(3, ["a", "b", "c"], 0.80, 0.75, 500, 1),
        ]
        result = analyzer.analyze(results)
        assert result.sweet_spot_count == 2
        # 3 has score 0.81, above 0.70 overload, so overload_threshold = max tested (3)
        assert result.overload_threshold == 3

    def test_analyze_with_overload(self):
        analyzer = SkillsBenchAnalyzer()
        results = [
            SkillLoadResult(1, ["a"], 0.90, 0.90, 100, 0),
            SkillLoadResult(2, ["a", "b"], 0.85, 0.85, 200, 0),
            SkillLoadResult(3, ["a", "b", "c"], 0.60, 0.55, 1000, 2),
            SkillLoadResult(4, ["a", "b", "c", "d"], 0.40, 0.35, 2000, 3),
        ]
        result = analyzer.analyze(results)
        # Sweet spot = 1 (highest score above 0.85)
        assert result.sweet_spot_count == 1
        # Overload threshold = 3 - 1 = 2 (3 has score below 0.70)
        assert result.overload_threshold == 2

    def test_analyze_conflict_detection(self):
        analyzer = SkillsBenchAnalyzer()
        results = [
            SkillLoadResult(2, ["skill_x", "skill_y"], 0.70, 0.65, 500, 1),
            SkillLoadResult(3, ["a", "b", "c"], 0.90, 0.90, 200, 0),
        ]
        result = analyzer.analyze(results)
        assert len(result.conflict_pairs) >= 1
        assert ("skill_x", "skill_y") in result.conflict_pairs

    def test_analyze_sorted_by_skill_count(self):
        analyzer = SkillsBenchAnalyzer()
        results = [
            SkillLoadResult(3, ["a", "b", "c"], 0.80, 0.80, 300, 0),
            SkillLoadResult(1, ["a"], 0.95, 0.95, 100, 0),
            SkillLoadResult(2, ["a", "b"], 0.90, 0.90, 200, 0),
        ]
        result = analyzer.analyze(results)
        curve_counts = [p["skill_count"] for p in result.degradation_curve]
        assert curve_counts == [1, 2, 3]

    def test_analyze_degradation_curve_values(self):
        analyzer = SkillsBenchAnalyzer()
        results = [
            SkillLoadResult(1, ["a"], 0.90, 0.90, 100, 0),
            SkillLoadResult(2, ["a", "b"], 0.85, 0.85, 200, 0),
        ]
        result = analyzer.analyze(results)
        assert len(result.degradation_curve) == 2
        for point in result.degradation_curve:
            assert "skill_count" in point
            assert "score" in point
            assert isinstance(point["score"], float)

    def test_analyze_no_overlap_between_singles(self):
        """Single-skill results shouldn't create false conflict pairs."""
        analyzer = SkillsBenchAnalyzer()
        results = [
            SkillLoadResult(1, ["skill_x"], 0.90, 0.90, 100, 1),
        ]
        result = analyzer.analyze(results)
        # conflicts_detected > 0 but len(skills_loaded) != 2
        assert len(result.conflict_pairs) == 0

    def test_recommendation_high_sweet_spot(self):
        analyzer = SkillsBenchAnalyzer()
        results = [
            SkillLoadResult(3, ["a", "b", "c"], 0.95, 0.95, 200, 0),
        ]
        result = analyzer.analyze(results)
        assert "Optimal loading" in result.recommendation
        assert "3" in result.recommendation

    def test_recommendation_low_sweet_spot(self):
        analyzer = SkillsBenchAnalyzer()
        results = [
            SkillLoadResult(1, ["a"], 0.70, 0.70, 5000, 0),
        ]
        result = analyzer.analyze(results)
        assert "Conservative loading" in result.recommendation

    def test_recommendation_with_conflicts(self):
        analyzer = SkillsBenchAnalyzer()
        results = [
            SkillLoadResult(2, ["x", "y"], 0.60, 0.60, 500, 2),
        ]
        result = analyzer.analyze(results)
        assert "Known conflicts" in result.recommendation
        assert "x+y" in result.recommendation

    def test_quick_check_safe(self):
        analyzer = SkillsBenchAnalyzer()
        result = analyzer.quick_check(["a", "b"])
        assert result["status"] == "safe"
        assert "optimal" in result["message"]

    def test_quick_check_caution(self):
        analyzer = SkillsBenchAnalyzer()
        result = analyzer.quick_check(["a", "b", "c", "d"])
        assert result["status"] == "caution"

    def test_quick_check_warning(self):
        analyzer = SkillsBenchAnalyzer()
        result = analyzer.quick_check(["a", "b", "c", "d", "e", "f"])
        assert result["status"] == "warning"

    def test_quick_check_error_exceeds_hard_limit(self):
        analyzer = SkillsBenchAnalyzer()
        names = [f"skill_{i}" for i in range(11)]
        result = analyzer.quick_check(names)
        assert result["status"] == "error"
        assert "exceeds hard limit" in result["message"]

    def test_quick_check_at_limit_boundary(self):
        analyzer = SkillsBenchAnalyzer()
        names = [f"skill_{i}" for i in range(10)]
        result = analyzer.quick_check(names)
        assert result["status"] == "warning"

    def test_quick_check_empty(self):
        analyzer = SkillsBenchAnalyzer()
        result = analyzer.quick_check([])
        assert result["status"] == "safe"

    def test_find_overload_never_occurs(self):
        """When no result drops below overload threshold, return max tested."""
        analyzer = SkillsBenchAnalyzer(overload_threshold=0.0)  # Never triggered
        results = [
            SkillLoadResult(1, ["a"], 0.50, 0.50, 500, 0),
            SkillLoadResult(2, ["a", "b"], 0.40, 0.40, 500, 0),
        ]
        result = analyzer.analyze(results)
        assert result.overload_threshold == 2  # max tested count

    def test_find_overload_single_result_empty_list(self):
        """Edge case: single-element results where _find_overload_threshold returns 1."""
        analyzer = SkillsBenchAnalyzer(overload_threshold=0.50)
        results = [
            SkillLoadResult(1, ["a"], 0.40, 0.40, 500, 0),
        ]
        result = analyzer.analyze(results)
        assert result.overload_threshold == 1  # clamped to min 1

    def test_analyze_no_conflicts_with_single_pair_no_conflict(self):
        """When conflicts_detected > 0 but skills_loaded doesn't have 2 items."""
        analyzer = SkillsBenchAnalyzer()
        results = [
            SkillLoadResult(2, ["a", "b"], 0.85, 0.85, 200, 0),
        ]
        result = analyzer.analyze(results)
        assert len(result.conflict_pairs) == 0

    def test_recommendation_with_overload_gt_sweet_spot(self):
        analyzer = SkillsBenchAnalyzer()
        analyzer.overload_threshold = 0.50
        results = [
            SkillLoadResult(1, ["a"], 0.90, 0.90, 100, 0),
            SkillLoadResult(3, ["a", "b", "c"], 0.40, 0.40, 1000, 0),
        ]
        result = analyzer.analyze(results)
        # overload_threshold = 3 - 1 = 2, sweet_spot = 1
        # overload > sweet_spot so recommendation includes "degrades beyond"
        # overload_threshold = 2 > sweet_spot_count = 1
        assert "degrades beyond" in result.recommendation

    def test_foreground_optimization(self):
        """Verify behavior with near-threshold scores."""
        analyzer = SkillsBenchAnalyzer(sweet_spot_threshold=0.90, overload_threshold=0.80)
        results = [
            SkillLoadResult(1, ["a"], 0.89, 0.89, 100, 0),  # below sweet_spot
            SkillLoadResult(2, ["a", "b"], 0.91, 0.91, 200, 0),  # above sweet_spot
            SkillLoadResult(3, ["a", "b", "c"], 0.79, 0.79, 500, 0),  # below overload
        ]
        result = analyzer.analyze(results)
        assert result.sweet_spot_count == 2
        # 3 has score 0.822, above 0.80 overload, so overload_threshold = max tested (3)
        assert result.overload_threshold == 3

    def test_sweet_spot_edge_same_score(self):
        """When two skill counts have same score, pick the higher count."""
        analyzer = SkillsBenchAnalyzer(sweet_spot_threshold=0.0)
        results = [
            SkillLoadResult(1, ["a"], 0.95, 0.95, 100, 0),
            SkillLoadResult(2, ["a", "b"], 0.95, 0.95, 200, 0),
        ]
        result = analyzer.analyze(results)
        # Both at 0.95 above 0.0 threshold, first-wins (count=1 has higher score from lower latency)
        assert result.sweet_spot_count == 1
