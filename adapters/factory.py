"""Factory for creating model adapters by auto-detecting the correct type from model name."""

import logging

from engine.config import ModelConfig

from .anthropic_compat import AnthropicCompatAdapter
from .base import ModelAdapter
from .openai_compat import OpenAICompatAdapter

logger = logging.getLogger(__name__)


def _is_known_provider(model_name: str) -> bool:
    """Check if a model name matches a known provider pattern (case-insensitive)."""
    return any(kw in model_name for kw in ("claude", "qwen", "deepseek"))


def create_adapter(model_config: ModelConfig, rpm_limit: int = 60) -> ModelAdapter:
    """Create a model adapter by auto-detecting the correct type from the model name.

    Auto-detection rules (checked case-insensitively):
      - "claude" in model_name → AnthropicCompatAdapter
      - "qwen" in model_name   → OpenAICompatAdapter (Qwen uses OpenAI-compat API)
      - "deepseek" in model_name → OpenAICompatAdapter
      - Any other name          → OpenAICompatAdapter (default, with warning logged)

    Args:
        model_config: ModelConfig with base_url, api_key, model_name, and optional fallback fields.
        rpm_limit: Rate limit in requests per minute (default: 60).

    Returns:
        An initialized ModelAdapter instance.
    """
    model_name = model_config.model_name.lower()

    if "claude" in model_name:
        logger.info("Detected Anthropic-compatible model: %s", model_config.model_name)
        return AnthropicCompatAdapter(
            base_url=model_config.base_url,
            api_key=model_config.api_key,
            model=model_config.model_name,
            fallback_model=model_config.fallback_model,
            rpm_limit=rpm_limit,
        )

    if "qwen" in model_name:
        logger.info("Detected Qwen model (OpenAI-compatible): %s", model_config.model_name)
    elif "deepseek" in model_name:
        logger.info("Detected DeepSeek model (OpenAI-compatible): %s", model_config.model_name)
    else:
        logger.warning(
            "Unknown model name '%s', falling back to OpenAICompatAdapter",
            model_config.model_name,
        )

    return OpenAICompatAdapter(
        base_url=model_config.base_url,
        api_key=model_config.api_key,
        model=model_config.provider_model or model_config.model_name,
        fallback_model=model_config.fallback_model,
        fallback_base_url=model_config.fallback_base_url,
        fallback_api_key=model_config.fallback_api_key,
        rpm_limit=rpm_limit,
    )
