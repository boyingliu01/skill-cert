import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from engine.config import SkillCertConfig
from skill_cert.cli import EXIT_ERROR, EXIT_FAIL_WITH_CAVEATS, EXIT_PASS, main


def test_default_config_values():
    """Test that default configuration values are correctly set."""
    config = SkillCertConfig()

    assert config.max_concurrency == 5
    assert config.rate_limit_rpm == 60
    assert config.request_timeout == 120
    assert config.judge_temperature == 0.0
    assert config.max_testgen_rounds == 3
    assert config.max_gapfill_rounds == 3
    assert config.max_total_time == 3600
    assert config.models == []


def test_config_from_env_vars():
    """Test loading configuration from environment variables."""
    with patch.dict(
        os.environ,
        {
            "SKILL_CERT_MAX_CONCURRENCY": "10",
            "SKILL_CERT_RATE_LIMIT_RPM": "120",
            "SKILL_CERT_TIMEOUT": "180",
            "SKILL_CERT_JUDGE_TEMP": "0.1",
            "SKILL_CERT_MAX_TESTGEN_ROUNDS": "5",
            "SKILL_CERT_MAX_GAPFILL_ROUNDS": "4",
            "SKILL_CERT_MAX_TOTAL_TIME": "7200",
        },
    ):
        config = SkillCertConfig.load()

        assert config.max_concurrency == 10
        assert config.rate_limit_rpm == 120
        assert config.request_timeout == 180
        assert config.judge_temperature == 0.1
        assert config.max_testgen_rounds == 5
        assert config.max_gapfill_rounds == 4
        assert config.max_total_time == 7200


def test_config_from_cli_args():
    """Test loading configuration from CLI arguments."""

    class MockArgs:
        max_concurrency = 8
        rate_limit_rpm = 100
        request_timeout = 200
        judge_temperature = 0.2
        max_testgen_rounds = 6
        max_gapfill_rounds = 5
        max_total_time = 5400
        models = None

    config = SkillCertConfig.load(cli_args=MockArgs())

    assert config.max_concurrency == 8
    assert config.rate_limit_rpm == 100
    assert config.request_timeout == 200
    assert config.judge_temperature == 0.2
    assert config.max_testgen_rounds == 6
    assert config.max_gapfill_rounds == 5
    assert config.max_total_time == 5400


def test_config_priority_order():
    """Test that CLI args override env vars, which override defaults."""
    with patch.dict(
        os.environ, {"SKILL_CERT_MAX_CONCURRENCY": "10", "SKILL_CERT_RATE_LIMIT_RPM": "120"}
    ):

        class MockArgs:
            max_concurrency = 15
            rate_limit_rpm = None
            request_timeout = 200
            judge_temperature = None
            max_testgen_rounds = None
            max_gapfill_rounds = None
            max_total_time = None
            models = None

        config = SkillCertConfig.load(cli_args=MockArgs())

        assert config.max_concurrency == 15
        assert config.rate_limit_rpm == 120
        assert config.request_timeout == 200


def test_parse_models_from_env():
    """Test parsing models from environment variable."""
    models_env = "gpt-4=https://api.openai.com,v1.secret.key,fallback|claude-3=https://api.anthropic.com,v2.secret.key"

    models = SkillCertConfig._parse_models_from_env(models_env)

    assert len(models) == 2

    assert models[0].model_name == "gpt-4"
    assert models[0].base_url == "https://api.openai.com"
    assert models[0].api_key == "v1.secret.key"
    assert models[0].fallback_model == "fallback"

    assert models[1].model_name == "claude-3"
    assert models[1].base_url == "https://api.anthropic.com"
    assert models[1].api_key == "v2.secret.key"
    assert models[1].fallback_model is None


def test_parse_models_from_cli():
    """Test parsing models from CLI arguments."""
    models_cli = [
        "gpt-4=https://api.openai.com,v1.secret.key,fallback",
        "claude-3=https://api.anthropic.com,v2.secret.key",
    ]

    models = SkillCertConfig._parse_models_from_cli(models_cli)

    assert len(models) == 2

    assert models[0].model_name == "gpt-4"
    assert models[0].base_url == "https://api.openai.com"
    assert models[0].api_key == "v1.secret.key"
    assert models[0].fallback_model == "fallback"

    assert models[1].model_name == "claude-3"
    assert models[1].base_url == "https://api.anthropic.com"
    assert models[1].api_key == "v2.secret.key"
    assert models[1].fallback_model is None


def test_parse_models_from_cli_with_provider_model():
    models_cli = [
        "alias=http://localhost,key,fallback,LOCAL/Qwen3.5-122B-A10B",
    ]
    models = SkillCertConfig._parse_models_from_cli(models_cli)

    assert len(models) == 1
    assert models[0].model_name == "alias"
    assert models[0].base_url == "http://localhost"
    assert models[0].api_key == "key"
    assert models[0].fallback_model == "fallback"
    assert models[0].provider_model == "LOCAL/Qwen3.5-122B-A10B"


def test_parse_models_from_cli_without_provider_model_defaults_to_model_name():
    """When provider_model is omitted (3-part CLI format), provider_model defaults to model_name."""
    models_cli = [
        "gpt-4=https://api.openai.com,v1.secret.key",
    ]
    models = SkillCertConfig._parse_models_from_cli(models_cli)

    assert models[0].model_name == "gpt-4"
    assert models[0].provider_model == "gpt-4"


def test_provider_model_in_file_config():
    """models.yaml can specify provider_model separately from model_name."""
    from engine.config import ModelConfig

    cfg = ModelConfig(
        model_name="whalecloud-qwen3",
        base_url="https://lab.iwhalecloud.com/gpt-proxy",
        api_key="secret",
        provider_model="LOCAL/Qwen3.5-122B-A10B",
    )
    assert cfg.model_name == "whalecloud-qwen3"
    assert cfg.provider_model == "LOCAL/Qwen3.5-122B-A10B"


def _config_file_setup():
    """Common helper: return (unique_config_dir, models_yaml_path) for an isolated temporary config.

    We use a unique-per-call temp dir so parallel --fast execution does not race on shared paths.
    """
    import shutil
    from pathlib import Path as RealPath

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yaml") as f:
        f.write("""
max_concurrency: 7
rate_limit_rpm: 80
models:
  - model_name: test-model
    base_url: https://test.api.com
    api_key: test-key
    fallback_model: fallback-model
""")
        temp_config_path = f.name

    config_dir = RealPath(tempfile.mkdtemp()) / ".skill-cert"
    config_dir.mkdir(exist_ok=True, parents=True)
    target_path = config_dir / "models.yaml"
    shutil.move(temp_config_path, target_path)

    original_expanduser = os.path.expanduser

    def mock_expanduser(path):
        if path == "~":
            return str(config_dir.parent)
        return original_expanduser(path)

    return config_dir, target_path, mock_expanduser, original_expanduser


def test_provider_model_in_file_config_from_file():
    """Load config from file with valid YAML — uses isolated temp dir for parallel safety."""
    config_dir, target_path, mock_expanduser, original_expanduser = _config_file_setup()
    try:
        with patch("os.path.expanduser", side_effect=mock_expanduser):
            config = SkillCertConfig.load()

            assert config.max_concurrency == 7
            assert config.rate_limit_rpm == 80
            assert len(config.models) == 1
            assert config.models[0].model_name == "test-model"
            assert config.models[0].base_url == "https://test.api.com"
            assert config.models[0].api_key == "test-key"
            assert config.models[0].fallback_model == "fallback-model"
    finally:
        import shutil

        shutil.rmtree(str(config_dir.parent), ignore_errors=True)


def test_config_from_file_with_valid_yaml():
    """Load config from file with valid YAML — isolated temp dir for parallel safety.

    Formerly named 'test_config_from_file_with_error' (but the YAML *was* valid).
    """
    config_dir, target_path, mock_expanduser, original_expanduser = _config_file_setup()
    try:
        with patch("os.path.expanduser", side_effect=mock_expanduser):
            config = SkillCertConfig.load()

            assert config.max_concurrency == 7
            assert config.rate_limit_rpm == 80
            assert len(config.models) == 1
            assert config.models[0].model_name == "test-model"
    finally:
        import shutil

        shutil.rmtree(str(config_dir.parent), ignore_errors=True)


def test_config_from_file_with_malformed_yaml():
    """Test loading configuration from malformed YAML file — isolated temp dir."""
    import shutil

    _write_fixture = """\
max_concurrency: 7
rate_limit_rpm: 80
models:
  - model_name: test-model
    base_url: https://test.api.com
    api_key: test-key
    fallback_model: fallback-model
  malformed_yaml:
    - item1
    item2: value2  # This is malformed
"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yaml") as f:
        f.write(_write_fixture)
        temp_config_path = f.name

    from pathlib import Path as RealPath

    config_dir = RealPath(tempfile.mkdtemp()) / ".skill-cert"
    config_dir.mkdir(exist_ok=True, parents=True)
    target_path = config_dir / "models.yaml"
    shutil.move(temp_config_path, target_path)

    original_expanduser = os.path.expanduser

    def mock_expanduser(path):
        if path == "~":
            return str(config_dir.parent)
        return original_expanduser(path)

    try:
        with patch("os.path.expanduser", side_effect=mock_expanduser):
            config = SkillCertConfig.load()

            assert config.max_concurrency == 5  # Default value (malformed file ignored)
            assert config.rate_limit_rpm == 60  # Default value
    finally:
        shutil.rmtree(str(config_dir.parent), ignore_errors=True)


def test_config_with_invalid_env_var_values():
    """Test loading configuration with invalid environment variable values."""
    with patch.dict(
        os.environ,
        {
            "SKILL_CERT_MAX_CONCURRENCY": "not_a_number",
            "SKILL_CERT_RATE_LIMIT_RPM": "also_not_a_number",
            "SKILL_CERT_TIMEOUT": "still_not_a_number",
            "SKILL_CERT_JUDGE_TEMP": "not_a_float",
        },
    ):
        config = SkillCertConfig.load()

        # Should use default values when env vars can't be converted
        assert config.max_concurrency == 5  # Default value
        assert config.rate_limit_rpm == 60  # Default value
        assert config.request_timeout == 120  # Default value
        assert config.judge_temperature == 0.0  # Default value


def test_load_models_from_config_with_api_key_resolution():
    """Test loading models from config with API key resolution."""
    models_config = [
        {
            "model_name": "test-model",
            "base_url": "https://test.api.com",
            "api_key": "${TEST_API_KEY}",  # This should resolve from env
            "fallback_model": "fallback-model",
        }
    ]

    with patch.dict(os.environ, {"TEST_API_KEY": "resolved-api-key"}):
        models = SkillCertConfig._load_models_from_config(models_config)

        assert len(models) == 1
        assert models[0].model_name == "test-model"
        assert models[0].api_key == "resolved-api-key"


def test_load_models_from_config_with_unresolved_api_key():
    """Test loading models from config with unresolved API key."""
    models_config = [
        {
            "model_name": "test-model",
            "base_url": "https://test.api.com",
            "api_key": "${UNRESOLVED_API_KEY}",  # This should remain unresolved
            "fallback_model": "fallback-model",
        }
    ]

    # Don't set the environment variable
    models = SkillCertConfig._load_models_from_config(models_config)

    assert len(models) == 1
    assert models[0].model_name == "test-model"
    assert models[0].api_key == "${UNRESOLVED_API_KEY}"  # Should remain as-is


def test_load_models_from_config_with_name_fallback_to_model_name():
    """When models.yaml uses 'name' instead of 'model_name', it should fall back gracefully."""
    models_config = [
        {
            "name": "whalecloud-qwen3",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-test",
            "provider_model": "LOCAL/Qwen3.5-122B-A10B",
        }
    ]
    models = SkillCertConfig._load_models_from_config(models_config)

    assert len(models) == 1
    # 'name' should be mapped to 'model_name' when 'model_name' is absent
    assert models[0].model_name == "whalecloud-qwen3"
    assert models[0].provider_model == "LOCAL/Qwen3.5-122B-A10B"
    assert models[0].base_url == "https://api.example.com/v1"


def test_load_models_from_config_with_both_name_and_model_name():
    """When both 'name' and 'model_name' are present, 'model_name' should take precedence."""
    models_config = [
        {
            "name": "display-name",
            "model_name": "LOCAL/RealModel",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-test",
        }
    ]
    models = SkillCertConfig._load_models_from_config(models_config)

    assert len(models) == 1
    # 'model_name' should be used when both are present
    assert models[0].model_name == "LOCAL/RealModel"


def test_parse_models_from_env_with_invalid_format():
    """Test parsing models from environment variable with invalid format."""
    models_env = "invalid_format_without_equals_sign"

    models = SkillCertConfig._parse_models_from_env(models_env)

    assert len(models) == 0  # Should return empty list for invalid format


def test_parse_models_from_env_with_partial_config():
    """Test parsing models from environment variable with partial configuration."""
    models_env = "gpt-4=https://api.openai.com,partial_key"  # Only 2 parts instead of 3

    models = SkillCertConfig._parse_models_from_env(models_env)

    assert len(models) == 1
    assert models[0].model_name == "gpt-4"
    assert models[0].base_url == "https://api.openai.com"
    assert models[0].api_key == "partial_key"
    assert models[0].fallback_model is None  # Should be None when not provided


def test_parse_models_from_cli_with_invalid_format():
    """Test parsing models from CLI arguments with invalid format."""
    models_cli = ["invalid_format_without_equals_sign"]

    models = SkillCertConfig._parse_models_from_cli(models_cli)

    assert len(models) == 0  # Should return empty list for invalid format


def test_parse_models_from_cli_with_partial_config():
    """Test parsing models from CLI arguments with partial configuration."""
    models_cli = ["gpt-4=https://api.openai.com,partial_key"]  # Only 2 parts instead of 3

    models = SkillCertConfig._parse_models_from_cli(models_cli)

    assert len(models) == 1
    assert models[0].model_name == "gpt-4"
    assert models[0].base_url == "https://api.openai.com"
    assert models[0].api_key == "partial_key"
    assert models[0].fallback_model is None  # Should be None when not provided


def test_config_with_models_from_env():
    """Test loading configuration with models from environment variable."""
    with (
        patch.dict(
            os.environ,
            {
                "SKILL_CERT_MODELS": "gpt-4=https://api.openai.com,test.key,fallback|claude=https://api.claude.com,claude.key"
            },
        ),
        patch.object(SkillCertConfig, "_apply_config_file", return_value={"models": []}),
    ):
        # Create a mock CLI args without models to trigger env var usage
        class MockArgs:
            max_concurrency = None
            rate_limit_rpm = None
            request_timeout = None
            judge_temperature = None
            max_testgen_rounds = None
            max_gapfill_rounds = None
            max_total_time = None
            models = None  # This should trigger env var usage

        config = SkillCertConfig.load(cli_args=MockArgs())

        assert len(config.models) == 2
        assert config.models[0].model_name == "gpt-4"
        assert config.models[0].base_url == "https://api.openai.com"
        assert config.models[0].api_key == "test.key"
        assert config.models[0].fallback_model == "fallback"

        assert config.models[1].model_name == "claude"
        assert config.models[1].base_url == "https://api.claude.com"
        assert config.models[1].api_key == "claude.key"
        assert config.models[1].fallback_model is None


class TestCLI:
    def test_cli_no_args_shows_error(self):
        with patch.object(sys, "argv", ["skill_cert"]), patch("sys.exit") as mock_exit:
            main()
            mock_exit.assert_called_once()

    def test_cli_help_output(self, capsys):
        with patch.object(sys, "argv", ["skill_cert", "--help"]), pytest.raises(SystemExit):
            main()
        captured = capsys.readouterr()
        assert "--skill" in captured.out
        assert "--mode" in captured.out
        assert "--models" in captured.out
        assert "--max-turns" in captured.out
        assert "--session" in captured.out

    def test_cli_missing_skill(self):
        with patch.object(sys, "argv", ["skill_cert"]), pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 2

    def test_cli_nonexistent_skill(self):
        with patch.object(sys, "argv", ["skill_cert", "--skill", "/nonexistent.md"]):
            exit_code = main()
            assert exit_code == EXIT_ERROR

    def test_cli_valid_skill_no_models(self, monkeypatch, tmp_path):
        """Real SKILL.md at project root, no models configured → EXIT_ERROR.

        Uses monkeypatch/tmp_path to isolate from local ~/.skill-cert/models.yaml.
        """
        spec_path = str(Path(__file__).parent.parent / "SKILL.md")
        assert Path(spec_path).exists(), f"SKILL.md not found at {spec_path}"

        # Isolate from any existing config: empty HOME means no ~/.skill-cert/models.yaml
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("SKILL_CERT_MODELS", raising=False)

        with patch.object(sys, "argv", ["skill_cert", "--skill", spec_path]):
            exit_code = main()
            assert exit_code == EXIT_ERROR

    def test_cli_mode_single_is_default(self, capsys):
        with patch.object(sys, "argv", ["skill_cert", "--help"]), pytest.raises(SystemExit):
            main()
        captured = capsys.readouterr()
        assert "single" in captured.out
        assert "dialogue" in captured.out
        assert "replay" in captured.out

    def test_cli_mode_dialogue_requires_max_turns(self, capsys):
        with patch.object(sys, "argv", ["skill_cert", "--help"]), pytest.raises(SystemExit):
            main()
        captured = capsys.readouterr()
        assert "--max-turns" in captured.out

    def test_cli_mode_replay_requires_session(self, capsys):
        with patch.object(sys, "argv", ["skill_cert", "--help"]), pytest.raises(SystemExit):
            main()
        captured = capsys.readouterr()
        assert "--session" in captured.out

    def test_cli_exit_codes_defined(self):
        assert EXIT_PASS == 0
        assert EXIT_ERROR == 1
        assert EXIT_FAIL_WITH_CAVEATS == 2


if __name__ == "__main__":
    pytest.main([__file__])
