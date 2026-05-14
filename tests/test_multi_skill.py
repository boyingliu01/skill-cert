"""Tests for engine/multi_skill.py — multi-skill conflict detection."""

from engine.multi_skill import (
    MultiSkillAnalyzer,
    ConflictType,
    ConflictSeverity,
    SkillConflict,
)


def _make_skill(name, triggers=None, description="", workflow_steps=None,
                anti_patterns=None, output_format=None, content_length=0):
    """Helper to create a minimal skill spec dict."""
    return {
        "name": name,
        "description": description,
        "triggers": triggers or [],
        "workflow_steps": workflow_steps or [],
        "anti_patterns": anti_patterns or [],
        "output_format": output_format or [],
        "content_length": content_length,
    }


# ─── Trigger Conflict Tests ─────────────────────────────────────────────

class TestTriggerConflicts:

    def test_no_conflicts_distinct_triggers(self):
        """Skills with completely different triggers should have no conflicts."""
        skills = [
            _make_skill("skill-a", triggers=["review this", "code review"]),
            _make_skill("skill-b", triggers=["deploy", "ship it"]),
            _make_skill("skill-c", triggers=["debug", "fix bug"]),
        ]
        analyzer = MultiSkillAnalyzer()
        analyzer.inject_multiple_skills(skills)
        conflicts = analyzer.test_trigger_conflicts()
        assert len(conflicts) == 0

    def test_exact_trigger_overlap(self):
        """Two skills sharing the same trigger should conflict."""
        skills = [
            _make_skill("skill-a", triggers=["review this", "code review"]),
            _make_skill("skill-b", triggers=["review this", "deploy"]),
        ]
        analyzer = MultiSkillAnalyzer()
        analyzer.inject_multiple_skills(skills)
        conflicts = analyzer.test_trigger_conflicts()
        assert len(conflicts) == 1
        conflict = conflicts[0]
        assert conflict.conflict_type == ConflictType.TRIGGER_OVERLAP
        assert "review this" in conflict.trigger_word

    def test_partial_trigger_match_substring(self):
        """Trigger substring overlap should be detected as conflict."""
        skills = [
            _make_skill("skill-a", triggers=["review"]),
            _make_skill("skill-b", triggers=["code review"]),
        ]
        analyzer = MultiSkillAnalyzer()
        analyzer.inject_multiple_skills(skills)
        conflicts = analyzer.test_trigger_conflicts()
        assert len(conflicts) == 1

    def test_three_way_trigger_conflict(self):
        """Three skills sharing one trigger should produce pairwise conflicts."""
        skills = [
            _make_skill("skill-a", triggers=["review"]),
            _make_skill("skill-b", triggers=["review"]),
            _make_skill("skill-c", triggers=["review"]),
        ]
        analyzer = MultiSkillAnalyzer()
        analyzer.inject_multiple_skills(skills)
        conflicts = analyzer.test_trigger_conflicts()
        # 3 pairs: A-B, A-C, B-C
        assert len(conflicts) == 3

    def test_case_insensitive_trigger_match(self):
        """'review' should match 'Review' — case insensitive."""
        skills = [
            _make_skill("skill-a", triggers=["review"]),
            _make_skill("skill-b", triggers=["Review"]),
        ]
        analyzer = MultiSkillAnalyzer()
        analyzer.inject_multiple_skills(skills)
        conflicts = analyzer.test_trigger_conflicts()
        assert len(conflicts) == 1

    def test_empty_triggers_no_conflict(self):
        """Skills with no triggers should not produce trigger conflicts."""
        skills = [
            _make_skill("skill-a"),
            _make_skill("skill-b"),
        ]
        analyzer = MultiSkillAnalyzer()
        analyzer.inject_multiple_skills(skills)
        conflicts = analyzer.test_trigger_conflicts()
        assert len(conflicts) == 0

    def test_trigger_conflict_severity_multiple_overlaps(self):
        """Many overlapping triggers between two skills should increase severity."""
        skills = [
            _make_skill("skill-a", triggers=["review", "check", "audit", "inspect"]),
            _make_skill("skill-b", triggers=["review", "check", "deploy"]),
        ]
        analyzer = MultiSkillAnalyzer()
        analyzer.inject_multiple_skills(skills)
        conflicts = analyzer.test_trigger_conflicts()
        assert len(conflicts) >= 1
        # At least one conflict for the shared triggers
        shared = [c for c in conflicts if c.skill_a == "skill-a" and c.skill_b == "skill-b"]
        assert len(shared) >= 1


# ─── Prompt Contamination Tests ─────────────────────────────────────────

class TestPromptContamination:

    def test_no_contamination_disjoint_vocabulary(self):
        """Skills with completely different instruction vocabularies should not contaminate."""
        skills = [
            _make_skill("skill-a", description="Deploy docker containers to kubernetes cluster"),
            _make_skill("skill-b", description="Review Python code for type annotations"),
        ]
        analyzer = MultiSkillAnalyzer()
        analyzer.inject_multiple_skills(skills)
        conflicts = analyzer.test_prompt_contamination()
        assert len(conflicts) == 0

    def test_contamination_shared_workflow_language(self):
        """Skills with same workflow step names may contaminate."""
        skills = [
            _make_skill("skill-a", workflow_steps=[
                {"name": "Parse input", "type": "action"},
                {"name": "Validate", "type": "action"},
                {"name": "Generate output", "type": "action"},
            ]),
            _make_skill("skill-b", workflow_steps=[
                {"name": "Parse input", "type": "action"},
                {"name": "Validate", "type": "action"},
                {"name": "Execute", "type": "action"},
            ]),
        ]
        analyzer = MultiSkillAnalyzer()
        analyzer.inject_multiple_skills(skills)
        conflicts = analyzer.test_prompt_contamination()
        assert len(conflicts) >= 1
        assert conflicts[0].conflict_type == ConflictType.PROMPT_CONTAMINATION

    def test_contamination_same_anti_patterns(self):
        """Skills sharing anti-patterns may interfere with each other."""
        skills = [
            _make_skill("skill-a", anti_patterns=["Skip validation", "Ignore errors"]),
            _make_skill("skill-b", anti_patterns=["Skip validation", "Hardcode values"]),
        ]
        analyzer = MultiSkillAnalyzer()
        analyzer.inject_multiple_skills(skills)
        conflicts = analyzer.test_prompt_contamination()
        assert len(conflicts) >= 1

    def test_contamination_shared_output_format(self):
        """Skills with same output format fields may contaminate context."""
        skills = [
            _make_skill("skill-a", output_format=["report", "summary", "metrics"]),
            _make_skill("skill-b", output_format=["report", "summary", "logs"]),
        ]
        analyzer = MultiSkillAnalyzer()
        analyzer.inject_multiple_skills(skills)
        conflicts = analyzer.test_prompt_contamination()
        assert len(conflicts) >= 1

    def test_contamination_trigger_in_description(self):
        """If skill A's description mentions skill B's trigger, contamination risk."""
        skills = [
            _make_skill("skill-a", description="Use this to review code before you deploy",
                        triggers=["review"]),
            _make_skill("skill-b", triggers=["deploy"]),
        ]
        analyzer = MultiSkillAnalyzer()
        analyzer.inject_multiple_skills(skills)
        conflicts = analyzer.test_prompt_contamination()
        assert len(conflicts) >= 1

    def test_no_contamination_single_skill(self):
        """Single skill cannot contaminate itself."""
        skills = [
            _make_skill("skill-a", description="Deploy to production",
                        triggers=["deploy"]),
        ]
        analyzer = MultiSkillAnalyzer()
        analyzer.inject_multiple_skills(skills)
        conflicts = analyzer.test_prompt_contamination()
        assert len(conflicts) == 0

    def test_contamination_description_keyword_overlap(self):
        """High keyword overlap in descriptions signals contamination risk."""
        skills = [
            _make_skill("skill-a", description="review code check quality verify standards"),
            _make_skill("skill-b", description="review code check style verify patterns"),
        ]
        analyzer = MultiSkillAnalyzer()
        analyzer.inject_multiple_skills(skills)
        conflicts = analyzer.test_prompt_contamination()
        assert len(conflicts) >= 1


# ─── Token Overflow Tests ───────────────────────────────────────────────

class TestTokenOverflow:

    def test_no_overflow_small_skills(self):
        """Small combined skills should not exceed token budget."""
        skills = [
            _make_skill("skill-a", content_length=500),
            _make_skill("skill-b", content_length=500),
        ]
        analyzer = MultiSkillAnalyzer()
        analyzer.inject_multiple_skills(skills)
        conflicts = analyzer.test_token_overflow()
        assert len(conflicts) == 0

    def test_overflow_large_combined_skills(self):
        """Combined content_length exceeding budget should produce overflow conflict."""
        skills = [
            _make_skill("skill-a", content_length=50000),
            _make_skill("skill-b", content_length=50000),
            _make_skill("skill-c", content_length=50000),
        ]
        analyzer = MultiSkillAnalyzer()
        analyzer.inject_multiple_skills(skills)
        conflicts = analyzer.test_token_overflow()
        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == ConflictType.TOKEN_OVERFLOW

    def test_overflow_custom_budget(self):
        """Custom budget should be respected."""
        skills = [
            _make_skill("skill-a", content_length=10000),
            _make_skill("skill-b", content_length=10000),
        ]
        analyzer = MultiSkillAnalyzer()
        analyzer.inject_multiple_skills(skills)
        conflicts = analyzer.test_token_overflow(token_budget=15000)
        assert len(conflicts) == 1

    def test_no_overflow_at_budget_boundary(self):
        """Combined content exactly at budget should NOT overflow."""
        boundary_skills = [
            _make_skill("skill-a", content_length=50000),
            _make_skill("skill-b", content_length=50000),
        ]
        analyzer = MultiSkillAnalyzer()
        analyzer.inject_multiple_skills(boundary_skills)
        conflicts = analyzer.test_token_overflow(token_budget=100000)
        assert len(conflicts) == 0

    def test_overflow_severity_scales_with_excess(self):
        """Larger excess over budget should produce higher severity."""
        skills = [
            _make_skill("skill-a", content_length=80000),
            _make_skill("skill-b", content_length=80000),
        ]
        analyzer_low = MultiSkillAnalyzer()
        analyzer_low.inject_multiple_skills(skills)
        conflicts_low = analyzer_low.test_token_overflow(token_budget=120000)

        skills_high = [
            _make_skill("skill-a", content_length=200000),
            _make_skill("skill-b", content_length=200000),
        ]
        analyzer_high = MultiSkillAnalyzer()
        analyzer_high.inject_multiple_skills(skills_high)
        conflicts_high = analyzer_high.test_token_overflow(token_budget=120000)

        assert len(conflicts_low) == 1
        assert len(conflicts_high) == 1
        severity_order = {"none": 0, "low": 1, "moderate": 2, "high": 3}
        assert severity_order[conflicts_high[0].severity.value] >= severity_order[conflicts_low[0].severity.value]

    def test_token_overflow_single_skill(self):
        """Single skill below budget should not overflow."""
        skills = [
            _make_skill("skill-a", content_length=30000),
        ]
        analyzer = MultiSkillAnalyzer()
        analyzer.inject_multiple_skills(skills)
        conflicts = analyzer.test_token_overflow()
        assert len(conflicts) == 0


# ─── Full Analysis Tests ────────────────────────────────────────────────

class TestFullAnalysis:

    def test_full_analysis_no_conflicts(self):
        """Fully disjoint skills produce zero conflicts."""
        skills = [
            _make_skill("skill-a", triggers=["review"], description="Code review skill",
                        content_length=100),
            _make_skill("skill-b", triggers=["deploy"], description="Deploy to kubernetes",
                        content_length=100),
        ]
        analyzer = MultiSkillAnalyzer()
        analyzer.inject_multiple_skills(skills)
        report = analyzer.analyze()
        assert len(report["conflicts"]) == 0
        assert report["overall_risk"] == "none"

    def test_full_analysis_mixed_conflicts(self):
        """Skills with both trigger and token issues produce mixed conflicts."""
        skills = [
            _make_skill("skill-a", triggers=["review"], content_length=60000),
            _make_skill("skill-b", triggers=["review"], content_length=60000),
        ]
        analyzer = MultiSkillAnalyzer()
        analyzer.inject_multiple_skills(skills)
        report = analyzer.analyze()
        assert len(report["conflicts"]) >= 2
        types = {c.conflict_type for c in report["conflicts"]}
        assert ConflictType.TRIGGER_OVERLAP in types
        assert ConflictType.TOKEN_OVERFLOW in types

    def test_empty_skill_list(self):
        """Empty input should return empty analysis."""
        analyzer = MultiSkillAnalyzer()
        report = analyzer.analyze()
        assert len(report["conflicts"]) == 0
        assert report["overall_risk"] == "none"

    def test_report_summary_includes_all_conflict_types(self):
        """Report summary should enumerate each conflict type found."""
        skills = [
            _make_skill("skill-a", triggers=["review"], content_length=60000),
            _make_skill("skill-b", triggers=["review"], content_length=60000),
        ]
        analyzer = MultiSkillAnalyzer()
        analyzer.inject_multiple_skills(skills)
        report = analyzer.analyze()
        summary = report.get("summary", "")
        assert summary != ""
        assert "trigger" in summary.lower() or "conflict" in summary.lower()


# ─── SkillConflict Model Tests ──────────────────────────────────────────

class TestSkillConflictModel:

    def test_conflict_string_representation(self):
        """SkillConflict should have readable string repr."""
        conflict = SkillConflict(
            conflict_type=ConflictType.TRIGGER_OVERLAP,
            severity=ConflictSeverity.HIGH,
            skill_a="skill-a",
            skill_b="skill-b",
            trigger_word="review",
            description="Both skills trigger on 'review'",
        )
        text = str(conflict)
        assert "skill-a" in text
        assert "skill-b" in text
        assert "trigger_overlap" in text or "TRIGGER_OVERLAP" in text

    def test_conflict_to_dict(self):
        """SkillConflict should serialize to dict."""
        conflict = SkillConflict(
            conflict_type=ConflictType.PROMPT_CONTAMINATION,
            severity=ConflictSeverity.MODERATE,
            skill_a="a",
            skill_b="b",
            description="Shared workflow",
        )
        d = conflict.to_dict()
        assert d["conflict_type"] == "prompt_contamination"
        assert d["severity"] == "moderate"
        assert d["skill_a"] == "a"
        assert d["skill_b"] == "b"


# ─── Edge Cases ─────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_duplicate_skill_names(self):
        """Two skill dicts with same name should still be analyzed."""
        skills = [
            _make_skill("same-name", triggers=["review"]),
            _make_skill("same-name", triggers=["review"]),
        ]
        analyzer = MultiSkillAnalyzer()
        analyzer.inject_multiple_skills(skills)
        conflicts = analyzer.test_trigger_conflicts()
        assert len(conflicts) == 1

    def test_single_skill_no_conflicts_possible(self):
        """One skill cannot conflict with anything."""
        skills = [
            _make_skill("solo", triggers=["review"], content_length=100000),
        ]
        analyzer = MultiSkillAnalyzer()
        analyzer.inject_multiple_skills(skills)
        conflicts = analyzer.test_trigger_conflicts()
        assert len(conflicts) == 0
        token_conflicts = analyzer.test_token_overflow()
        assert len(token_conflicts) == 0

    def test_many_skills_stress(self):
        """10 skills with shared triggers should produce many conflicts."""
        skills = [
            _make_skill(f"skill-{i}", triggers=["review", "check"])
            for i in range(10)
        ]
        analyzer = MultiSkillAnalyzer()
        analyzer.inject_multiple_skills(skills)
        conflicts = analyzer.test_trigger_conflicts()
        # C(10,2) = 45 pairs, each with 2 shared triggers
        assert len(conflicts) > 10

    def test_overall_risk_aggregation(self):
        """Overall risk should be the maximum severity across all conflicts."""
        skills = [
            _make_skill("skill-a", triggers=["a"]),
            _make_skill("skill-b", triggers=["a", "b", "c", "d", "e"]),
        ]
        analyzer = MultiSkillAnalyzer()
        analyzer.inject_multiple_skills(skills)
        report = analyzer.analyze()
        severity_order = {"none": 0, "low": 1, "moderate": 2, "high": 3}
        assert severity_order[report["overall_risk"]] >= severity_order["low"]


class TestReporterIntegration:

    def test_reporter_multi_skill_section(self):
        from engine.reporter import Reporter

        multi_report = {
            "skill_count": 3,
            "overall_risk": "moderate",
            "summary": "Trigger conflicts detected on 2 overlaps: 'review', 'deploy'",
            "conflicts": [],
            "trigger_conflicts": 2,
            "prompt_contamination_conflicts": 0,
            "token_overflow_conflicts": 0,
        }

        metrics = {
            "overall_score": 0.8,
            "l1_trigger_accuracy": 0.9,
            "l2_with_without_skill_delta": 0.3,
            "l3_step_adherence": 0.85,
            "l4_execution_stability": 0.95,
            "metrics_breakdown": {
                "l1_details": {"total_trigger_evals": 5, "passed_trigger_evals": 5, "trigger_accuracy": 1.0},
                "l2_details": {"with_skill_avg_pass_rate": 0.9, "without_skill_avg_pass_rate": 0.6, "improvement_percentage": 30.0},
                "l3_details": {"step_coverage_ratio": 0.85},
                "l4_details": {"execution_stability": 0.95, "stdev_deterministic_pass_rate": 0.05},
            },
        }

        reporter = Reporter()
        md, js = reporter.generate_report_with_multi_skill(
            metrics=metrics,
            drift={"drift_detected": False, "highest_severity": "none"},
            config={"total_evaluations": 5},
            multi_skill_report=multi_report,
        )

        assert "Multi-Skill Analysis" in md
        assert "3" in md
        assert "moderate" in md.lower()
        assert js["multi_skill_analysis"]["skill_count"] == 3
        assert js["multi_skill_analysis"]["overall_risk"] == "moderate"

    def test_reporter_multi_skill_with_conflicts(self):
        from engine.reporter import Reporter
        from engine.multi_skill import SkillConflict, ConflictType, ConflictSeverity

        reporter = Reporter()
        conflict = SkillConflict(
            conflict_type=ConflictType.TRIGGER_OVERLAP,
            severity=ConflictSeverity.HIGH,
            skill_a="skill-a",
            skill_b="skill-b",
            trigger_word="review",
            description="Both trigger on review",
        )

        multi_report = {
            "skill_count": 2,
            "overall_risk": "high",
            "summary": "Trigger conflicts",
            "conflicts": [conflict],
            "trigger_conflicts": 1,
            "prompt_contamination_conflicts": 0,
            "token_overflow_conflicts": 0,
        }

        metrics = {
            "overall_score": 0.5,
            "l1_trigger_accuracy": 0.7,
            "l2_with_without_skill_delta": 0.1,
            "l3_step_adherence": 0.6,
            "l4_execution_stability": 0.8,
            "metrics_breakdown": {
                "l1_details": {"total_trigger_evals": 5, "passed_trigger_evals": 3, "trigger_accuracy": 0.6},
                "l2_details": {"with_skill_avg_pass_rate": 0.7, "without_skill_avg_pass_rate": 0.6, "improvement_percentage": 10.0},
                "l3_details": {"step_coverage_ratio": 0.6},
                "l4_details": {"execution_stability": 0.8, "stdev_deterministic_pass_rate": 0.08},
            },
        }

        md, js = reporter.generate_report_with_multi_skill(
            metrics=metrics,
            drift={"drift_detected": False},
            config={},
            multi_skill_report=multi_report,
        )

        assert "trigger_overlap" in md
        assert "skill-a" in md
        assert "skill-b" in md
        assert len(js["multi_skill_analysis"]["conflicts"]) == 1
