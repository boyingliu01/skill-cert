"""Tests for CLI helper utilities — coverage focus on helpers.py."""

from unittest.mock import MagicMock

from engine.deadline import Deadline
from skill_cert.cli.helpers import _print_metric, _print_phase, _print_phase_with_deadline


class TestPrintPhase:
    """Tests for _print_phase function."""

    def test_print_phase_basic(self, capsys):
        """_print_phase prints standard phase header."""
        _print_phase(1, "Test Phase")
        captured = capsys.readouterr()

        assert "Phase 1: Test Phase" in captured.out
        assert captured.out.count("=") == 120


class TestPrintPhaseWithDeadline:
    """Tests for _print_phase_with_deadline function."""

    def test_print_phase_with_deadline_none(self, capsys):
        """_print_phase_with_deadline with deadline=None calls _print_phase."""
        _print_phase_with_deadline(1, "Test Phase", deadline=None)
        captured = capsys.readouterr()

        # Should print standard phase header without deadline info
        assert "Phase 1: Test Phase" in captured.out
        assert "Elapsed" not in captured.out
        assert "remaining" not in captured.out

    def test_print_phase_with_deadline_finite(self, capsys, monkeypatch):
        """_print_phase_with_deadline with finite deadline prints elapsed/remaining."""
        # Mock deadline with finite max_total_time
        mock_deadline = MagicMock(spec=Deadline)
        mock_deadline.elapsed = 10.5
        mock_deadline.max_total_time = 60.0
        mock_deadline.remaining = 49.5

        _print_phase_with_deadline(2, "Processing", deadline=mock_deadline)
        captured = capsys.readouterr()

        assert "Phase 2: Processing" in captured.out
        assert "Elapsed: 10s" in captured.out
        assert "60s" in captured.out
        # remaining is rounded: 60 - 10.5 = 49.5 -> 50s
        assert "50s remaining" in captured.out

    def test_print_phase_with_deadline_infinite(self, capsys):
        """_print_phase_with_deadline with infinite deadline prints standard header."""
        # Mock deadline with infinite max_total_time
        mock_deadline = MagicMock(spec=Deadline)
        mock_deadline.elapsed = 5.0
        mock_deadline.max_total_time = float("inf")
        mock_deadline.remaining = float("inf")

        _print_phase_with_deadline(3, "Infinite Phase", deadline=mock_deadline)
        captured = capsys.readouterr()

        # Should print standard header (no elapsed/remaining for infinite)
        assert "Phase 3: Infinite Phase" in captured.out
        assert "Elapsed" not in captured.out
        assert "remaining" not in captured.out

    def test_print_phase_with_deadline_zero_elapsed(self, capsys):
        """_print_phase_with_deadline handles zero elapsed time."""
        mock_deadline = MagicMock(spec=Deadline)
        mock_deadline.elapsed = 0.0
        mock_deadline.max_total_time = 30.0
        mock_deadline.remaining = 30.0

        _print_phase_with_deadline(1, "Start", deadline=mock_deadline)
        captured = capsys.readouterr()

        assert "Elapsed: 0s" in captured.out
        assert "30s" in captured.out
        assert "30s remaining" in captured.out

    def test_print_phase_with_deadline_near_expiry(self, capsys):
        """_print_phase_with_deadline handles near-expiry deadline."""
        mock_deadline = MagicMock(spec=Deadline)
        mock_deadline.elapsed = 29.9
        mock_deadline.max_total_time = 30.0
        mock_deadline.remaining = 0.1

        _print_phase_with_deadline(1, "Last Moment", deadline=mock_deadline)
        captured = capsys.readouterr()

        assert "Elapsed: 30s" in captured.out  # rounded
        assert "30s" in captured.out
        assert "0s remaining" in captured.out  # rounded


class TestPrintMetric:
    """Tests for _print_metric function."""

    def test_print_metric_without_threshold(self, capsys):
        """_print_metric with threshold=None prints value only."""
        _print_metric("Accuracy", 0.85, threshold=None)
        captured = capsys.readouterr()

        assert "Accuracy: 85.0%" in captured.out
        assert "threshold" not in captured.out
        assert "✓" not in captured.out
        assert "✗" not in captured.out

    def test_print_metric_with_passing_threshold(self, capsys):
        """_print_metric with passing threshold shows checkmark."""
        _print_metric("Coverage", 0.95, threshold=0.9)
        captured = capsys.readouterr()

        assert "Coverage: 95.0%" in captured.out
        assert "threshold: 90%" in captured.out
        assert "✓" in captured.out

    def test_print_metric_with_failing_threshold(self, capsys):
        """_print_metric with failing threshold shows X."""
        _print_metric("Precision", 0.75, threshold=0.8)
        captured = capsys.readouterr()

        assert "Precision: 75.0%" in captured.out
        assert "threshold: 80%" in captured.out
        assert "✗" in captured.out

    def test_print_metric_perfect_score(self, capsys):
        """_print_metric handles 100% score."""
        _print_metric("Perfect", 1.0, threshold=None)
        captured = capsys.readouterr()

        assert "Perfect: 100.0%" in captured.out

    def test_print_metric_zero_score(self, capsys):
        """_print_metric handles 0% score."""
        _print_metric("Failed", 0.0, threshold=0.5)
        captured = capsys.readouterr()

        assert "Failed: 0.0%" in captured.out
        assert "✗" in captured.out

    def test_print_metric_with_threshold_zero(self, capsys):
        """_print_metric with threshold=0 always passes."""
        _print_metric("Any Value", 0.01, threshold=0.0)
        captured = capsys.readouterr()

        assert "threshold: 0%" in captured.out
        assert "✓" in captured.out
