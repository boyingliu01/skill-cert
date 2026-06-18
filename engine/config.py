import logging
import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)

from engine.constants import ConcurrencyLimits, TestGenLimits, TimingLimits


class ModelConfig(BaseModel):
    base_url: str
    api_key: str
    model_name: str
    provider_model: str | None = None
    fallback_model: str | None = None
    fallback_base_url: str | None = None
    fallback_api_key: str | None = None

    @model_validator(mode="after")
    def _resolve_provider_model(self) -> "ModelConfig":
        if not self.provider_model:
            self.provider_model = self.model_name
        return self


class SkillCertConfig(BaseModel):
    """Configuration with loading priority: CLI args > env vars > config file > defaults"""

    models: list[ModelConfig] = Field(default_factory=list)
    max_concurrency: int = Field(
        default=ConcurrencyLimits.MAX_CONCURRENCY,
        json_schema_extra={"env": "SKILL_CERT_MAX_CONCURRENCY"},
    )
    rate_limit_rpm: int = Field(
        default=TimingLimits.RATE_LIMIT_RPM,
        json_schema_extra={"env": "SKILL_CERT_RATE_LIMIT_RPM"},
    )
    request_timeout: int = Field(
        default=TimingLimits.REQUEST_TIMEOUT,
        json_schema_extra={"env": "SKILL_CERT_TIMEOUT"},
    )
    judge_temperature: float = Field(
        default=0.0,
        json_schema_extra={"env": "SKILL_CERT_JUDGE_TEMP"},
    )
    max_testgen_rounds: int = Field(
        default=TestGenLimits.MAX_REVIEW_ROUNDS,
        json_schema_extra={"env": "SKILL_CERT_MAX_TESTGEN_ROUNDS"},
    )
    max_gapfill_rounds: int = Field(
        default=TestGenLimits.MAX_REVIEW_ROUNDS,
        json_schema_extra={"env": "SKILL_CERT_MAX_GAPFILL_ROUNDS"},
    )
    max_total_time: int = Field(
        default=TimingLimits.GLOBAL_TIMEOUT,
        json_schema_extra={"env": "SKILL_CERT_MAX_TOTAL_TIME"},
    )

    @classmethod
    def load(cls, cli_args=None) -> "SkillCertConfig":
        """Load configuration with priority: CLI args > env vars > config file > defaults"""
        config_dict = cls._get_default_config()
        config_dict = cls._apply_config_file(config_dict)
        config_dict = cls._apply_environment_variables(config_dict)
        config_dict = cls._apply_cli_arguments(config_dict, cli_args)
        return cls(**config_dict)

    @classmethod
    def _get_default_config(cls) -> dict:
        return {
            "max_concurrency": ConcurrencyLimits.MAX_CONCURRENCY,
            "rate_limit_rpm": TimingLimits.RATE_LIMIT_RPM,
            "request_timeout": TimingLimits.REQUEST_TIMEOUT,
            "judge_temperature": 0.0,
            "max_testgen_rounds": TestGenLimits.MAX_REVIEW_ROUNDS,
            "max_gapfill_rounds": TestGenLimits.MAX_REVIEW_ROUNDS,
            "max_total_time": TimingLimits.GLOBAL_TIMEOUT,
            "models": [],
        }

    @classmethod
    def _apply_config_file(cls, config_dict: dict) -> dict:
        config_file_path = Path.home() / ".skill-cert" / "models.yaml"
        if config_file_path.exists():
            try:
                with open(config_file_path) as f:
                    file_config = yaml.safe_load(f)
                    if file_config:
                        if "models" in file_config:
                            models_from_file = cls._load_models_from_config(file_config["models"])
                            config_dict["models"] = models_from_file
                        for key, value in file_config.items():
                            if key != "models":
                                config_dict[key] = value
            except Exception:
                # If config file is malformed, continue with defaults
                pass
        return config_dict

    @classmethod
    def _apply_environment_variables(cls, config_dict: dict) -> dict:
        env_vars = {
            "max_concurrency": os.getenv("SKILL_CERT_MAX_CONCURRENCY"),
            "rate_limit_rpm": os.getenv("SKILL_CERT_RATE_LIMIT_RPM"),
            "request_timeout": os.getenv("SKILL_CERT_TIMEOUT"),
            "judge_temperature": os.getenv("SKILL_CERT_JUDGE_TEMP"),
            "max_testgen_rounds": os.getenv("SKILL_CERT_MAX_TESTGEN_ROUNDS"),
            "max_gapfill_rounds": os.getenv("SKILL_CERT_MAX_GAPFILL_ROUNDS"),
            "max_total_time": os.getenv("SKILL_CERT_MAX_TOTAL_TIME"),
        }

        for key, value in env_vars.items():
            if value is not None:
                if key in [
                    "max_concurrency",
                    "rate_limit_rpm",
                    "max_testgen_rounds",
                    "max_gapfill_rounds",
                    "max_total_time",
                    "request_timeout",
                ]:
                    try:
                        config_dict[key] = int(value)
                    except ValueError:
                        pass
                elif key in ["judge_temperature"]:
                    try:
                        config_dict[key] = float(value)
                    except ValueError:
                        pass
        return config_dict

    @classmethod
    def _apply_cli_arguments(cls, config_dict: dict, cli_args) -> dict:
        if cli_args:
            for field in [
                "max_concurrency",
                "rate_limit_rpm",
                "request_timeout",
                "judge_temperature",
                "max_testgen_rounds",
                "max_gapfill_rounds",
                "max_total_time",
            ]:
                if hasattr(cli_args, field) and getattr(cli_args, field) is not None:
                    config_dict[field] = getattr(cli_args, field)

            if hasattr(cli_args, "models") and cli_args.models:
                config_dict["models"] = cls._parse_models_from_cli(cli_args.models)

        if not config_dict["models"]:
            models_env = os.getenv("SKILL_CERT_MODELS")
            if models_env:
                config_dict["models"] = cls._parse_models_from_env(models_env)
        return config_dict

    @staticmethod
    def _load_models_from_config(models_config: list[dict]) -> list[ModelConfig]:
        def resolve_env_var(value: str, field_name: str = "") -> str:
            if value and value.startswith("${") and value.endswith("}"):
                var_name = value[2:-1]
                resolved = os.getenv(var_name)
                if resolved:
                    return resolved
                if "fallback" in field_name.lower():
                    resolved = os.getenv("DASHSCOPE_API_KEY")
                    if resolved:
                        return resolved
            return value

        models = []
        for model_data in models_config:
            for key in ("api_key", "fallback_api_key", "fallback_base_url"):
                if key in model_data:
                    model_data[key] = resolve_env_var(model_data[key], key)
            # REQ-FIX-46: Gracefully handle `name` field used in place of `model_name`
            # YAML configs written with `name` (display identifier) but missing
            # `model_name` (API model identifier) should not crash. Map `name` -> `model_name`
            # when `model_name` is absent, with a clear warning.
            if "model_name" not in model_data and "name" in model_data:
                logger.warning(
                    "models.yaml entry '%s' uses 'name' instead of 'model_name'. "
                    "Using 'name' value as 'model_name'. Add 'model_name' field "
                    "explicitly to use a different API model identifier.",
                    model_data["name"],
                )
                model_data["model_name"] = model_data.pop("name")
            models.append(ModelConfig(**model_data))
        return models

    @staticmethod
    def _parse_models_from_env(models_env: str) -> list[ModelConfig]:
        """Parse models from environment variable in format:
        model1=url,key,fallback|model2=url,key,fallback"""
        models: list[ModelConfig] = []
        if not models_env:
            return models

        model_strings = models_env.split("|")
        for model_str in model_strings:
            if "=" in model_str:
                name_part, config_part = model_str.split("=", 1)
                config_parts = config_part.split(",")

                if len(config_parts) >= 2:
                    base_url = config_parts[0]
                    api_key = config_parts[1]
                    fallback_model = config_parts[2] if len(config_parts) > 2 else None
                    provider_model = config_parts[3] if len(config_parts) > 3 else None

                    models.append(
                        ModelConfig(
                            model_name=name_part,
                            base_url=base_url,
                            api_key=api_key,
                            fallback_model=fallback_model,
                            provider_model=provider_model,
                        )
                    )

        return models

    @staticmethod
    def _parse_models_from_cli(models_cli: str | list[str]) -> list[ModelConfig]:
        """Parse models from CLI: model1=url,key[,fallback][|model2=url,key[,fallback]]"""
        models = []

        if isinstance(models_cli, str):
            model_strings = models_cli.split("|") if "|" in models_cli else [models_cli]
        else:
            model_strings = models_cli

        for model_arg in model_strings:
            model_arg = model_arg.strip()
            if model_arg and "=" in model_arg:
                name, config_part = model_arg.split("=", 1)
                config_parts = config_part.split(",")
                if len(config_parts) >= 2:
                    base_url = config_parts[0]
                    api_key = config_parts[1]
                    fallback_model = (
                        config_parts[2].strip()
                        if len(config_parts) > 2 and config_parts[2].strip()
                        else None
                    )
                    provider_model = (
                        config_parts[3].strip()
                        if len(config_parts) > 3 and config_parts[3].strip()
                        else None
                    )

                    models.append(
                        ModelConfig(
                            model_name=name.strip(),
                            base_url=base_url,
                            api_key=api_key,
                            fallback_model=fallback_model,
                            provider_model=provider_model,
                        )
                    )

        return models
