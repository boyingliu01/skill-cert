"""Setup subcommand — interactive model configuration for skill-cert."""

import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from engine.config import ModelConfig

if TYPE_CHECKING:
    from argparse import Namespace

CONFIG_DIR = Path.home() / ".skill-cert"
CONFIG_FILE = CONFIG_DIR / "models.yaml"

EXIT_OK = 0
EXIT_ERROR = 1


def _validate_base_url(url: str) -> str | None:
    """Return an error message if the URL is obviously invalid, else None."""
    if not url:
        return "URL cannot be empty"
    if not url.startswith(("http://", "https://")):
        return "URL must start with http:// or https://"
    return None


def _validate_api_key(key: str) -> str | None:
    """Return an error message if the API key is obviously invalid, else None."""
    if not key or not key.strip():
        return "API key cannot be empty"
    if key.startswith("$"):
        return None  # env-var reference like $OPENAI_API_KEY — allowed
    if len(key.strip()) < 8:
        return "API key seems too short (minimum 8 characters)"
    return None


def _test_connectivity(model: ModelConfig, timeout: int = 15) -> tuple[bool, str]:
    """Test LLM connectivity with a minimal request.

    Returns:
        (success, message)
    """
    from adapters.factory import create_adapter

    try:
        adapter = create_adapter(model)
        response = adapter.chat(
            messages=[{"role": "user", "content": "Say OK"}],
            system="You are a test endpoint. Reply with exactly 'OK'.",
            timeout=timeout,
        )
        if response:
            return True, f"Connected successfully (response: {response[:60]}...)"
        return False, "Empty response from model"
    except Exception as e:
        return False, str(e)


def _write_config(models: list[ModelConfig]) -> Path:
    """Write model configuration to the config file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    models_data = []
    for m in models:
        entry: dict = {
            "model_name": m.model_name,
            "base_url": m.base_url,
            "api_key": m.api_key,
        }
        if m.fallback_model:
            entry["fallback_model"] = m.fallback_model
        models_data.append(entry)

    with open(CONFIG_FILE, "w") as f:
        yaml.dump({"models": models_data}, f, default_flow_style=False, allow_unicode=True)

    return CONFIG_FILE


def _load_existing_models() -> list[ModelConfig]:
    """Load existing models from config file, return empty list if not found."""
    if not CONFIG_FILE.exists():
        return []
    try:
        with open(CONFIG_FILE) as f:
            data = yaml.safe_load(f)
        if data and "models" in data:
            return [ModelConfig(**m) for m in data["models"]]
    except Exception:
        pass
    return []


def _prompt_input(prompt: str, default: str = "", input_fn=input) -> str:
    """Prompt user for input with optional default value."""
    if default:
        value = input_fn(f"  {prompt} [{default}]: ").strip()
        return value if value else default
    return input_fn(f"  {prompt}: ").strip()


def _print_setup_header(output_fn: Callable) -> None:
    """Print setup wizard header."""
    output_fn("\n=== Skill-Cert Model Setup ===\n")
    output_fn("Configure LLM models for skill evaluation.")
    output_fn(f"Config will be saved to: {CONFIG_FILE}\n")


def _handle_existing_config(
    existing: list[ModelConfig], input_fn: Callable, output_fn: Callable
) -> bool:
    """Handle existing config. Return True if user wants to overwrite."""
    if not existing:
        return True

    output_fn(f"Found {len(existing)} existing model(s):")
    for i, m in enumerate(existing, 1):
        output_fn(f"  {i}. {m.model_name} @ {m.base_url}")
    answer = input_fn("\nOverwrite existing config? [y/N]: ").strip().lower()
    if answer != "y":
        output_fn("Setup cancelled. Existing config preserved.")
        return False
    output_fn("")
    return True


def _prompt_model_name(input_fn: Callable, output_fn: Callable) -> str | None:
    """Prompt for model name. Return None if invalid."""
    name = _prompt_input(
        "Model name (e.g. qwen3.6-plus, claude-sonnet-4-20250514)",
        input_fn=input_fn,
    )
    if not name:
        output_fn("  ERROR: Model name is required")
        return None
    return name


def _prompt_and_validate_url(input_fn: Callable, output_fn: Callable) -> str | None:
    """Prompt for URL and validate. Return None if invalid."""
    url = _prompt_input("API base URL (e.g. https://api.example.com/v1)", input_fn=input_fn)
    err = _validate_base_url(url)
    if err:
        output_fn(f"  ERROR: {err}")
        return None
    return url


def _prompt_and_validate_key(input_fn: Callable, output_fn: Callable) -> str | None:
    """Prompt for API key and validate. Return None if invalid."""
    key = _prompt_input("API key (or $ENV_VAR_NAME)", input_fn=input_fn)
    err = _validate_api_key(key)
    if err:
        output_fn(f"  ERROR: {err}")
        return None
    return key


def _prompt_fallback_model(input_fn: Callable) -> str | None:
    """Prompt for fallback model. Return None if skipped."""
    fallback = _prompt_input(
        "Fallback model name (optional, press Enter to skip)",
        default="",
        input_fn=input_fn,
    )
    return fallback if fallback else None


def _test_and_confirm_model(
    model: ModelConfig,
    input_fn: Callable,
    output_fn: Callable,
    test_fn: Callable | None,
) -> bool:
    """Test connectivity and confirm with user. Return True if should save."""
    output_fn(f"  Testing connectivity to {model.model_name}...")
    if test_fn:
        success, msg = test_fn(model)
    else:
        success, msg = _test_connectivity(model)

    if success:
        output_fn(f"  OK: {msg}")
        return True

    output_fn(f"  WARN: Connection failed — {msg}")
    answer = input_fn("  Save this model anyway? [y/N]: ").strip().lower()
    if answer != "y":
        output_fn("  Skipped.\n")
        return False
    return True


def _prompt_add_another_model(model_num: int, input_fn: Callable) -> bool:
    """Prompt if user wants to add another model. Return True if yes."""
    if model_num < 2:
        return True

    answer = (
        input_fn("Add another model? (recommended for drift detection) [y/N]: ").strip().lower()
    )
    return answer == "y"


def _print_setup_summary(models: list[ModelConfig], path: Path, output_fn: Callable) -> None:
    """Print setup completion summary."""
    output_fn(f"\nSetup complete! {len(models)} model(s) saved to {path}")
    output_fn("\nQuick start:")
    output_fn("  skill-cert --skill path/to/SKILL.md")
    if len(models) >= 2:
        output_fn("\nDrift detection enabled (multiple models configured).")


def _setup_interactive(
    input_fn: Callable = input,
    output_fn: Callable = print,
    test_fn: Callable | None = None,
) -> int:
    """Run interactive setup wizard.

    Args:
        input_fn: Function for reading user input (default: built-in input).
        output_fn: Function for printing output (default: built-in print).
        test_fn: Optional override for connectivity test (for testing).

    Returns:
        Exit code (0 = success, 1 = error).
    """
    _print_setup_header(output_fn)

    existing = _load_existing_models()
    if not _handle_existing_config(existing, input_fn, output_fn):
        return EXIT_OK

    models: list[ModelConfig] = []
    model_num = 1

    while True:
        output_fn(f"--- Model {model_num} ---")

        name = _prompt_model_name(input_fn, output_fn)
        if not name:
            continue

        url = _prompt_and_validate_url(input_fn, output_fn)
        if not url:
            continue

        key = _prompt_and_validate_key(input_fn, output_fn)
        if not key:
            continue

        fallback = _prompt_fallback_model(input_fn)

        model = ModelConfig(
            model_name=name,
            base_url=url,
            api_key=key,
            fallback_model=fallback,
        )

        if not _test_and_confirm_model(model, input_fn, output_fn, test_fn):
            continue

        models.append(model)
        output_fn(f"  Added: {name}\n")
        model_num += 1

        if not _prompt_add_another_model(model_num, input_fn):
            break

    if not models:
        output_fn("\nNo models configured. Setup cancelled.")
        return EXIT_ERROR

    path = _write_config(models)
    _print_setup_summary(models, path, output_fn)

    return EXIT_OK


def _setup_non_interactive(
    model_name: str,
    base_url: str,
    api_key: str,
    fallback_model: str = "",
    skip_test: bool = False,
    test_fn: Callable | None = None,
) -> int:
    """Run non-interactive setup with parameters.

    Returns:
        Exit code (0 = success, 1 = error).
    """
    err = _validate_base_url(base_url)
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        return EXIT_ERROR

    err = _validate_api_key(api_key)
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        return EXIT_ERROR

    model = ModelConfig(
        model_name=model_name,
        base_url=base_url,
        api_key=api_key,
        fallback_model=fallback_model if fallback_model else None,
    )

    if not skip_test:
        print(f"Testing connectivity to {model_name}...")
        if test_fn:
            success, msg = test_fn(model)
        else:
            success, msg = _test_connectivity(model)
        if success:
            print(f"OK: {msg}")
        else:
            print(f"WARN: Connection failed — {msg}")
            print("Saving config anyway (use --skip-test to suppress this warning)")

    path = _write_config([model])
    print(f"Setup complete! Model saved to {path}")
    return EXIT_OK


def run_setup(args: "Namespace | None" = None) -> int:
    """Entry point for the setup subcommand.

    Supports both interactive (wizard) and non-interactive (--model-name) modes.

    Args:
        args: Parsed argparse namespace. If None or no model flags, runs interactive mode.

    Returns:
        Exit code (0 = success, 1 = error).
    """
    if args and getattr(args, "model_name", None):
        return _setup_non_interactive(
            model_name=args.model_name,
            base_url=args.base_url,
            api_key=args.api_key,
            fallback_model=getattr(args, "fallback_model", "") or "",
            skip_test=getattr(args, "skip_test", False),
        )
    return _setup_interactive()
