"""Tests for L7 cost efficiency metrics."""

import pytest
from engine.metrics import MetricsCalculator


class TestL7CostEfficiency:

    def test_l7_no_cost_data_returns_none(self):
        """When no cost data exists, L7 should return None."""
        calc = MetricsCalculator()
        results = [
            {"final_passed": True, "pass_rate": 0.8},
            {"final_passed": False, "pass_rate": 0.3},
        ]
        l7 = calc._calculate_l7_cost_efficiency(results)
        assert l7 is None

    def test_l7_basic_calculation(self):
        """L7 should calculate cost metrics when cost data exists."""
        calc = MetricsCalculator()
        results = [
            {
                "final_passed": True,
                "pass_rate": 0.9,
                "skill_used": True,
                "cost": 0.05,
                "tokens_used": 1000,
            },
            {
                "final_passed": True,
                "pass_rate": 0.8,
                "skill_used": True,
                "cost": 0.04,
                "tokens_used": 800,
            },
            {
                "final_passed": False,
                "pass_rate": 0.5,
                "skill_used": False,
                "cost": 0.03,
                "tokens_used": 600,
            },
            {
                "final_passed": True,
                "pass_rate": 0.7,
                "skill_used": False,
                "cost": 0.02,
                "tokens_used": 400,
            },
        ]
        l7 = calc._calculate_l7_cost_efficiency(results)
        assert l7 is not None
        assert "cost_per_eval" in l7
        assert "total_cost" in l7
        assert "cost_with_skill" in l7
        assert "cost_without_skill" in l7
        assert "cost_delta_pct" in l7
        assert "cost_efficiency" in l7

    def test_l7_cost_per_eval(self):
        """Cost per eval should be average of all eval costs."""
        calc = MetricsCalculator()
        results = [
            {"skill_used": True, "cost": 0.06},
            {"skill_used": True, "cost": 0.04},
            {"skill_used": False, "cost": 0.03},
            {"skill_used": False, "cost": 0.01},
        ]
        l7 = calc._calculate_l7_cost_efficiency(results)
        assert l7 is not None
        # (0.06 + 0.04 + 0.03 + 0.01) / 4 = 0.035
        assert l7["cost_per_eval"] == pytest.approx(0.035, rel=0.001)

    def test_l7_total_cost(self):
        """Total cost should sum all eval costs."""
        calc = MetricsCalculator()
        results = [
            {"skill_used": True, "cost": 0.10},
            {"skill_used": True, "cost": 0.15},
            {"skill_used": False, "cost": 0.05},
            {"skill_used": False, "cost": 0.08},
        ]
        l7 = calc._calculate_l7_cost_efficiency(results)
        assert l7 is not None
        assert l7["total_cost"] == pytest.approx(0.38, rel=0.001)

    def test_l7_cost_delta_pct(self):
        """Cost delta should compare with-skill vs without-skill avg cost."""
        calc = MetricsCalculator()
        results = [
            {"skill_used": True, "cost": 0.06},
            {"skill_used": True, "cost": 0.04},
            {"skill_used": False, "cost": 0.02},
            {"skill_used": False, "cost": 0.02},
        ]
        l7 = calc._calculate_l7_cost_efficiency(results)
        assert l7 is not None
        # with_avg = 0.05, without_avg = 0.02
        # (0.05 - 0.02) / 0.02 = 1.5 = 150%
        assert l7["cost_delta_pct"] == pytest.approx(1.5, rel=0.001)

    def test_l7_cost_efficiency(self):
        """Cost efficiency = L2_delta / cost_delta_pct."""
        calc = MetricsCalculator()
        results = [
            {"skill_used": True, "cost": 0.06, "pass_rate": 0.9},
            {"skill_used": True, "cost": 0.04, "pass_rate": 0.95},
            {"skill_used": False, "cost": 0.02, "pass_rate": 0.5},
            {"skill_used": False, "cost": 0.02, "pass_rate": 0.55},
        ]
        l7 = calc._calculate_l7_cost_efficiency(results)
        assert l7 is not None
        assert "cost_efficiency" in l7
        # cost_efficiency should be a numeric value
        assert isinstance(l7["cost_efficiency"], float)

    def test_l7_no_without_skill_cost(self):
        """When no without-skill data, cost_delta_pct should be 0."""
        calc = MetricsCalculator()
        results = [
            {"skill_used": True, "cost": 0.05},
            {"skill_used": True, "cost": 0.03},
        ]
        l7 = calc._calculate_l7_cost_efficiency(results)
        assert l7 is not None
        assert l7["cost_delta_pct"] == 0.0

    def test_l7_all_costs_zero(self):
        """When all costs are zero, efficiency should handle gracefully."""
        calc = MetricsCalculator()
        results = [
            {"skill_used": True, "cost": 0.0},
            {"skill_used": False, "cost": 0.0},
        ]
        l7 = calc._calculate_l7_cost_efficiency(results)
        assert l7 is not None
        assert l7["cost_per_eval"] == 0.0
        assert l7["total_cost"] == 0.0
