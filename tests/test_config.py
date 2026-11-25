from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from safety_games.config import (
    ConfigError, ExperimentConfig, ExperimentMode, LLMConfig, SandboxConfig, load_config,
)


class ConfigTests(unittest.TestCase):
    def load_text(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "experiment.toml"
            path.write_text(text, encoding="utf-8")
            return load_config(path)

    def test_example_loads_and_roundtrips_to_plain_data(self):
        config = load_config("configs/baseline.toml")
        self.assertEqual(config.mode, ExperimentMode.BASELINE)
        self.assertEqual(config.to_dict()["sandbox"]["max_output_bytes"], 65536)
        self.assertEqual(config.to_dict()["output_dir"], "runs")

    def test_modes_are_configuration_labels(self):
        for mode in ExperimentMode:
            with self.subTest(mode=mode):
                self.assertEqual(self.load_text(f'mode = "{mode.value}"').mode, mode)

    def test_typo_unknown_secret_and_unknown_mode_are_rejected(self):
        for text in ('rounnds = 2', 'mode = "missing"', '[llm]\napi_key = "secret"', '[extra]\nx = 1'):
            with self.subTest(text=text), self.assertRaises(ConfigError):
                self.load_text(text)

    def test_invalid_toml_or_table_is_rejected(self):
        for text in ('rounds = [', 'llm = "api"', 'sandbox = []'):
            with self.subTest(text=text), self.assertRaises(ConfigError):
                self.load_text(text)

    def test_invalid_numeric_values_are_rejected(self):
        for changes in ({"rounds": 0}, {"rounds": True}, {"rounds": 1.5}, {"seed": -1}):
            with self.subTest(changes=changes), self.assertRaises(ConfigError):
                replace(ExperimentConfig(), **changes)
        for changes in ({"timeout_s": 0}, {"cpus": float("nan")}, {"memory_mb": 16},
                        {"pids_limit": True}, {"max_output_bytes": -1}, {"tmpfs_mb": 129}):
            with self.subTest(changes=changes), self.assertRaises(ConfigError):
                replace(SandboxConfig(), **changes)

    def test_model_configuration_validation(self):
        for changes in ({"backend": "magic"}, {"temperature": float("inf")},
                        {"temperature": -0.1}, {"max_output_tokens": True},
                        {"api_key_env": "not a variable"}, {"model": ""}):
            with self.subTest(changes=changes), self.assertRaises(ConfigError):
                replace(LLMConfig(), **changes)
        self.assertEqual(LLMConfig(backend="local", api_key_env="LLM_API_KEY").backend, "local")

    def test_config_does_not_accept_docker_option_as_image(self):
        for image in ("--privileged", "image with spaces", ""):
            with self.subTest(image=image), self.assertRaises(ConfigError):
                SandboxConfig(image=image)


if __name__ == "__main__":
    unittest.main()
