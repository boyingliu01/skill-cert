"""Tests for progressive disclosure module (Issue #41)."""

import tempfile
from pathlib import Path

from engine.progressive_disclosure import (
    INDEX_TOKEN_LIMIT,
    TieredCostModel,
    progressive_disclosure_test,
)


def _create_skill_dir(
    skill_name: str = "test-skill",
    description: str = "A test skill",
    skill_md_body: str = "",
    ref_files: list[tuple[str, str]] | None = None,
) -> Path:
    """Create a temporary skill directory for testing."""
    tmp = Path(tempfile.mkdtemp())
    frontmatter = f"---\nname: {skill_name}\ndescription: {description}\n---\n"
    (tmp / "SKILL.md").write_text(frontmatter + skill_md_body, encoding="utf-8")

    if ref_files:
        ref_dir = tmp / "references"
        ref_dir.mkdir(exist_ok=True)
        for fname, content in ref_files:
            fpath = ref_dir / fname
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content, encoding="utf-8")

    return tmp


class TestTieredCostModel:
    """Tests for TieredCostModel."""

    def test_analyze_minimal_skill(self):
        """Minimal skill with only SKILL.md (no references)."""
        skill_dir = _create_skill_dir()
        model = TieredCostModel(skill_dir)
        result = model.analyze()

        assert result.index.token_count > 0
        assert result.index.file_count == 1
        assert result.index.tier_name == "index"
        assert result.load.file_count == 1
        assert result.runtime.file_count == 0
        assert result.runtime.token_count == 0
        assert result.total_tokens > 0

    def test_analyze_with_references(self):
        """Skill with references/ directory should count runtime tokens."""
        ref_files = [
            ("guide.md", "# User Guide\n\nThis is a detailed guide with many words " * 50),
            ("config.yaml", "setting: value\n" * 20),
        ]
        skill_dir = _create_skill_dir(ref_files=ref_files)
        model = TieredCostModel(skill_dir)
        result = model.analyze()

        assert result.index.file_count == 1
        assert result.load.file_count == 1
        assert result.runtime.file_count > 0
        assert result.runtime.token_count > 0
        assert result.total_tokens > 0

    def test_analyze_nonexistent_skill_dir(self):
        """Non-existent skill directory should return zero costs."""
        model = TieredCostModel("/nonexistent/skill/path")
        result = model.analyze()

        assert result.index.token_count == 0
        assert result.load.token_count == 0
        assert result.runtime.token_count == 0
        assert result.index.file_count == 0
        assert result.all_within_budget is True

    def test_index_tier_under_budget(self):
        """Index tier (name + description) should be under budget."""
        skill_dir = _create_skill_dir(
            skill_name="short-name",
            description="Brief description under budget",
        )
        model = TieredCostModel(skill_dir)
        result = model.analyze()

        assert result.index.token_count <= INDEX_TOKEN_LIMIT
        assert not result.index.over_budget
        assert result.total_tokens > 0

    def test_index_tier_over_budget(self):
        """Excessively long name+description should trigger over_budget."""
        very_long_desc = "word " * 500  # ~2000 chars = ~500t
        skill_dir = _create_skill_dir(description=very_long_desc)
        model = TieredCostModel(skill_dir, index_token_limit=50)
        result = model.analyze()

        assert result.index.over_budget
        assert len(result.alerts) > 0

    def test_load_tier_over_budget(self):
        """Large SKILL.md should trigger load tier over_budget."""
        huge_body = "# Big Section\n\n" + ("lots of content " * 5000)
        skill_dir = _create_skill_dir(skill_md_body=huge_body)
        model = TieredCostModel(skill_dir, load_token_limit=100)
        result = model.analyze()

        assert result.load.over_budget
        assert any("Load tier" in a for a in result.alerts)

    def test_roe_ratio_no_runtime(self):
        """ROE ratio should be 0 when no runtime files exist."""
        skill_dir = _create_skill_dir()
        model = TieredCostModel(skill_dir)
        result = model.analyze()

        assert result.roe_ratio == 0.0

    def test_roe_ratio_with_runtime(self):
        """ROE ratio should be > 0 when runtime files exist."""
        ref_files = [("data.md", "data content " * 100)]
        skill_dir = _create_skill_dir(ref_files=ref_files)
        model = TieredCostModel(skill_dir)
        result = model.analyze()

        assert result.roe_ratio > 0

    def test_all_within_budget(self):
        """Small skill should be within budget on all tiers."""
        skill_dir = _create_skill_dir()
        model = TieredCostModel(skill_dir)
        result = model.analyze()

        assert result.all_within_budget

    def test_count_tokens_approximate(self):
        """Token counting should use approximate 4-char method."""
        model = TieredCostModel("/tmp")
        # "hello world" = 11 chars / 4 = 2 tokens
        text = "hello world"
        count = model._count_tokens(text)
        assert count == 2

    def test_analyze_with_nested_references(self):
        """Nested subdirectories in references/ should be counted."""
        ref_files = [
            ("subdir/deep/file_a.md", "content a " * 50),
            ("subdir/file_b.yaml", "config: value\n" * 30),
            ("root_file.txt", "root content " * 20),
        ]
        skill_dir = _create_skill_dir(ref_files=ref_files)
        model = TieredCostModel(skill_dir)
        result = model.analyze()

        assert result.runtime.file_count == 3
        assert len(result.runtime.files) == 3

    def test_references_only_dir(self):
        """Skill with only references/ and no SKILL.md — runtime should be counted."""
        tmp = Path(tempfile.mkdtemp())
        ref_dir = tmp / "references"
        ref_dir.mkdir()
        (ref_dir / "helper.md").write_text("helper content", encoding="utf-8")

        model = TieredCostModel(tmp)
        result = model.analyze()

        assert result.index.token_count == 0
        assert result.load.token_count == 0
        # Runtime is counted independently (references/ directory check is separate)
        assert result.runtime.file_count == 1
        assert result.runtime.token_count > 0


class TestProgressiveDisclosureTest:
    """Tests for progressive_disclosure_test()."""

    def test_skill_with_references_passes(self):
        """Skill with SKILL.md and references/ should pass basic checks."""
        ref_files = [("guide.md", "guide content " * 10)]
        skill_dir = _create_skill_dir(ref_files=ref_files)
        result = progressive_disclosure_test(skill_dir)

        assert result.has_references_dir
        assert result.references_file_count > 0
        assert result.references_token_count > 0
        assert result.tiered_cost_result is not None

    def test_skill_without_references(self):
        """Skill without references/ should not report references."""
        skill_dir = _create_skill_dir()
        result = progressive_disclosure_test(skill_dir)

        assert not result.has_references_dir
        assert result.references_file_count == 0
        assert result.references_token_count == 0

    def test_nonexistent_skill_dir_fails(self):
        """Non-existent directory should return PASS=False with issues."""
        result = progressive_disclosure_test("/nonexistent/skill")
        assert not result.passed
        assert len(result.issues) > 0

    def test_skill_dir_without_skill_md_fails(self):
        """Directory without SKILL.md should return PASS=False."""
        tmp = Path(tempfile.mkdtemp())
        result = progressive_disclosure_test(tmp)
        assert not result.passed
        assert any("SKILL.md" in i for i in result.issues)

    def test_verdict_property(self):
        """Verdict property should return PASS/FAIL string."""
        skill_dir = _create_skill_dir()
        result = progressive_disclosure_test(skill_dir)
        assert result.verdict in ("PASS", "FAIL")

    def test_large_skill_generates_issues(self):
        """Very large SKILL.md should generate load tier issues."""
        huge_body = "# Huge\n\n" + ("x" * 30000)
        skill_dir = _create_skill_dir(skill_md_body=huge_body)
        result = progressive_disclosure_test(skill_dir)

        assert not result.passed
        assert len(result.issues) > 0

    def test_skill_with_deep_references(self):
        """Deeply nested references should be discovered."""
        ref_files = [
            ("a/b/c/deep.md", "deep content " * 30),
            ("a/b/shallow.md", "shallow " * 10),
        ]
        skill_dir = _create_skill_dir(ref_files=ref_files)
        result = progressive_disclosure_test(skill_dir)

        assert result.references_file_count == 2
        assert result.references_token_count > 0


# ─── Test: analyze_structure_quality ────────────────────────────────────────


class TestAnalyzeStructureQuality:
    """Tests for analyze_structure_quality() — SKILL.md structure quality scoring."""

    def test_empty_content_scores_low(self):
        """Empty content scores low but not zero (has 1 line from split)."""
        from engine.progressive_disclosure import analyze_structure_quality

        result = analyze_structure_quality("")
        assert result.skill_md_line_count == 1
        assert not result.skill_md_over_limit
        assert not result.is_router_pattern
        assert not result.has_routing_table

    def test_small_skill_scores_high(self):
        """Small well-structured SKILL.md with routing and modules scores high."""
        from engine.progressive_disclosure import analyze_structure_quality

        content = "\n".join([
            "# My Skill",
            "",
            "## Description",
            "A skill for doing things.",
            "",
            "## Routing Table",
            "| Trigger | Module |",
            "|----------|--------|",
            "| build    | references/build.md |",
            "| test     | references/test.md |",
            "",
            "## Workflow",
            "1. Check trigger",
            "2. Route to module",
        ] + ["padding line " * 10] * 3)  # small file
        result = analyze_structure_quality(content)
        assert result.score >= 20.0
        assert not result.skill_md_over_limit
        assert result.has_routing_table
        assert result.is_router_pattern

    def test_over_limit_small_line_count_deducted(self):
        """SKILL.md over 500 lines should trigger over_limit with deduction."""
        from engine.progressive_disclosure import analyze_structure_quality

        content = "\n".join([
            "# Large Skill",
            "",
            "## Routing Table",
            "delegate to references/module.md"
        ] + ["line " + str(i) for i in range(510)])
        result = analyze_structure_quality(content)
        assert result.skill_md_over_limit
        assert result.skill_md_line_count >= 500
        assert result.score < 100.0
        assert len(result.issues) >= 1

    def test_over_limit_no_module_refs_generates_issue(self):
        """Over-limit SKILL.md without module refs gets extraction suggestion."""
        from engine.progressive_disclosure import analyze_structure_quality

        content = "\n".join([
            "# Large Skill Without Modules",
        ] + ["content line " + str(i) for i in range(520)])
        result = analyze_structure_quality(content)
        assert result.skill_md_over_limit
        # Should have issue about extracting business logic
        assert any("extract" in issue.lower() or "module" in issue.lower()
                   for issue in result.issues)

    def test_has_routing_table_detected(self):
        """Routing table text should be detected."""
        from engine.progressive_disclosure import analyze_structure_quality

        content = "# Skill\n\n## Routing Table\n\n| Use | Module |\n"
        result = analyze_structure_quality(content)
        assert result.has_routing_table

    def test_module_refs_without_routing_generates_issue(self):
        """Module references without routing table should flag an issue."""
        from engine.progressive_disclosure import analyze_structure_quality

        content = "# Skill\n\nSee references/build.md and modules/deploy.md for details.\n"
        result = analyze_structure_quality(content)
        assert not result.has_routing_table
        assert result.is_router_pattern  # has module refs
        assert any("routing table" in issue.lower() for issue in result.issues)

    def test_cjk_content_counts_lines_correctly(self):
        """CJK content should count lines correctly (not token count)."""
        from engine.progressive_disclosure import analyze_structure_quality

        content = "\n".join(["# 技能说明", "", "## 路由表"] + ["中文内容行" * 5] * 10)
        result = analyze_structure_quality(content)
        assert result.skill_md_line_count == 13
        assert not result.skill_md_over_limit

    def test_exactly_500_lines_not_over_limit(self):
        """Exactly 500 lines should NOT be over limit (boundary)."""
        from engine.progressive_disclosure import analyze_structure_quality

        content = "\n".join([
            "# Exactly 500",
            "## Routing Table",
            "delegate to references/module.md",
        ] + ["line " + str(i) for i in range(497)])
        result = analyze_structure_quality(content)
        assert result.skill_md_line_count == 500
        assert not result.skill_md_over_limit
