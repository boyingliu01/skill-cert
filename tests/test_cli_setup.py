"""Tests for skill_cert.cli.setup — setup subcommand."""

import argparse
from unittest.mock import MagicMock, patch

import yaml

from engine.config import ModelConfig
from skill_cert.cli.setup import (
    EXIT_ERROR,
    EXIT_OK,
    _load_existing_models,
    _setup_interactive,
    _setup_non_interactive,
    _test_connectivity,
    _validate_api_key,
    _validate_base_url,
    _write_config,
    run_setup,
)

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


class TestValidateBaseUrl:
    def test_valid_https(self):
        assert _validate_base_url("https://api.example.com/v1") is None

    def test_valid_http(self):
        assert _validate_base_url("http://localhost:8080/v1") is None

    def test_empty_url(self):
        assert _validate_base_url("") is not None

    def test_no_scheme(self):
        assert _validate_base_url("api.example.com/v1") is not None

    def test_ftp_scheme(self):
        assert _validate_base_url("ftp://example.com") is not None


class TestValidateApiKey:
    def test_valid_key(self):
        assert _validate_api_key("sk-abcdefghij123456") is None

    def test_env_var_reference(self):
        assert _validate_api_key("$OPENAI_API_KEY") is None

    def test_empty_key(self):
        assert _validate_api_key("") is not None

    def test_whitespace_only(self):
        assert _validate_api_key("   ") is not None

    def test_too_short(self):
        assert _validate_api_key("abc") is not None


# ---------------------------------------------------------------------------
# Config file I/O
# ---------------------------------------------------------------------------


class TestWriteConfig:
    def test_writes_yaml(self, tmp_path):
        config_file = tmp_path / "models.yaml"
        with (
            patch("skill_cert.cli.setup.CONFIG_DIR", tmp_path),
            patch("skill_cert.cli.setup.CONFIG_FILE", config_file),
        ):
            models = [
                ModelConfig(
                    model_name="test-model",
                    base_url="https://api.test.com/v1",
                    api_key="sk-test12345678",
                )
            ]
            result = _write_config(models)

            assert result == config_file
            assert config_file.exists()

            data = yaml.safe_load(config_file.read_text())
            assert len(data["models"]) == 1
            assert data["models"][0]["model_name"] == "test-model"
            assert data["models"][0]["base_url"] == "https://api.test.com/v1"

    def test_writes_fallback_model(self, tmp_path):
        config_file = tmp_path / "models.yaml"
        with (
            patch("skill_cert.cli.setup.CONFIG_DIR", tmp_path),
            patch("skill_cert.cli.setup.CONFIG_FILE", config_file),
        ):
            models = [
                ModelConfig(
                    model_name="test-model",
                    base_url="https://api.test.com/v1",
                    api_key="sk-test12345678",
                    fallback_model="fallback-model",
                )
            ]
            _write_config(models)
            data = yaml.safe_load(config_file.read_text())
            assert data["models"][0]["fallback_model"] == "fallback-model"

    def test_creates_directory(self, tmp_path):
        sub = tmp_path / "nested" / "dir"
        config_file = sub / "models.yaml"
        with (
            patch("skill_cert.cli.setup.CONFIG_DIR", sub),
            patch("skill_cert.cli.setup.CONFIG_FILE", config_file),
        ):
            _write_config(
                [ModelConfig(model_name="m", base_url="https://x.com", api_key="sk-12345678")]
            )
            assert config_file.exists()


class TestLoadExistingModels:
    def test_returns_empty_when_no_file(self, tmp_path):
        config_file = tmp_path / "models.yaml"
        with patch("skill_cert.cli.setup.CONFIG_FILE", config_file):
            assert _load_existing_models() == []

    def test_loads_valid_file(self, tmp_path):
        config_file = tmp_path / "models.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "models": [
                        {
                            "model_name": "m1",
                            "base_url": "https://api.test.com",
                            "api_key": "sk-test12345678",
                        }
                    ]
                }
            )
        )
        with patch("skill_cert.cli.setup.CONFIG_FILE", config_file):
            models = _load_existing_models()
            assert len(models) == 1
            assert models[0].model_name == "m1"

    def test_returns_empty_on_malformed_file(self, tmp_path):
        config_file = tmp_path / "models.yaml"
        config_file.write_text("not: valid: yaml: [[[")
        with patch("skill_cert.cli.setup.CONFIG_FILE", config_file):
            assert _load_existing_models() == []


# ---------------------------------------------------------------------------
# Connectivity test
# ---------------------------------------------------------------------------


class TestConnectivity:
    def test_success(self):
        model = ModelConfig(
            model_name="test", base_url="https://api.test.com/v1", api_key="sk-test12345678"
        )
        mock_adapter = MagicMock()
        mock_adapter.chat.return_value = "OK"
        with patch("adapters.factory.create_adapter", return_value=mock_adapter):
            success, msg = _test_connectivity(model)
        assert success is True
        assert "Connected" in msg

    def test_failure(self):
        model = ModelConfig(
            model_name="test", base_url="https://api.test.com/v1", api_key="sk-test12345678"
        )
        mock_adapter = MagicMock()
        mock_adapter.chat.side_effect = ConnectionError("refused")
        with patch("adapters.factory.create_adapter", return_value=mock_adapter):
            success, msg = _test_connectivity(model)
        assert success is False
        assert "refused" in msg

    def test_empty_response(self):
        model = ModelConfig(
            model_name="test", base_url="https://api.test.com/v1", api_key="sk-test12345678"
        )
        mock_adapter = MagicMock()
        mock_adapter.chat.return_value = ""
        with patch("adapters.factory.create_adapter", return_value=mock_adapter):
            success, msg = _test_connectivity(model)
        assert success is False
        assert "Empty" in msg


# ---------------------------------------------------------------------------
# Interactive setup
# ---------------------------------------------------------------------------


class TestSetupInteractive:
    def _make_inputs(self, inputs: list[str]):
        """Create an input function that returns values from a list."""
        iterator = iter(inputs)
        return lambda prompt="": next(iterator)

    def test_single_model_success(self, tmp_path, capsys):
        config_file = tmp_path / "models.yaml"
        inputs = [
            "qwen3.6-plus",  # model name
            "https://api.test.com/v1",  # base URL
            "sk-test12345678",  # API key
            "",  # fallback (skip)
            "n",  # don't add another
        ]
        mock_test = MagicMock(return_value=(True, "OK"))
        outputs = []

        with (
            patch("skill_cert.cli.setup.CONFIG_DIR", tmp_path),
            patch("skill_cert.cli.setup.CONFIG_FILE", config_file),
        ):
            result = _setup_interactive(
                input_fn=self._make_inputs(inputs),
                output_fn=outputs.append,
                test_fn=mock_test,
            )

        assert result == EXIT_OK
        assert config_file.exists()
        data = yaml.safe_load(config_file.read_text())
        assert data["models"][0]["model_name"] == "qwen3.6-plus"

    def test_two_models(self, tmp_path):
        config_file = tmp_path / "models.yaml"
        inputs = [
            "model-a",
            "https://api.a.com/v1",
            "sk-aaaaaaaaa",
            "",  # model 1
            "y",  # add another
            "model-b",
            "https://api.b.com/v1",
            "sk-bbbbbbbbb",
            "",  # model 2
            "n",  # don't add another
        ]
        mock_test = MagicMock(return_value=(True, "OK"))
        outputs = []

        with (
            patch("skill_cert.cli.setup.CONFIG_DIR", tmp_path),
            patch("skill_cert.cli.setup.CONFIG_FILE", config_file),
        ):
            result = _setup_interactive(
                input_fn=self._make_inputs(inputs),
                output_fn=outputs.append,
                test_fn=mock_test,
            )

        assert result == EXIT_OK
        data = yaml.safe_load(config_file.read_text())
        assert len(data["models"]) == 2

    def test_existing_config_cancel(self, tmp_path):
        config_file = tmp_path / "models.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "models": [
                        {
                            "model_name": "old",
                            "base_url": "https://x.com",
                            "api_key": "sk-old12345678",
                        }
                    ]
                }
            )
        )
        inputs = ["n"]  # cancel overwrite
        outputs = []

        with (
            patch("skill_cert.cli.setup.CONFIG_DIR", tmp_path),
            patch("skill_cert.cli.setup.CONFIG_FILE", config_file),
        ):
            result = _setup_interactive(
                input_fn=self._make_inputs(inputs),
                output_fn=outputs.append,
                test_fn=MagicMock(),
            )

        assert result == EXIT_OK
        # Original config preserved
        data = yaml.safe_load(config_file.read_text())
        assert data["models"][0]["model_name"] == "old"

    def test_connectivity_failure_save_anyway(self, tmp_path):
        config_file = tmp_path / "models.yaml"
        inputs = [
            "model-x",
            "https://api.x.com/v1",
            "sk-xxxxxxxxx",
            "",  # model
            "y",  # save anyway
            "n",  # don't add another
        ]
        mock_test = MagicMock(return_value=(False, "connection refused"))
        outputs = []

        with (
            patch("skill_cert.cli.setup.CONFIG_DIR", tmp_path),
            patch("skill_cert.cli.setup.CONFIG_FILE", config_file),
        ):
            result = _setup_interactive(
                input_fn=self._make_inputs(inputs),
                output_fn=outputs.append,
                test_fn=mock_test,
            )

        assert result == EXIT_OK
        assert config_file.exists()

    def test_connectivity_failure_skip(self, tmp_path):
        config_file = tmp_path / "models.yaml"
        inputs = [
            "model-x",
            "https://api.x.com/v1",
            "sk-xxxxxxxxx",
            "",  # model (fails)
            "n",  # don't save
            "model-y",
            "https://api.y.com/v1",
            "sk-yyyyyyyyy",
            "",  # model (ok)
            "n",  # don't add another
        ]

        def mock_test(model):
            if "model-x" in model.model_name:
                return (False, "failed")
            return (True, "OK")

        outputs = []
        with (
            patch("skill_cert.cli.setup.CONFIG_DIR", tmp_path),
            patch("skill_cert.cli.setup.CONFIG_FILE", config_file),
        ):
            result = _setup_interactive(
                input_fn=self._make_inputs(inputs),
                output_fn=outputs.append,
                test_fn=mock_test,
            )

        assert result == EXIT_OK
        data = yaml.safe_load(config_file.read_text())
        assert len(data["models"]) == 1
        assert data["models"][0]["model_name"] == "model-y"

    def test_connectivity_failure_save_anyway_single_model(self, tmp_path):
        """First model fails connectivity but user saves it anyway, then declines to add more."""
        config_file = tmp_path / "models.yaml"
        inputs = [
            "model-x",
            "https://api.x.com/v1",
            "sk-xxxxxxxxx",
            "",
            "y",  # save anyway despite failure
            "n",  # don't add another (model_num=2 triggers this prompt)
        ]
        mock_test = MagicMock(return_value=(False, "failed"))
        outputs = []

        with (
            patch("skill_cert.cli.setup.CONFIG_DIR", tmp_path),
            patch("skill_cert.cli.setup.CONFIG_FILE", config_file),
        ):
            result = _setup_interactive(
                input_fn=self._make_inputs(inputs),
                output_fn=outputs.append,
                test_fn=mock_test,
            )

        assert result == EXIT_OK
        data = yaml.safe_load(config_file.read_text())
        assert len(data["models"]) == 1
        assert data["models"][0]["model_name"] == "model-x"


# ---------------------------------------------------------------------------
# Non-interactive setup
# ---------------------------------------------------------------------------


class TestSetupNonInteractive:
    def test_success_with_test(self, tmp_path):
        config_file = tmp_path / "models.yaml"
        mock_test = MagicMock(return_value=(True, "OK"))
        with (
            patch("skill_cert.cli.setup.CONFIG_DIR", tmp_path),
            patch("skill_cert.cli.setup.CONFIG_FILE", config_file),
        ):
            result = _setup_non_interactive(
                model_name="qwen3.6-plus",
                base_url="https://api.test.com/v1",
                api_key="sk-test12345678",
                test_fn=mock_test,
            )
        assert result == EXIT_OK
        data = yaml.safe_load(config_file.read_text())
        assert data["models"][0]["model_name"] == "qwen3.6-plus"

    def test_skip_test(self, tmp_path):
        config_file = tmp_path / "models.yaml"
        with (
            patch("skill_cert.cli.setup.CONFIG_DIR", tmp_path),
            patch("skill_cert.cli.setup.CONFIG_FILE", config_file),
        ):
            result = _setup_non_interactive(
                model_name="test-model",
                base_url="https://api.test.com/v1",
                api_key="sk-test12345678",
                skip_test=True,
            )
        assert result == EXIT_OK

    def test_invalid_url(self):
        result = _setup_non_interactive(
            model_name="test",
            base_url="not-a-url",
            api_key="sk-test12345678",
            skip_test=True,
        )
        assert result == EXIT_ERROR

    def test_invalid_api_key(self):
        result = _setup_non_interactive(
            model_name="test",
            base_url="https://api.test.com/v1",
            api_key="",
            skip_test=True,
        )
        assert result == EXIT_ERROR


# ---------------------------------------------------------------------------
# run_setup dispatcher
# ---------------------------------------------------------------------------


class TestRunSetup:
    def test_interactive_when_no_model_name(self, tmp_path):
        config_file = tmp_path / "models.yaml"
        with (
            patch("skill_cert.cli.setup.CONFIG_DIR", tmp_path),
            patch("skill_cert.cli.setup.CONFIG_FILE", config_file),
            patch(
                "skill_cert.cli.setup._setup_interactive", return_value=EXIT_OK
            ) as mock_interactive,
        ):
            result = run_setup(None)
        assert result == EXIT_OK
        mock_interactive.assert_called_once()

    def test_non_interactive_with_model_name(self, tmp_path):
        config_file = tmp_path / "models.yaml"
        args = argparse.Namespace(
            model_name="test-model",
            base_url="https://api.test.com/v1",
            api_key="sk-test12345678",
            fallback_model="",
            skip_test=True,
        )
        with (
            patch("skill_cert.cli.setup.CONFIG_DIR", tmp_path),
            patch("skill_cert.cli.setup.CONFIG_FILE", config_file),
            patch(
                "skill_cert.cli.setup._setup_non_interactive", return_value=EXIT_OK
            ) as mock_non_interactive,
        ):
            result = run_setup(args)
        assert result == EXIT_OK
        mock_non_interactive.assert_called_once()


# ---------------------------------------------------------------------------
# CLI main integration — setup subcommand interception
# ---------------------------------------------------------------------------


class TestMainSetupInterception:
    def test_setup_subcommand_intercepted(self):
        """Verify that 'skill-cert setup' is intercepted before standard argparse."""
        with (
            patch("sys.argv", ["skill-cert", "setup", "--skip-test"]),
            patch("skill_cert.cli.setup.run_setup", return_value=EXIT_OK) as mock_setup,
        ):
            from skill_cert.cli.main import main

            result = main()
        assert result == EXIT_OK
        mock_setup.assert_called_once()

    def test_setup_with_flags(self):
        """Verify non-interactive flags are passed through."""
        with (
            patch(
                "sys.argv",
                [
                    "skill-cert",
                    "setup",
                    "--model-name",
                    "test-model",
                    "--base-url",
                    "https://api.test.com/v1",
                    "--api-key",
                    "sk-test12345678",
                    "--skip-test",
                ],
            ),
            patch("skill_cert.cli.setup.run_setup", return_value=EXIT_OK) as mock_setup,
        ):
            from skill_cert.cli.main import main

            result = main()
        assert result == EXIT_OK
        mock_setup.assert_called_once()
        args = mock_setup.call_args[0][0]
        assert args.model_name == "test-model"
        assert args.base_url == "https://api.test.com/v1"
