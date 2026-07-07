"""Tests for engine/hooks_detector.py — SKILL.md hooks/guardrail detection."""

from engine.hooks_detector import HooksResult, detect_hooks


class TestDetectHooks:
    """Test detect_hooks() — SKILL.md hooks/guardrail analysis."""

    def test_no_hooks_detected(self):
        """SKILL.md with no hook references scores 0."""
        content = "# My Skill\nA simple skill without any hooks.\n"
        result = detect_hooks(content)
        assert isinstance(result, HooksResult)
        assert result.score == 0.0
        assert result.safety_hooks == []
        assert result.operational_hooks == []
        assert not result.passed

    def test_safety_hooks_detected(self):
        """SKILL.md with safety hooks (/careful, /freeze) detects them."""
        content = (
            "---\nname: test\n---\n"
            "Use /careful before destructive commands.\n"
            "Use /freeze to restrict file edits.\n"
        )
        result = detect_hooks(content)
        assert "/careful" in result.safety_hooks
        assert "/freeze" in result.safety_hooks
        assert result.score >= 40.0

    def test_operational_hooks_detected(self):
        """SKILL.md with operational hooks tracks them separately."""
        content = (
            "---\nname: test\n---\n"
            "Run /context-save before ending.\n"
            "Use /context-restore to resume.\n"
        )
        result = detect_hooks(content)
        assert "/context-save" in result.operational_hooks
        assert "/context-restore" in result.operational_hooks

    def test_full_hooks_coverage(self):
        """SKILL.md with all hook categories scores high."""
        content = (
            "---\nname: test\n---\n"
            "/careful\n/freeze\n/guard\n"
            "/context-save\n/context-restore\n"
        )
        result = detect_hooks(content)
        assert result.score >= 80.0
        assert result.passed

    def test_empty_content_scores_zero(self):
        """Empty content returns score 0 with no hooks."""
        result = detect_hooks("")
        assert result.score == 0.0
        assert result.issues

    def test_same_hook_not_duplicated(self):
        """Repeated hook mentions are deduplicated."""
        content = "Use /careful here.\nAlso use /careful there.\n"
        result = detect_hooks(content)
        assert len(result.safety_hooks) == 1
        assert result.safety_hooks == ["/careful"]
