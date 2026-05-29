from __future__ import annotations

from pathlib import Path

import yaml


def load_config(path: str) -> dict:
    """Load a YAML configuration file."""
    config_path = Path(path).expanduser()

    if not config_path.is_file():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    try:
        with config_path.open("r", encoding="utf-8") as file:
            config = yaml.safe_load(file)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in config file {config_path}: {exc}") from exc

    if config is None:
        return {}

    if not isinstance(config, dict):
        raise ValueError(f"Config file must contain a YAML mapping: {config_path}")

    return config
