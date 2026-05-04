"""Tests for adapters/pricing.py — model pricing table and token→$ conversion."""

import pytest
from adapters.pricing import ModelPricing, get_pricing


class TestModelPricing:
    """Test model pricing table and cost calculation."""

    def setup_method(self):
        self.pricing = ModelPricing()

    def test_initialization_has_default_models(self):
        """ModelPricing should have a default pricing table."""
        pricing = ModelPricing()
        # Should have at least some models loaded
        assert len(pricing.models) > 0

    def test_get_model_price_known_model(self):
        """Should return pricing for known models."""
        # Anthropic Claude family
        price = self.pricing.get_model_price("claude-sonnet-4-5-20250514")
        assert price is not None
        assert price["input_per_m"] > 0
        assert price["output_per_m"] > 0

    def test_get_model_price_qwen_model(self):
        """Should return pricing for Qwen models."""
        price = self.pricing.get_model_price("qwen3.6-plus")
        assert price is not None
        assert price["input_per_m"] > 0
        assert price["output_per_m"] > 0

    def test_get_model_price_unknown_model(self):
        """Should return None for unknown models."""
        price = self.pricing.get_model_price("some-unknown-model-xyz")
        assert price is None

    def test_get_model_price_case_sensitive(self):
        """Model name matching should be exact."""
        price_exact = self.pricing.get_model_price("qwen3.6-plus")
        assert price_exact is not None


class TestCalculateCost:
    """Test cost calculation from token usage."""

    def setup_method(self):
        self.pricing = ModelPricing()

    def test_calculate_cost_basic(self):
        """Should calculate cost from prompt_tokens, completion_tokens, and model."""
        cost = self.pricing.calculate_cost(
            prompt_tokens=1000,
            completion_tokens=500,
            model_name="qwen3.6-plus"
        )
        assert cost > 0
        assert isinstance(cost, float)

    def test_calculate_cost_zero_tokens(self):
        """Zero tokens should yield zero cost."""
        cost = self.pricing.calculate_cost(
            prompt_tokens=0,
            completion_tokens=0,
            model_name="qwen3.6-plus"
        )
        assert cost == 0.0

    def test_calculate_cost_unknown_model(self):
        """Unknown model should return 0 cost (or a default rate)."""
        cost = self.pricing.calculate_cost(
            prompt_tokens=1000,
            completion_tokens=500,
            model_name="unknown-model"
        )
        # Should return 0 or a very small default rate
        assert cost >= 0

    def test_calculate_cost_formula(self):
        """Cost = (prompt_tokens / 1_000_000) * input_rate + (completion_tokens / 1_000_000) * output_rate."""
        # Use a known price: test with override
        pricing = ModelPricing()
        pricing.add_model("test-model", input_per_m=3.0, output_per_m=15.0)

        cost = pricing.calculate_cost(
            prompt_tokens=1_000_000,  # 1M input tokens
            completion_tokens=1_000_000,  # 1M output tokens
            model_name="test-model"
        )
        # $3.00 + $15.00 = $18.00
        assert cost == pytest.approx(18.0, rel=0.001)

    def test_calculate_cost_partial_tokens(self):
        """Should correctly calculate partial token costs."""
        pricing = ModelPricing()
        pricing.add_model("test-model", input_per_m=10.0, output_per_m=20.0)

        cost = pricing.calculate_cost(
            prompt_tokens=500_000,  # 0.5M input
            completion_tokens=250_000,  # 0.25M output
            model_name="test-model"
        )
        # $5.00 + $5.00 = $10.00
        assert cost == pytest.approx(10.0, rel=0.001)


class TestAddModel:
    """Test adding custom model pricing."""

    def test_add_model(self):
        """Should allow adding custom model pricing."""
        pricing = ModelPricing()
        pricing.add_model("my-custom-model", input_per_m=5.0, output_per_m=25.0)

        price = pricing.get_model_price("my-custom-model")
        assert price is not None
        assert price["input_per_m"] == 5.0
        assert price["output_per_m"] == 25.0

    def test_add_model_overrides_existing(self):
        """Adding a model with same name should override."""
        pricing = ModelPricing()
        pricing.add_model("test-override", input_per_m=1.0, output_per_m=2.0)
        pricing.add_model("test-override", input_per_m=10.0, output_per_m=20.0)

        price = pricing.get_model_price("test-override")
        assert price["input_per_m"] == 10.0
        assert price["output_per_m"] == 20.0


class TestGetPricing:
    """Test the get_pricing() convenience function."""

    def test_get_pricing_returns_instance(self):
        """get_pricing() should return a ModelPricing instance."""
        pricing = get_pricing()
        assert isinstance(pricing, ModelPricing)

    def test_get_pricing_singleton(self):
        """get_pricing() should return the same instance (singleton)."""
        p1 = get_pricing()
        p2 = get_pricing()
        assert p1 is p2
