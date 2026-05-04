"""Model pricing table — converts token usage to $ cost."""

from typing import Dict, Optional

_MODEL_PRICING = {
    # Anthropic Claude family (per 1M tokens)
    "claude-sonnet-4-5-20250514": {"input_per_m": 3.0, "output_per_m": 15.0},
    "claude-sonnet-4-20250514": {"input_per_m": 3.0, "output_per_m": 15.0},
    "claude-opus-4-20250514": {"input_per_m": 15.0, "output_per_m": 75.0},
    "claude-opus-4-1-20250805": {"input_per_m": 15.0, "output_per_m": 75.0},
    "claude-haiku-4-20250514": {"input_per_m": 0.8, "output_per_m": 4.0},
    # OpenAI GPT family
    "gpt-5": {"input_per_m": 1.25, "output_per_m": 10.0},
    "gpt-5-mini": {"input_per_m": 0.25, "output_per_m": 2.0},
    "gpt-4o": {"input_per_m": 2.5, "output_per_m": 10.0},
    "gpt-4o-mini": {"input_per_m": 0.15, "output_per_m": 0.6},
    # Qwen family
    "qwen3.6-plus": {"input_per_m": 0.3, "output_per_m": 0.9},
    "qwen3.5-plus": {"input_per_m": 0.3, "output_per_m": 0.9},
    "qwen3-coder-plus": {"input_per_m": 0.3, "output_per_m": 0.9},
    "qwen3-coder-next": {"input_per_m": 0.4, "output_per_m": 1.2},
    # DeepSeek
    "deepseek-chat": {"input_per_m": 0.14, "output_per_m": 0.56},
    "deepseek-reasoner": {"input_per_m": 0.55, "output_per_m": 2.19},
    # Google Gemini
    "gemini-2.5-pro": {"input_per_m": 1.25, "output_per_m": 10.0},
    "gemini-2.5-flash": {"input_per_m": 0.15, "output_per_m": 0.6},
    # Whalecloud LOCAL (free — local deployment)
    "LOCAL/Qwen3.5-122B-A10B": {"input_per_m": 0.0, "output_per_m": 0.0},
    "LOCAL/MiniMax-M2.7": {"input_per_m": 0.0, "output_per_m": 0.0},
}


class ModelPricing:
    def __init__(self):
        self.models: Dict[str, Dict[str, float]] = dict(_MODEL_PRICING)

    def get_model_price(self, model_name: str) -> Optional[Dict[str, float]]:
        return self.models.get(model_name)

    def add_model(self, model_name: str, input_per_m: float, output_per_m: float):
        self.models[model_name] = {"input_per_m": input_per_m, "output_per_m": output_per_m}

    def calculate_cost(self, prompt_tokens: int, completion_tokens: int, model_name: str) -> float:
        price = self.get_model_price(model_name)
        if price is None:
            return 0.0
        return (prompt_tokens / 1_000_000) * price["input_per_m"] + \
               (completion_tokens / 1_000_000) * price["output_per_m"]


_pricing_instance: Optional[ModelPricing] = None


def get_pricing() -> ModelPricing:
    global _pricing_instance
    if _pricing_instance is None:
        _pricing_instance = ModelPricing()
    return _pricing_instance
