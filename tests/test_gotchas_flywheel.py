"""Tests for engine/gotchas_flywheel.py — GotchasFlywheel (Issue #42)."""

import tempfile

from engine.gotchas_flywheel import GotchasFlywheel


class TestGotchasFlywheel:
    """Test the GotchasFlywheel class."""

    def test_extract_from_failure_returns_none_for_pass(self):
        flywheel = GotchasFlywheel()
        result = {"final_passed": True, "eval_name": "test"}
        assert flywheel.extract_from_failure(result) is None

    def test_extract_from_failure_returns_gotcha_for_fail(self):
        flywheel = GotchasFlywheel()
        result = {
            "final_passed": False,
            "eval_name": "test-fail",
            "eval_id": "e1",
            "category": "trigger",
            "negative_case": False,
            "pass_rate": 0.0,
            "assertion_results": [],
        }
        gotcha = flywheel.extract_from_failure(result)
        assert gotcha is not None
        assert "test-fail" in gotcha
        assert "should_trigger" in gotcha

    def test_extract_from_failure_with_assertion_failures(self):
        flywheel = GotchasFlywheel()
        result = {
            "final_passed": False,
            "eval_name": "assert-test",
            "eval_id": "e2",
            "category": "boundary",
            "negative_case": True,
            "pass_rate": 0.25,
            "assertion_results": [
                {
                    "passed": False,
                    "assertion_type": "contains",
                    "expected": "foo",
                    "description": "check foo",
                },
                {
                    "passed": True,
                    "assertion_type": "regex",
                    "expected": "bar",
                    "description": "check bar",
                },
            ],
        }
        gotcha = flywheel.extract_from_failure(result)
        assert gotcha is not None
        assert "assert-test" in gotcha
        assert "should_NOT_trigger" in gotcha
        assert "contains" in gotcha

    def test_append_creates_new_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            flywheel = GotchasFlywheel(gotchas_dir=tmpdir)
            flywheel.append("Test gotcha content")
            path = flywheel.gotchas_path
            assert path.exists()
            content = path.read_text()
            assert "Test gotcha content" in content
            assert "Gotchas Flywheel" in content

    def test_append_appends_to_existing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            flywheel = GotchasFlywheel(gotchas_dir=tmpdir)
            flywheel.append("First gotcha")
            flywheel.append("Second gotcha")
            content = flywheel.gotchas_path.read_text()
            assert "First gotcha" in content
            assert "Second gotcha" in content

    def test_load_returns_empty_list_when_no_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            flywheel = GotchasFlywheel(gotchas_dir=tmpdir)
            assert flywheel.load() == []

    def test_load_returns_gotchas(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            flywheel = GotchasFlywheel(gotchas_dir=tmpdir)
            flywheel.append("Gotcha one")
            flywheel.append("Gotcha two")
            gotchas = flywheel.load()
            assert len(gotchas) == 2

    def test_process_failures(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            flywheel = GotchasFlywheel(gotchas_dir=tmpdir)
            graded_results = [
                {
                    "final_passed": False,
                    "eval_name": "fail1",
                    "eval_id": "e1",
                    "category": "trigger",
                    "negative_case": False,
                    "pass_rate": 0.0,
                    "assertion_results": [],
                },
                {
                    "final_passed": True,
                    "eval_name": "pass1",
                    "eval_id": "e2",
                    "category": "trigger",
                    "negative_case": False,
                    "pass_rate": 1.0,
                    "assertion_results": [],
                },
                {
                    "final_passed": False,
                    "eval_name": "fail2",
                    "eval_id": "e3",
                    "category": "boundary",
                    "negative_case": True,
                    "pass_rate": 0.0,
                    "assertion_results": [],
                },
            ]
            count = flywheel.process_failures(graded_results)
            assert count == 2
            gotchas = flywheel.load()
            assert len(gotchas) == 2

    def test_process_failures_all_pass(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            flywheel = GotchasFlywheel(gotchas_dir=tmpdir)
            graded_results = [
                {
                    "final_passed": True,
                    "eval_name": "p1",
                    "eval_id": "e1",
                    "category": "trigger",
                    "negative_case": False,
                    "pass_rate": 1.0,
                    "assertion_results": [],
                },
            ]
            count = flywheel.process_failures(graded_results)
            assert count == 0

    def test_default_path(self):
        flywheel = GotchasFlywheel()
        assert str(flywheel.gotchas_path).endswith("references/gotchas.md")
