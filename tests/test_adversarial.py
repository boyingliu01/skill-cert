"""Tests for engine/adversarial.py — adversarial test generation PoC."""

from engine.adversarial import (
    AdversarialCase,
    AdversarialGenerator,
    AdversarialReport,
    Weakness,
    WeaknessAnalyzer,
    evaluate_poc,
    generate_adversarial_cases,
)

# ─── Fixtures ───────────────────────────────────────────────────────────────


EMPTY_SPEC: dict = {
    "name": "empty-skill",
    "description": "",
    "triggers": [],
    "workflow_steps": [],
    "anti_patterns": [],
    "output_format": [],
    "examples": [],
}


FULL_SPEC: dict = {
    "name": "full-skill",
    "description": (
        "A complete skill with detailed description that covers all the required"
        " aspects for proper operation and clear usage guidelines."
    ),
    "triggers": ["run test", "verify skill", "check quality"],
    "workflow_steps": [
        {"name": "Parse input", "type": "unknown", "critical": False},
        {"name": "Validate fields", "type": "unknown", "critical": True},
        {"name": "Execute action", "type": "unknown", "critical": False},
        {"name": "Return result", "type": "unknown", "critical": False},
    ],
    "anti_patterns": ["Skipping validation", "Ignoring errors"],
    "output_format": ["status", "data", "error"],
    "examples": ["Basic usage"],
}


PARTIAL_SPEC: dict = {
    "name": "partial-skill",
    "description": "Short desc",
    "triggers": ["only one trigger"],
    "workflow_steps": [],
    "anti_patterns": [],
    "output_format": [],
    "examples": [],
}


# ─── Test: Weakness Model ──────────────────────────────────────────────────


class TestWeaknessModel:
    def test_weakness_creation(self):
        w = Weakness(
            category="ambiguous_trigger",
            description="No triggers defined",
            severity="high",
            location="triggers",
        )
        assert w.category == "ambiguous_trigger"
        assert w.severity == "high"
        assert w.location == "triggers"

    def test_weakness_categories(self):
        valid = ["ambiguous_trigger", "unclear_workflow", "missing_edge_case", "vague_output"]
        for cat in valid:
            w = Weakness(category=cat, description="test", severity="low", location="x")
            assert w.category == cat

    def test_weakness_severities(self):
        valid = ["low", "medium", "high"]
        for sev in valid:
            w = Weakness(
                category="ambiguous_trigger",
                description="test",
                severity=sev,
                location="x",
            )
            assert w.severity == sev


# ─── Test: AdversarialCase Model ───────────────────────────────────────────


class TestAdversarialCaseModel:
    def test_case_defaults(self):
        c = AdversarialCase(
            id=1,
            name="test-case",
            category="boundary",
            prompt="test prompt",
            target_weakness="weak point",
        )
        assert c.expected_triggers is True
        assert c.assertions == []

    def test_case_with_assertions(self):
        c = AdversarialCase(
            id=2,
            name="test-case-2",
            category="adversarial",
            prompt="test",
            target_weakness="weak",
            expected_triggers=False,
            assertions=[{"type": "not_contains", "value": "skill activated", "weight": 2}],
        )
        assert c.expected_triggers is False
        assert len(c.assertions) == 1
        assert c.assertions[0]["type"] == "not_contains"


# ─── Test: AdversarialReport Model ─────────────────────────────────────────


class TestAdversarialReport:
    def test_report_creation(self):
        r = AdversarialReport(
            weaknesses_found=3,
            adversarial_cases_generated=3,
            generation_quality=0.8,
            extra_cost_pct=0.0,
            reproducible=True,
            marginal_value=1.6,
            recommendation="PROCEED",
        )
        assert r.weaknesses_found == 3
        assert r.adversarial_cases_generated == 3
        assert r.generation_quality == 0.8
        assert r.recommendation == "PROCEED"


# ─── Test: WeaknessAnalyzer ────────────────────────────────────────────────


class TestWeaknessAnalyzer:
    def test_empty_skill_finds_weaknesses(self):
        analyzer = WeaknessAnalyzer()
        weaknesses = analyzer.analyze(EMPTY_SPEC)
        # Empty spec should find: ambiguous_trigger (no triggers), unclear_workflow (no steps),
        # missing_edge_case (no anti-patterns), vague_output (no output_format)
        # Description is empty - the analyzer only checks description if non-empty
        # So expects: 4 weaknesses (triggers, workflow_steps, anti_patterns, output_format)
        assert len(weaknesses) >= 3
        categories = {w.category for w in weaknesses}
        assert "ambiguous_trigger" in categories
        assert "unclear_workflow" in categories
        assert "missing_edge_case" in categories

    def test_full_skill_finds_few_weaknesses(self):
        analyzer = WeaknessAnalyzer()
        weaknesses = analyzer.analyze(FULL_SPEC)
        # Full spec has triggers (3), steps (4), anti-patterns (2), output_format (3)
        # Description is 19 words which is < 20, so vague_output on description
        # So expects: 1 weakness (description too short)
        assert len(weaknesses) <= 2

    def test_weakness_categories_are_correct(self):
        analyzer = WeaknessAnalyzer()
        spec = {
            "name": "cat-test",
            "description": "",
            "triggers": [],
            "workflow_steps": [],
            "anti_patterns": [],
            "output_format": [],
        }
        weaknesses = analyzer.analyze(spec)
        cat_map = {w.location: w.category for w in weaknesses}
        assert cat_map["triggers"] == "ambiguous_trigger"
        assert cat_map["workflow_steps"] == "unclear_workflow"
        assert cat_map["anti_patterns"] == "missing_edge_case"
        assert cat_map["output_format"] == "vague_output"

    def test_single_trigger_detected(self):
        analyzer = WeaknessAnalyzer()
        spec = {
            "name": "single-trigger",
            "description": (
                "A longer description that exceeds twenty words by quite a bit"
                " to check the counter."
            ),
            "triggers": ["only one"],
            "workflow_steps": [
                {"name": "Step 1", "type": "unknown", "critical": False},
                {"name": "Step 2", "type": "unknown", "critical": False},
                {"name": "Step 3", "type": "unknown", "critical": False},
            ],
            "anti_patterns": ["Some pattern"],
            "output_format": ["output"],
        }
        weaknesses = analyzer.analyze(spec)
        trigger_weaknesses = [w for w in weaknesses if w.location == "triggers"]
        assert len(trigger_weaknesses) == 1
        assert trigger_weaknesses[0].category == "ambiguous_trigger"
        assert trigger_weaknesses[0].severity == "medium"
        assert "Only 1 trigger" in trigger_weaknesses[0].description

    def test_short_description_detected(self):
        analyzer = WeaknessAnalyzer()
        spec = {
            "name": "short-desc",
            "description": "Too short",
            "triggers": ["t1", "t2"],
            "workflow_steps": [
                {"name": "S1", "type": "unknown", "critical": False},
                {"name": "S2", "type": "unknown", "critical": False},
                {"name": "S3", "type": "unknown", "critical": False},
            ],
            "anti_patterns": ["ap"],
            "output_format": ["of"],
        }
        weaknesses = analyzer.analyze(spec)
        desc_weaknesses = [w for w in weaknesses if w.location == "description"]
        assert len(desc_weaknesses) == 1
        assert desc_weaknesses[0].category == "vague_output"


# ─── Test: AdversarialGenerator ────────────────────────────────────────────


class TestAdversarialGenerator:
    def test_each_weakness_produces_a_case(self):
        generator = AdversarialGenerator()
        weaknesses = [
            Weakness(
                category="ambiguous_trigger",
                description="no triggers",
                severity="high",
                location="triggers",
            ),
            Weakness(
                category="unclear_workflow",
                description="no steps",
                severity="high",
                location="workflow_steps",
            ),
            Weakness(
                category="missing_edge_case",
                description="no anti-patterns",
                severity="medium",
                location="anti_patterns",
            ),
            Weakness(
                category="vague_output",
                description="no output format",
                severity="medium",
                location="output_format",
            ),
        ]
        cases, metrics = generator.generate(weaknesses)
        assert len(cases) == 4
        case_cats = {c.category for c in cases}
        assert "adversarial" in case_cats
        assert "boundary" in case_cats
        assert "failure" in case_cats

    def test_each_case_has_assertions(self):
        generator = AdversarialGenerator()
        weaknesses = [
            Weakness(
                category="ambiguous_trigger",
                description="test",
                severity="high",
                location="triggers",
            ),
            Weakness(
                category="unclear_workflow",
                description="test",
                severity="high",
                location="steps",
            ),
            Weakness(
                category="missing_edge_case",
                description="test",
                severity="medium",
                location="anti_patterns",
            ),
            Weakness(
                category="vague_output",
                description="test",
                severity="medium",
                location="output_format",
            ),
        ]
        cases, _ = generator.generate(weaknesses)
        for case in cases:
            assert len(case.assertions) >= 1, f"Case {case.name} has no assertions"

    def test_metrics_are_positive(self):
        generator = AdversarialGenerator()
        weaknesses = [
            Weakness(
                category="ambiguous_trigger",
                description="test",
                severity="high",
                location="triggers",
            ),
        ]
        _, metrics = generator.generate(weaknesses)
        assert metrics["generation_quality"] >= 0.0
        assert metrics["extra_cost_pct"] == 0.0
        assert metrics["reproducible"] is True
        assert metrics["marginal_value"] >= 1.5


# ─── Test: evaluate_poc ────────────────────────────────────────────────────


class TestEvaluatePoc:
    def test_full_skill_returns_proceed(self):
        report = evaluate_poc(FULL_SPEC)
        assert isinstance(report, AdversarialReport)
        assert report.weaknesses_found >= 0
        assert report.adversarial_cases_generated >= 0
        assert report.recommendation == "PROCEED"

    def test_empty_skill_returns_report(self):
        report = evaluate_poc(EMPTY_SPEC)
        assert isinstance(report, AdversarialReport)
        assert report.weaknesses_found >= 1
        assert report.adversarial_cases_generated >= 1

    def test_partial_skill_returns_report(self):
        report = evaluate_poc(PARTIAL_SPEC)
        assert isinstance(report, AdversarialReport)
        assert report.weaknesses_found >= 1

    def test_reproducibility(self):
        """Same spec twice should produce identical results."""
        report1 = evaluate_poc(FULL_SPEC)
        report2 = evaluate_poc(FULL_SPEC)
        assert report1.weaknesses_found == report2.weaknesses_found
        assert report1.adversarial_cases_generated == report2.adversarial_cases_generated
        assert report1.generation_quality == report2.generation_quality
        assert report1.extra_cost_pct == report2.extra_cost_pct
        assert report1.reproducible == report2.reproducible
        assert report1.marginal_value == report2.marginal_value
        assert report1.recommendation == report2.recommendation

    def test_reproducibility_weaknesses_identical(self):
        """Same spec should produce the exact same weaknesses list."""
        analyzer = WeaknessAnalyzer()
        w1 = analyzer.analyze(FULL_SPEC)
        w2 = analyzer.analyze(FULL_SPEC)
        assert len(w1) == len(w2)
        for a, b in zip(w1, w2):
            assert a.category == b.category
            assert a.description == b.description
            assert a.severity == b.severity
            assert a.location == b.location

    def test_reproducibility_cases_identical(self):
        """Same weaknesses should produce the same adversarial cases."""
        generator = AdversarialGenerator()
        weaknesses = [
            Weakness(
                category="ambiguous_trigger",
                description="test",
                severity="high",
                location="triggers",
            ),
            Weakness(
                category="unclear_workflow",
                description="test",
                severity="high",
                location="steps",
            ),
        ]
        cases1, _ = generator.generate(weaknesses)
        cases2, _ = generator.generate(weaknesses)
        assert len(cases1) == len(cases2)
        for a, b in zip(cases1, cases2):
            assert a.id == b.id
            assert a.name == b.name
            assert a.category == b.category
            assert a.prompt == b.prompt
            assert a.assertions == b.assertions


# ─── Test: generate_adversarial_cases ──────────────────────────────────────


class TestGenerateAdversarialCases:
    def test_generate_adversarial_cases_delegates_dispatcher(self):
        """generate_adversarial_cases accepts dispatcher and returns list."""
        from engine.integrations import GiskardSecurityIntegration, IntegrationDispatcher

        dispatcher = IntegrationDispatcher()
        dispatcher.register(GiskardSecurityIntegration())

        weak = Weakness(
            category="ambiguous_trigger",
            description="Trigger is too generic",
            severity="medium",
            location="SKILL.md trigger section",
        )

        cases = generate_adversarial_cases(
            weaknesses=[weak],
            skill_name="test-skill",
            dispatcher=dispatcher,
        )
        assert isinstance(cases, list)

    def test_generate_adversarial_cases_no_dispatcher_returns_empty(self):
        """When dispatcher is None, returns empty list without error."""
        weak = Weakness(
            category="ambiguous_trigger",
            description="Trigger is too generic",
            severity="medium",
            location="SKILL.md trigger section",
        )

        cases = generate_adversarial_cases(weaknesses=[weak], skill_name="test")
        assert cases == []
