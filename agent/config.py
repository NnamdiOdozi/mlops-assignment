"""Load the selected experiment configuration from TOML."""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

config_path_value = os.environ.get("CONFIG_PATH")

if config_path_value:
    CONFIG_PATH = Path(config_path_value)
    if not CONFIG_PATH.is_absolute():
        CONFIG_PATH = ROOT / CONFIG_PATH
else:
    CONFIG_PATH = ROOT / "configs" / "bf16_baseline.toml"

with CONFIG_PATH.open("rb") as _f:
    CONFIG: dict[str, Any] = tomllib.load(_f)

EXPERIMENT_CONFIG = CONFIG["experiment"]
AGENT_CONFIG = CONFIG["agent"]
SCHEMA_CONFIG = CONFIG["schema"]
VLLM_CONFIG = CONFIG["vllm"]
